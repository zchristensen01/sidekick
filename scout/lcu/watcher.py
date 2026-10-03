"""The `scout watch` state machine: Idle -> Drafting -> Final -> Loading -> InGame -> Idle.

One report per game (2026-10-03: "never the free draft read; straight from champ select
to the LLM report"). In champ select: pick options until I lock, then only "picks locked". At
the loading screen, as soon as everyone's summoner spells show: enemy roles confirmed, the
players' records and likely duos / one-tricks gathered, and the final report written by the
LLM is the one report shown ("writing your report" until then). The rules version is shown
only when the AI writer is off, or as a labelled fallback when it fails. Discards on dodge;
nothing is computed from the game itself. Every champ select is also recorded
(scout/lcu/recorder.py). docs/LCU.md section 6.
"""

import dataclasses
import threading
import time
import traceback
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from scout.analysis.insights import analyze, stats_disagreements
from scout.analysis.role_inference import RoleRates
from scout.analysis.stats import NO_STATS
from scout.counterpick import DEFAULT_BANDS, Bands
from scout.data import review
from scout.data.patch import short_patch
from scout.data.riot import RiotError
from scout.data.stats_service import StatsService
from scout.data.store import Knowledge
from scout.lcu.champselect import (
    ChampionIndex,
    NotReportable,
    apply_confirmed_roles,
    apply_spells,
    confirmed_roles,
    parse_session,
)
from scout.lcu.client import (
    CHAMP_SELECT_SESSION,
    CHAMPION_MASTERY,
    GAMEFLOW_PHASE,
    GAMEFLOW_SESSION,
    SUMMONER_BY_PUUID,
    LcuError,
    LcuUnavailable,
)
from scout.lcu.recorder import IN_GAME_PHASES, Reader, Recorder, game_roster
from scout.loading import Riot, enemies_at_loading
from scout.loading import check as check_loading
from scout.loading import resolve as resolve_players
from scout.model.game import GameState
from scout.model.roles import Role
from scout.picks import Picker, parse_mastery
from scout.picks import render as render_picks
from scout.player_cards import PlayerCard, gather, seats_at_loading
from scout.pool import Pool
from scout.postgame.check import check as check_game
from scout.postgame.check import record as record_postgame
from scout.postgame.check import summary as postgame_summary
from scout.postgame.claims import claims_from
from scout.postgame.claims import load as load_claims
from scout.postgame.claims import save as save_claims
from scout.postgame.grade import MatchError
from scout.report.builder import build_input
from scout.report.past import save as save_past
from scout.report.render import render_text, render_written
from scout.report.select import Item, Report, Section, select
from scout.report.view import picks_view, report_view, status_view
from scout.report.writer import ReportWriter
from scout.rules.engine import Rule, evaluate

FINAL_TIMER_PHASES = frozenset({"FINALIZATION", "GAME_STARTING"})
LOADING_PHASES = frozenset({"GameStart", "InProgress", "Reconnect"})
# The client is in champ select or a game: background work waits (Watcher.idle)
BUSY_PHASES = frozenset({"ChampSelect"}) | LOADING_PHASES
CLIENT_WAIT_S = 3.0


@dataclass
class Live:
    """One champ select being watched."""

    game_id: Any
    game: GameState | None = None
    report_path: Path | None = None
    final_seen_at: float | None = None
    skipped: bool = False
    stats_pending: bool = False  # the last report went out while stats were still loading
    picks_text: str = ""  # the pick options last shown (M9b)
    shown: tuple[str, str] | None = None  # (title, text) of the report last shown
    addendum: list[str] = field(default_factory=list)  # loading-screen lines (M11)
    addendum_started: bool = False
    addendum_done: threading.Event = field(default_factory=threading.Event)
    written_shown: bool = False  # the LLM's version is on screen (late stats keep it there)
    view_args: tuple[Any, ...] | None = None  # (report, insights, written, phase) last shown
    players: list[PlayerCard] = field(default_factory=list)  # loading-screen records (M16)
    match_game_id: int | None = None  # the game's id from the loading screen (M10)
    claims_path: Path | None = None  # the final report's claims, checked after the game
    final_view: dict[str, Any] | None = None  # the final report's screen, kept for History (M23)
    players_started: bool = False
    players_done: threading.Event = field(default_factory=threading.Event)


@dataclass
class Watcher:
    client: Reader
    knowledge: Knowledge
    rules: list[Rule]
    rates: RoleRates
    index: ChampionIndex
    reports_dir: Path
    notes: list[dict[str, str]] = field(default_factory=list)
    low_confidence: float = 0.6
    recorder: Recorder | None = None
    echo: Callable[[str], None] = print
    on_report: Callable[[str, str], None] | None = None  # the report window (M6b)
    writer: ReportWriter | None = None  # the LLM writer (M7); None = rules report only
    max_words: dict[Role, int] = field(default_factory=dict)
    write_in_background: bool = True  # tests write in the same thread
    stats: StatsService | None = None  # OP.GG numbers (M8); None = traits only
    fetch_budget_s: float = 5.0  # how long a report waits for stats still loading
    review_queue: Path | None = None  # stats-vs-traits disagreements are queued here
    bands: Bands = DEFAULT_BANDS  # counter-pick bands (config.yaml counterpick)
    picker: Picker | None = None  # pick suggestions before I lock (M9b)
    # the logged-in account's champions, asked at each champ select (M22); None = keep the pool
    account_pool: Callable[[], Pool | None] | None = None
    account_name: Callable[[], str] | None = None  # who's playing, for History (M23)
    riot: Riot | None = None  # loading-screen duo / one-trick check (M11); None = off
    opgg_region: str = ""  # OP.GG region for players' records at loading (M16); "" = off
    players_budget_s: float = 15.0  # how long the written report waits for those records
    history_dir: Path | None = None  # post-game results (M10); None = no automatic check
    postgame_waits_s: tuple[float, ...] = (90, 60, 60, 120, 180, 300)  # Riot publishes late
    on_view: Callable[[dict[str, Any]], None] | None = None  # the app's dashboard (M13)
    on_state: Callable[[str, str], None] | None = None  # (state, message) for the app's header
    clock: Callable[[], float] = time.monotonic
    now: Callable[[], datetime] = lambda: datetime.now().astimezone()
    state: str = "idle"  # idle | drafting | final | loading | in_game
    phase: str = ""  # the client's gameflow phase at the last poll
    live: Live | None = None
    _seq: int = (
        0  # increments with every report, so a slow written version can't overwrite a newer one
    )

    # ------------------------------------------------------------ polling

    def tick(self) -> None:
        """Read the client once and act on it. Raises LcuUnavailable if the client is closed."""
        phase = self.client.get(GAMEFLOW_PHASE)
        session = self.client.get(CHAMP_SELECT_SESSION) if phase == "ChampSelect" else None
        gameflow = None
        recording = self.recorder is not None and self.recorder.current is not None
        if phase in IN_GAME_PHASES and (self.state == "loading" or recording or
                                         self.state in ("drafting", "final")):  # fmt: skip
            gameflow = self.client.get(GAMEFLOW_SESSION)
        if self.recorder is not None:
            self.recorder.process(phase, session, gameflow)
        self.process(phase, session, gameflow)

    def idle(self) -> bool:
        """Not in champ select or a game, whether or not this game was followed (Swiftplay has
        no champ select; the app may open mid-game): when background work may run."""
        return self.state == "idle" and self.phase not in BUSY_PHASES

    def process(self, phase: Any, session: Any, gameflow: Any = None) -> None:
        self.phase = str(phase or "")
        if phase == "ChampSelect":
            self._champ_select(session)
        elif phase in IN_GAME_PHASES:
            self._game(phase, gameflow)
        elif self.state in ("drafting", "final"):
            self._discard(phase)
        else:
            if self.state in ("loading", "in_game"):
                self._state("ended", "Game over. Waiting for the next game.")
            self.state, self.live = "idle", None

    # ------------------------------------------------------------ champ select

    def _champ_select(self, session: Any) -> None:
        if not isinstance(session, dict):
            return  # champ select is starting; the session isn't ready yet
        game_id = session.get("gameId")
        if (
            self.live is None
            or self.state in ("idle", "in_game")
            or (game_id and self.live.game_id and game_id != self.live.game_id)
        ):
            if self.live is not None and self.state in ("drafting", "final"):
                self._discard("a new champ select")
            self.live, self.state = Live(game_id=game_id), "drafting"
            self.echo("Champion select started.")
            self._state("champ_select", "Champion select started.")
            self._use_account_pool()
            self._read_mastery()
        live = self.live
        if live.skipped:
            return
        try:
            game = parse_session(session, self.index, self.rates)
        except NotReportable as exc:
            live.skipped = True
            self.echo(f"No report: {exc}")
            return
        live.game = game
        if self.stats is not None:
            self.stats.prefetch(game)  # background; only what isn't cached yet
        if game.my_role not in game.ally:  # I haven't locked yet
            self._suggest(game, live)
        timer = session.get("timer") if isinstance(session.get("timer"), dict) else {}
        if (
            timer.get("phase") not in FINAL_TIMER_PHASES
            or len(game.enemy) < 5
            or len(game.ally) < 5
        ):
            return
        if live.final_seen_at is None:  # no report here: it comes at the loading screen
            live.final_seen_at = self.clock()
            self.state = "final"
            self.echo("Picks locked. The report comes at the loading screen.")
            self._status("picks_locked", "Your report comes at the loading screen, as soon as it "
                         "shows everyone's summoner spells.")  # fmt: skip

    # ------------------------------------------------------------ loading screen and game

    def _game(self, phase: str, gameflow: Any) -> None:
        live = self.live
        if self.state in ("drafting", "final") and live and live.game and not live.skipped:
            complete = len(live.game.enemy) == 5 and len(live.game.ally) == 5
            self.state = "loading" if complete else "in_game"
        if self.state != "loading" or live is None or live.game is None:
            if live is not None and phase == "GameStart":
                self._stats_update(live)  # still the loading screen
            if phase not in LOADING_PHASES:
                self._state("ended", "Game over. Waiting for the next game.")
                if live is not None and live.claims_path is not None:
                    self._start_postgame(live.claims_path)
                self.state, self.live = "idle", None  # the game ended
            return
        roster = game_roster(gameflow)
        data = gameflow.get("gameData") if isinstance(gameflow, dict) else None
        if isinstance(data, dict) and isinstance(data.get("gameId"), int) and data["gameId"]:
            live.match_game_id = data["gameId"]
        if not roster.get("spells"):
            if phase != "GameStart":  # the game started and the roster never showed
                self.echo("Game started; the loading roster never showed, roles stay guessed.")
                self.state = "in_game"
                self._start_players(live, live.game, gameflow)
                self._report(live.game, "Final report (roles guessed)")
            return
        keys = {self.index.by_key.get(k): k for k in self.index.by_key}
        enemy_keys = [keys[p.champ_id] for p in live.game.enemy.values() if p.champ_id in keys]
        confirmed = {self.index.by_key[k]: role for k, role in
                     confirmed_roles(roster, enemy_keys, self.index.smite_key).items()}  # fmt: skip
        game, changes = apply_confirmed_roles(live.game, confirmed, self.rates)
        game = apply_spells(game, roster, self.index)
        self.state = "in_game"
        self._start_addendum(live, game, gameflow, enemy_keys)
        if self.stats is not None:
            self.stats.prefetch(game)
        if not changes:
            self.echo("Loading screen: roles as guessed (no enemy Smite or positions shown).")
        name = self.knowledge.facts
        lines = []
        for champ, guessed, real in changes:
            if guessed == real:
                lines.append(f"Confirmed at loading: {name(champ).name} is their {real.value}.")
            else:
                was = f", not their {guessed.value}" if guessed else ""
                lines.append(
                    f"Corrected at loading: {name(champ).name} is their {real.value}{was}."
                )
        for line in lines:
            self.echo(line)
        game = _with_notes(game, lines)
        live.game = game
        title = "Report with roles confirmed" if changes else "Final report"
        self._start_players(live, game, gameflow)
        self._report(game, title)  # the one report, written by the LLM

    def _discard(self, why: str) -> None:
        """A dodge: champ select ended without a game (no report exists before loading)."""
        live = self.live
        if live is not None and live.final_seen_at is not None:
            self.echo(f"Champion select ended without a game ({why}).")
            self._state("waiting_game", f"Champion select ended without a game ({why}).")
        self.state, self.live = "idle", None

    # ------------------------------------------------------------ output

    def _suggest(self, game: GameState, live: Live) -> None:
        """Pick options for my role, shown when they change (enemies lock, stats arrive)."""
        if self.picker is None:
            return
        if self.stats is not None:
            opp = game.enemy.get(game.my_role)
            self.stats.prefetch_tables(game.my_role, self.picker.champions_to_fetch(game),
                                       opp.champ_id if opp else None)  # fmt: skip
            allies = {r: p.champ_id for r, p in game.ally.items()}
            self.stats.prefetch_synergies(game.my_role, allies)
        suggestions = self.picker.suggest(game)
        text = render_picks(suggestions, self.bands.low_confidence)
        if text == live.picks_text:
            return
        live.picks_text = text
        if self.on_view is not None:
            names = {p.champ_id: self.knowledge.facts(p.champ_id).name
                     for p in (*game.ally.values(), *game.enemy.values())}  # fmt: skip
            names |= {b: self.knowledge.facts(b).name for b in game.bans}
            self.on_view(picks_view(suggestions, game, names))
        self.echo("")
        self.echo(text.rstrip("\n"))
        if self.on_report is not None:
            self.on_report(f"Pick options ({game.my_role.value})", text)

    def _with_pool_note(self, game: GameState) -> GameState:
        """Off-pool lock: the report is the same, plus a note (docs/COUNTERPICK.md)."""
        pool = self.picker.pool.get(game.my_role, ()) if self.picker else ()
        me = game.ally.get(game.my_role)
        if not pool or me is None or me.champ_id in pool:
            return game
        name = self.knowledge.facts(me.champ_id).name
        note = f"{name} isn't in your {game.my_role.value} pool (the Champions button adds it)."
        return game if note in game.notes else _with_notes(game, [note])

    def _use_account_pool(self) -> None:
        """The champions of whoever is logged in: each account keeps its own (M22)."""
        if self.picker is None or self.account_pool is None:
            return
        pool = self.account_pool()
        if pool is not None:
            self.picker.pool = pool

    def _read_mastery(self) -> None:
        """My champion mastery, read once per champ select (read-only)."""
        if self.picker is None or self.client is None:
            return
        try:
            raw = self.client.get(CHAMPION_MASTERY)
        except LcuError:
            return
        found = parse_mastery(raw, self.index.by_key)
        if found:
            self.picker.mastery = found

    def _stats_update(self, live: Live) -> None:
        """One re-render when stats that were still loading at report time have arrived. After
        the final report (its claims are saved) it stays the final report, written again with
        the numbers, instead of falling back to the draft read and dropping the written one."""
        if (live.stats_pending and live.claims_path is not None and live.game is not None
                and self.stats is not None and not self.stats.busy()):  # fmt: skip
            live.stats_pending = False
            self._report(live.game, "Final report (stats arrived)")

    def _report(self, game: GameState, title: str) -> None:
        """Build and save the final report and have the LLM write it; it's shown once written
        (with no writer, the rules version is shown at once)."""
        started = time.perf_counter()
        game = self._with_pool_note(game)
        stats = NO_STATS
        if self.stats is not None:
            stats = self.stats.for_game(game, self.fetch_budget_s)
            if self.live is not None:
                self.live.stats_pending = self.stats.busy()
        insights = analyze(game, self.knowledge, stats, self.bands)
        self._queue_disagreements(insights)
        fired = evaluate(self.rules, insights)
        report = select(insights, fired, self.notes, self.low_confidence)
        text = render_text(report)
        elapsed = time.perf_counter() - started
        live = self.live
        lag = ""
        if live is not None and live.final_seen_at is not None:
            lag = f", {self.clock() - live.final_seen_at:.1f} s after picks locked"
        writing = self.writer is not None
        self.echo("")
        if writing:  # nothing shown until the LLM's version is in
            self.echo(f"{title}: built in {elapsed:.2f} s{lag}; the AI is writing it.")
            if live is None or not live.written_shown:
                self._status("writing", "Roles and summoner spells are in. Gathering the "
                             "players and likely duos, then the AI writes your "
                             "report.")  # fmt: skip
        else:
            self.echo("=" * 100)
            self.echo(f"{title} (built in {elapsed:.2f} s{lag})")
            self.echo("=" * 100)
            self.echo(text.rstrip("\n"))
            self._show(live, f"{title} ({report.role.value}, {report.champion})", text)
            self._view(live, report, insights, None, "final")
        if live is not None:
            if live.report_path is None:
                me = report.ally.get(game.my_role, "unknown").replace(" ", "")
                stamp = self.now().strftime("%Y-%m-%d_%H%M%S")
                live.report_path = self.reports_dir / f"{stamp}_{game.my_role.value}_{me}.md"
            self.reports_dir.mkdir(parents=True, exist_ok=True)
            body = f"# {title}\n\n```text\n{text}```\n" + _addendum_section(live)
            live.report_path.write_text(body, encoding="utf-8", newline="\n")
            shown = {i.source for s in report.sections for i in s.items}  # what it predicted
            live.claims_path = live.report_path.with_suffix(".json")
            game_id = live.match_game_id or (live.game_id if isinstance(live.game_id, int)
                                             else None)  # fmt: skip
            save_claims(live.claims_path, game, game_id,
                        claims_from(insights, fired, shown), self.now().isoformat())
            self._save_past(live)
        self._seq += 1
        if writing:
            payload = build_input(report, insights, self.knowledge,
                                  self.max_words.get(report.role, 120))  # fmt: skip
            job = (payload, report, title, text, self._seq, live, insights)
            if self.write_in_background:
                threading.Thread(target=self._write, args=job, daemon=True).start()
            else:
                self._write(*job)

    def _view(self, live: Live | None, report: Report, insights: Any, written: Any,
              phase: str) -> None:  # fmt: skip
        """The dashboard's report screen (M13), with the loading-screen lines once they're in."""
        if live is not None:
            live.view_args = (report, insights, written, phase)
        final = phase == "final" and live is not None
        if self.on_view is None and not final:
            return
        addendum = live.addendum if live is not None else []
        players = [c.view() for c in live.players] if live is not None else []
        view = report_view(report, insights, written, phase, addendum, players)
        if self.on_view is not None:
            self.on_view(view)
        if final and live is not None:
            live.final_view = view
            self._save_past(live)

    def _save_past(self, live: Live) -> None:
        """The final screen next to the report, for the app's History (M23); rewritten when
        the written version or the loading-screen records arrive. Only on this PC."""
        if live.report_path is None or live.final_view is None:
            return
        meta = {"saved_at": self.now().isoformat(timespec="seconds"),
                "account": self.account_name() if self.account_name is not None else ""}
        try:
            save_past(live.report_path, live.final_view, meta)
        except OSError as exc:
            self.echo(f"(Couldn't save this game for History: {exc})")

    def _status(self, state: str, message: str) -> None:
        """A status screen in the app (picks locked, writing the report)."""
        if self.on_view is not None:
            self.on_view(status_view(state, message))

    def _state(self, state: str, message: str) -> None:
        if self.on_state is not None:
            self.on_state(state, message)

    def _show(self, live: Live | None, title: str, text: str) -> None:
        """Show a report in the window, with the loading-screen lines if they're in."""
        if live is not None:
            live.shown = (title, text)
        if self.on_report is not None:
            extra = _addendum_text(live)
            self.on_report(title, text + extra)

    # ------------------------------------------------------------ loading screen (M11)

    def _start_addendum(self, live: Live, game: GameState, gameflow: Any,
                        enemy_keys: list[int]) -> None:  # fmt: skip
        """Likely duos and one-tricks among the visible enemies: once, in the background."""
        if live.addendum_started:
            return
        live.addendum_started = True
        if self.riot is None:
            live.addendum_done.set()
            return
        key_of = {c: k for k, c in self.index.by_key.items()}
        names = {k: self.knowledge.facts(self.index.by_key[k]).name for k in enemy_keys}
        roles = {key_of[p.champ_id]: r for r, p in game.enemy.items() if p.champ_id in key_of}
        job = (live, gameflow, enemy_keys, names, roles)
        if self.write_in_background:
            threading.Thread(target=self._addendum, args=job, daemon=True).start()
        else:
            self._addendum(*job)

    def _addendum(self, live: Live, gameflow: Any, enemy_keys: list[int], names: dict[int, str],
                  roles: dict[int, Role]) -> None:  # fmt: skip
        lines: list[str] = []
        try:
            lines = self._check_enemies(gameflow, enemy_keys, names, roles)
        finally:
            if self.live is live:
                live.addendum = lines
            live.addendum_done.set()  # the writer waits for this
        if self.live is not live or not lines:
            return
        self.echo("")
        for line in lines:
            self.echo(f"Loading screen: {line}" if not line.startswith("Loading screen") else line)
        if live.shown is not None:
            self._show(live, *live.shown)
        if live.view_args is not None:
            self._view(live, *live.view_args)
        if live.report_path is not None and live.report_path.exists():
            body = live.report_path.read_text(encoding="utf-8")
            if "## Loading screen" not in body:
                head, sep, rest = body.partition("\n## Rules version")
                live.report_path.write_text(head.rstrip("\n") + "\n" + _addendum_section(live)
                                            + (sep + rest if sep else ""),
                                            encoding="utf-8", newline="\n")  # fmt: skip

    def _check_enemies(self, gameflow: Any, enemy_keys: list[int], names: dict[int, str],
                       roles: dict[int, Role]) -> list[str]:  # fmt: skip
        assert self.riot is not None
        enemies, hidden = enemies_at_loading(gameflow, enemy_keys, names, roles)
        if not enemies and not hidden:
            return []
        try:
            enemies, unresolved = resolve_players(enemies, self._riot_id, self.riot)
        except RiotError as exc:
            return [f"Loading screen check skipped: {exc}."]
        return check_loading(self.riot, enemies, hidden + unresolved).lines()

    def _start_players(self, live: Live, game: GameState, gameflow: Any) -> None:
        """Each visible player's record on their champion (M16): once, in the background."""
        if live.players_started:
            return
        live.players_started = True
        opgg = self.stats.opgg if self.stats is not None else None
        if opgg is None or not self.opgg_region:
            live.players_done.set()
            return
        key_of = {c: k for k, c in self.index.by_key.items()}
        me = game.ally.get(game.my_role)
        seats = seats_at_loading(
            gameflow, [key_of[p.champ_id] for p in game.ally.values() if p.champ_id in key_of],
            self.index.by_key, {c: self.knowledge.facts(c).name for c in key_of},
            {p.champ_id: r for team in (game.ally, game.enemy) for r, p in team.items()},
            key_of.get(me.champ_id) if me else None,
        )  # fmt: skip
        region = self.opgg_region

        def job() -> None:
            try:
                cards = gather(seats, self._riot_id, lambda n, t: opgg.profile(n, t, region))
            finally:
                live.players_done.set()
            if self.live is not live or not cards:
                return
            live.players = cards
            self.echo("")
            for c in cards:
                self.echo(f"Players: {c.line()}")
            if live.shown is not None:
                self._show(live, *live.shown)
            if live.view_args is not None:
                self._view(live, *live.view_args)

        if self.write_in_background:
            threading.Thread(target=job, name="sidekick-players", daemon=True).start()
        else:
            job()

    def _start_postgame(self, path: Path) -> None:
        """Check the report against the match once Riot publishes it (M10), in the background."""
        riot = self.riot
        if riot is None or self.history_dir is None:
            return
        platform = getattr(riot, "platform", "")

        def job() -> None:
            saved = load_claims(path)
            for wait in self.postgame_waits_s:
                time.sleep(wait)
                try:
                    results = check_game(saved, riot, self.knowledge, platform)
                except MatchError as exc:
                    if "hasn't published" in str(exc):
                        continue
                    self.echo(f"Post-game check skipped: {exc}.")
                    return
                except RiotError as exc:
                    self.echo(f"Post-game check skipped: {exc}.")
                    return
                assert self.history_dir is not None
                record_postgame(self.history_dir, saved, results, self.now())
                lines = postgame_summary(results)
                self.echo("")
                for line in lines:
                    self.echo(line)
                if self.state == "idle":
                    self._state("ended", lines[0] + " Details: Settings, Open saved reports.")
                return
            self.echo("Post-game check: the match wasn't published in time; `scout postgame` "
                      "checks it later.")  # fmt: skip

        if self.write_in_background:
            threading.Thread(target=job, name="sidekick-postgame", daemon=True).start()
        else:
            job()

    def _riot_id(self, client_puuid: str) -> tuple[str, str] | None:
        """A visible player's Riot ID from the client (read-only); None if hidden or unknown."""
        try:
            found = self.client.get(SUMMONER_BY_PUUID.format(puuid=client_puuid))
        except (LcuError, ValueError):
            return None
        if isinstance(found, dict) and found.get("gameName") and found.get("tagLine"):
            return str(found["gameName"]), str(found["tagLine"])
        return None

    def _queue_disagreements(self, insights: Any) -> None:
        if self.review_queue is None:
            return
        found = stats_disagreements(insights)
        if found:
            patch = short_patch(insights.game.ddragon_version)
            review.add(self.review_queue, [review.entry(c, "stats_disagree", d, patch, self.now())
                                           for c, d in found])  # fmt: skip

    def _write(self, payload: dict[str, Any], report: Report, title: str, rules_text: str,
               seq: int, live: Live | None, insights: Any = None) -> None:  # fmt: skip
        """The LLM-written version; shown only if no newer report replaced this one meanwhile."""
        assert self.writer is not None
        if live is not None:  # wait for the players' records and the duo check, then write them in
            end = time.monotonic() + self.players_budget_s
            for done in (live.players_done, live.addendum_done):
                if live.players_started or done is live.addendum_done:
                    done.wait(max(0.0, end - time.monotonic()))
            if live.players:
                payload = with_players(payload, live.players)
            if live.addendum:
                report, payload = with_loading(report, payload, live.addendum)
        result = self.writer.write(payload)
        if seq != self._seq or self.live is not live:
            return
        if result.written is None:  # the rules version, labelled, rather than nothing
            note = result.note or "no answer"
            self.echo(f"(No written version: {note}; showing the rules version.)")
            fallback = dataclasses.replace(report, warnings=[
                *report.warnings, f"The AI writer didn't write this one ({note}): this is the "
                "rules version, with the same facts."])  # fmt: skip
            self._show(live, f"{title} ({report.role.value}, {report.champion})", rules_text)
            if insights is not None:
                self._view(live, fallback, insights, None, "final")
            return
        text = render_written(report, result.written)
        if live is not None:
            live.written_shown = True
        if insights is not None:
            self._view(live, report, insights, result.written, "final")
        how = "no new call, same draft" if result.cached else f"{result.calls} call(s)"
        self.echo("")
        self.echo("=" * 100)
        self.echo(f"{title}, written ({how})")
        self.echo("=" * 100)
        self.echo(text.rstrip("\n"))
        self._show(live, f"{title} ({report.role.value}, {report.champion})", text)
        if live is not None and live.report_path is not None:
            body = (f"# {title}\n\n```text\n{text}```\n" + _addendum_section(live)
                    + f"\n## Rules version\n\n```text\n{rules_text}```\n")  # fmt: skip
            live.report_path.write_text(body, encoding="utf-8", newline="\n")


def with_loading(report: Report, payload: dict[str, Any],
                 lines: list[str]) -> tuple[Report, dict[str, Any]]:  # fmt: skip
    """The loading-screen lines (likely duos, one-tricks; champions only, never names) as the
    report's last section, so the LLM writes them in."""
    items = [Item(f"loading:{i}", line, "high", 50) for i, line in enumerate(lines, 1)]
    section = Section("loading_screen", "Loading screen", False, items)
    entry = {"key": section.key, "title": section.title, "always": False,
             "items": [{"source": i.source, "confidence": i.confidence, "text": i.text,
                        "numbers": []} for i in items]}  # fmt: skip
    return (dataclasses.replace(report, sections=[*report.sections, section]),
            {**payload, "sections": [*payload["sections"], entry]})


def _loading_lines(live: Live | None) -> list[str]:
    if live is None:
        return []
    return [*live.addendum, *(c.line() for c in live.players)]


def _addendum_text(live: Live | None) -> str:
    lines = _loading_lines(live)
    if not lines:
        return ""
    return "\nLOADING SCREEN\n" + "".join(f"- {line}\n" for line in lines)


def _addendum_section(live: Live | None) -> str:
    lines = _loading_lines(live)
    if not lines:
        return ""
    return "\n## Loading screen\n\n" + "".join(f"- {line}\n" for line in lines)


def with_players(payload: dict[str, Any], cards: list[PlayerCard]) -> dict[str, Any]:
    """The writer's input plus a Players section and records (display strings, no names)."""
    items = [{"source": f"player:{c.side}:{c.role.value if c.role else c.champ_id}",
              "confidence": "high", "text": c.line(), "numbers": []}
             for c in cards if not c.note]  # fmt: skip
    sections = list(payload["sections"])
    if items:
        sections.append({"key": "players", "title": "Players", "always": False, "items": items})
    records = [{k: v for k, v in c.view().items() if k not in ("id", "text")} for c in cards]
    return {**payload, "sections": sections, "players": records}


def _with_notes(game: GameState, lines: list[str]) -> GameState:
    return dataclasses.replace(game, notes=[*game.notes, *lines])


def run(
    watcher: Watcher,
    poll_seconds: float,
    *,
    wait: Callable[[float], Any] = time.sleep,
    echo: Callable[[str], None] = print,
    error_log: Path | None = None,
    stop: threading.Event | None = None,
) -> None:
    """Watch until Ctrl+C (or `stop` is set). Waits for the client; never crashes on bad data."""
    connected: bool | None = None
    try:
        while stop is None or not stop.is_set():
            try:
                watcher.tick()
                if connected is not True:
                    echo("Connected to the League client. Waiting for champion select.")
                    if watcher.state == "idle":
                        watcher._state("waiting_game", "Connected to the League client.")
                connected = True
            except LcuUnavailable:
                if connected is not False:
                    echo("Waiting for the League client to open...")
                    watcher._state("waiting_client", "Open the League client to start.")
                connected = False
            except LcuError:
                raise  # e.g. a certificate problem: retrying won't fix it
            except Exception as exc:  # one bad read must not end the watch
                echo(f"Couldn't read champ select ({type(exc).__name__}: {exc}); still watching.")
                if error_log is not None:
                    error_log.parent.mkdir(parents=True, exist_ok=True)
                    with error_log.open("a", encoding="utf-8") as f:
                        f.write(f"{datetime.now().isoformat()}\n{traceback.format_exc()}\n")
            wait(poll_seconds if connected else max(poll_seconds, CLIENT_WAIT_S))
    except KeyboardInterrupt:
        echo("Stopping.")
    finally:
        if watcher.recorder is not None:
            watcher.recorder.stop()
