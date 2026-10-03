"""Stats for reports: fetch from OP.GG (in the background during a draft), store, look up.

- `refresh_lane_meta`: lane stats and role rates (one lane-meta call, plus one matchup guide to
  learn OP.GG's patch, which lane meta doesn't say). `scout refresh` and `scout watch` at start.
- `refresh_pool`: matchup tables for the owner's champ pool, nightly (`scout refresh --pool`).
- `prefetch`: during a draft, a matchup guide per lane as soon as both champions are known, my
  opponent's guide into me (their usual build), bot duo synergies. At most 2 calls at once.
- `for_game`: waits up to the fetch budget for calls still running, then reads the database.
docs/DATA.md (Keeping data current, During a draft). Never blocks a report on the network for
longer than the budget; with OP.GG down, reports carry a one-line notice instead.
"""

import dataclasses
import time
from collections.abc import Callable, Iterable, Mapping, Sequence
from concurrent.futures import Future, ThreadPoolExecutor
from concurrent.futures import wait as wait_for
from dataclasses import dataclass, field
from datetime import datetime
from threading import Lock
from typing import Any

from scout.analysis.stats import GameStats, StatsSettings, game_stats
from scout.data.opgg import (
    GUIDE,
    LANE_META,
    POSITION,
    SYNERGIES,
    Opgg,
    OpggError,
    OpggNoData,
    name_key,
)
from scout.data.opgg import opgg_name as to_opgg_name
from scout.data.patch import short_patch
from scout.data.stats_db import StatsDb
from scout.model.game import GameState
from scout.model.roles import Role

Row = Mapping[str, str]
POOL_OPPONENTS = 5  # nightly: guides against each pool champion's most-played opponents
# A draft asks for the same calls on every client update (about once a second). A call that
# already ran isn't repeated for this long, whether it worked (then it's cached in the database
# anyway) or failed or had no data (then retrying each second only queues behind OP.GG's limit).
RETRY_AFTER_S = 600.0


@dataclass(frozen=True)
class Champion:
    champ_id: str
    key: int
    name: str


@dataclass
class StatsService:
    db: StatsDb
    settings: StatsSettings
    champions: Mapping[str, Champion]  # by Data Dragon id
    items: Mapping[int, str] = field(default_factory=dict)  # item id -> name (items.csv)
    changed: frozenset[str] = frozenset()  # champions changed this patch (no old-patch data)
    opgg: Opgg | None = None  # None: cached data only, never the network
    max_age_hours: float = 72.0  # matchup tables, labels, synergies
    lane_max_age_hours: float = 24.0
    workers: int = 2
    now: Callable[[], datetime] = lambda: datetime.now().astimezone()
    _pool: ThreadPoolExecutor | None = None
    _inflight: dict[tuple[Any, ...], Future[None]] = field(default_factory=dict)
    _ran_at: dict[tuple[Any, ...], float] = field(default_factory=dict)  # key -> monotonic time
    _lock: Lock = field(default_factory=Lock)
    _errors: list[str] = field(default_factory=list)  # since the last reset (one draft)

    @classmethod
    def from_static(
        cls,
        db: StatsDb,
        settings: StatsSettings,
        version: str,
        tables: Mapping[str, Sequence[Row]],
        **kwargs: Any,
    ) -> "StatsService":
        """Champions, item names and this patch's changed champions from the static tables."""
        champions = {
            r["champ_id"]: Champion(r["champ_id"], int(r["key"]), r["name"])
            for r in tables.get("champions.csv", [])
        }
        items = {int(r["item_id"]): r["name"] for r in tables.get("items.csv", [])}
        patch = short_patch(version)
        changed = frozenset(
            r["champ_id"]
            for r in tables.get("champion_meta.csv", [])
            if r.get("last_changed_patch") == patch
        )
        return cls(db, settings, champions, items, changed, **kwargs)

    # ------------------------------------------------------------ lookups

    def by_key(self) -> dict[int, str]:
        return {c.key: c.champ_id for c in self.champions.values()}

    def by_name(self) -> dict[str, str]:
        return {name_key(c.name): c.champ_id for c in self.champions.values()}

    def role_rates(self) -> dict[str, dict[Role, float]]:
        """OP.GG role rates from the newest patch that has them ({} if none yet)."""
        for patch in reversed(self.db.patches()):
            rates = self.db.role_rates(patch)
            if rates:
                return rates
        return {}

    def lane_advantage(
        self, keys: Iterable[tuple[str, str, str]]
    ) -> dict[tuple[str, str, str], str]:
        """OP.GG's lane-advantage label per (role, champ, opp), newest patch first."""
        found = {}
        patches = list(reversed(self.db.patches()))
        for role, champ, opp in keys:
            if role not in {r.value for r in Role}:
                continue
            for patch in patches:
                labels = self.db.labels(patch, Role(role), champ, opp)
                if labels is not None and labels.lane_advantage:
                    found[(role, champ, opp)] = labels.lane_advantage
                    break
        return found

    def lane_stats_stale(self) -> bool:
        fetched = self.db.lane_fetched_at()
        return fetched is None or _hours(self.now() - fetched) >= self.lane_max_age_hours

    # ------------------------------------------------------------ refresh (blocking)

    def refresh_lane_meta(self) -> str:
        """Lane stats and role rates. Returns a one-line summary; raises OpggError."""
        opgg = self._online()
        started = time.monotonic()
        try:
            rows, shape = opgg.lane_meta()
        except OpggError as exc:
            self._log(LANE_META, {"position": "all"}, time.monotonic() - started, error=str(exc))
            raise
        took = time.monotonic() - started
        names = self.by_name()
        known = [(names[name_key(r.name)], r) for r in rows if name_key(r.name) in names]
        unknown = sorted({r.name for r in rows if name_key(r.name) not in names})
        patch = self._learn_patch(rows, names) or self.db.opgg_patch()
        if patch is None:
            raise OpggError("couldn't tell which patch OP.GG's numbers are for")
        stamp = self._stamp()
        self.db.put_lane_meta(patch, known, stamp)
        self._log(LANE_META, {"position": "all"}, took, fingerprint=shape, patch=patch)
        summary = f"lane stats: {len(known)} champion-roles for patch {patch}"
        if unknown:
            summary += f" ({len(unknown)} names not in our static data: {', '.join(unknown[:5])})"
        return summary

    def refresh_pool(
        self, pool: Mapping[Role, Sequence[str]], opponents: int = POOL_OPPONENTS
    ) -> list[str]:
        """Matchup guides for each pool champion against its role's most-played opponents."""
        patch = self.db.opgg_patch()
        done: list[str] = []
        for role, champs in pool.items():
            common = self._most_played(patch, role) if patch else []
            for champ in champs:
                if champ not in self.champions:
                    done.append(f"{champ}: not a known champion id (config player.champ_pool)")
                    continue
                against = [c for c in common if c != champ][:opponents]
                for opp in against:
                    self.guide(role, champ, opp)
                names = ", ".join(self.champions[c].name for c in against) or "none yet"
                done.append(f"{role.value} {self.champions[champ].name} vs {names}")
        return done + [f"error: {e}" for e in self.take_errors()]

    # ------------------------------------------------------------ during a draft (background)

    def prefetch(self, game: GameState) -> None:
        """Queue every call this draft needs that isn't fresh in the database. Non-blocking."""
        if self.opgg is None:
            return
        for role, mine in game.ally.items():
            theirs = game.enemy.get(role)
            if theirs is not None:
                self._submit(
                    ("guide", role, mine.champ_id, theirs.champ_id),
                    self.guide,
                    role,
                    mine.champ_id,
                    theirs.champ_id,
                )
        # Their side of each lane too: my opponent's usual build into me, and every enemy's win
        # rate by game length, so `scaling` is OP.GG's for all ten champions (M15). Mine first.
        roles = sorted(game.enemy, key=lambda r: r is not game.my_role)
        for role in roles:
            theirs, mine = game.enemy[role], game.ally.get(role)
            if mine is not None:
                self._submit(
                    ("guide", role, theirs.champ_id, mine.champ_id),
                    self.guide,
                    role,
                    theirs.champ_id,
                    mine.champ_id,
                )
        for team in (game.ally, game.enemy):
            adc = team.get(Role.BOT)
            if adc is not None and Role.SUPPORT in team:
                self._submit(
                    ("synergy", adc.champ_id), self.synergy, adc.champ_id, Role.BOT, Role.SUPPORT
                )

    def prefetch_tables(self, role: Role, champs: Sequence[str], opponent: str | None) -> None:
        """Pick suggestions: each candidate's full matchup table for this role (one guide each,
        against the locked opponent or the role's most-played champion). Non-blocking."""
        if self.opgg is None:
            return
        patch = self.db.opgg_patch()
        common = self._most_played(patch, role) if patch else []
        for champ in champs:
            vs = opponent or next((c for c in common if c != champ), None)
            if vs is not None:
                self._submit(("guide", role, champ, vs), self.guide, role, champ, vs)

    def prefetch_synergies(self, role: Role, allies: Mapping[Role, str]) -> None:
        """Pick suggestions (M18): each locked ally's synergy table with my role (one call per
        ally covers every candidate). Non-blocking; cached for matchup_max_age_hours."""
        if self.opgg is None:
            return
        for ally_role, champ in allies.items():
            if ally_role is not role:
                self._submit(("synergy", champ, ally_role, role), self.synergy, champ, ally_role,
                             role)  # fmt: skip

    def busy(self) -> bool:
        with self._lock:
            return any(not f.done() for f in self._inflight.values())

    def wait(self, budget_s: float) -> bool:
        """Wait up to budget_s for calls still running. True if none are left."""
        with self._lock:
            running = [f for f in self._inflight.values() if not f.done()]
        if running and budget_s > 0:
            wait_for(running, timeout=budget_s)
        return not self.busy()

    def for_game(self, game: GameState, budget_s: float = 0.0) -> GameStats:
        complete = self.wait(budget_s)
        notice = ""
        errors = self.take_errors()
        stats = game_stats(self.db, game, self.settings, self.changed, self.items)
        if errors and not stats.any:
            notice = f"Stats unavailable ({errors[-1][:90]}); rules and champion notes only."
        elif not stats.any:
            notice = "No stats yet for these champions."
        elif not complete:
            notice = "Some stats were still loading; they'll show in the next update."
        elif errors:
            notice = "Some stats are missing (OP.GG had errors); the rest are shown."
        return dataclasses.replace(stats, notice=notice)

    def take_errors(self) -> list[str]:
        with self._lock:
            errors, self._errors = self._errors, []
        return errors

    def close(self) -> None:
        if self._pool is not None:
            self._pool.shutdown(wait=False, cancel_futures=True)
        close = getattr(self.opgg.transport, "close", None) if self.opgg else None
        if close is not None:
            close()
        self.db.close()

    # ------------------------------------------------------------ single calls

    def guide(self, role: Role, champ: str, opp: str) -> None:
        """One matchup guide: champ's full table for this role, the pair's labels, builds."""
        fetched = self.db.guide_fetched_at(role, champ, opp)
        if fetched is not None and _hours(self.now() - fetched) < self.max_age_hours:
            return
        a, b = self.champions.get(champ), self.champions.get(opp)
        if a is None or b is None:
            return
        args = {
            "position": POSITION[role],
            "my_champion": to_opgg_name(a.name),
            "opponent_champion": to_opgg_name(b.name),
        }
        started = time.monotonic()
        try:
            found = self._online().guide(role, args["my_champion"], args["opponent_champion"])
        except OpggNoData as exc:  # no data for this champion in this role: not an outage
            self._log(GUIDE, args, time.monotonic() - started, error=f"no data: {exc}")
            return
        except OpggError as exc:
            self._log(GUIDE, args, time.monotonic() - started, error=str(exc))
            self._error(str(exc))
            return
        self.db.put_guide(found, champ, opp, self.by_key(), self._stamp())
        self._log(
            GUIDE,
            args,
            time.monotonic() - started,
            fingerprint=found.fingerprint,
            patch=found.patch,
        )

    def synergy(self, champ: str, role: Role, ally_role: Role) -> None:
        fetched = self.db.synergy_fetched_at(champ, role, ally_role)
        if fetched is not None and _hours(self.now() - fetched) < self.max_age_hours:
            return
        a = self.champions.get(champ)
        patch = self.db.opgg_patch()
        if a is None or patch is None:
            return
        args = {"champion": to_opgg_name(a.name), "role": role.value, "ally_role": ally_role.value}
        started = time.monotonic()
        try:
            rows, shape = self._online().synergies(args["champion"], role, ally_role)
        except OpggNoData as exc:
            self._log(SYNERGIES, args, time.monotonic() - started, error=f"no data: {exc}")
            return
        except OpggError as exc:
            self._log(SYNERGIES, args, time.monotonic() - started, error=str(exc))
            self._error(str(exc))
            return
        self.db.put_synergies(patch, champ, role, ally_role, rows, self.by_key(), self._stamp())
        self._log(SYNERGIES, args, time.monotonic() - started, fingerprint=shape)

    # ------------------------------------------------------------ plumbing

    def _online(self) -> Opgg:
        if self.opgg is None:
            raise OpggError("stats are offline (no OP.GG client)")
        return self.opgg

    def _submit(self, key: tuple[Any, ...], fn: Callable[..., None], *args: Any) -> None:
        with self._lock:
            existing = self._inflight.get(key)
            if existing is not None and not existing.done():
                return
            ran = self._ran_at.get(key)
            if ran is not None and time.monotonic() - ran < RETRY_AFTER_S:
                return
            if self._pool is None:
                self._pool = ThreadPoolExecutor(self.workers, thread_name_prefix="opgg")
            self._inflight[key] = self._pool.submit(self._guarded, key, fn, *args)

    def _guarded(self, key: tuple[Any, ...], fn: Callable[..., None], *args: Any) -> None:
        try:
            fn(*args)
        except Exception as exc:  # a background fetch must never take down the watcher
            self._error(f"{type(exc).__name__}: {exc}")
        finally:
            with self._lock:
                self._ran_at[key] = time.monotonic()

    def _learn_patch(self, rows: Sequence[Any], names: Mapping[str, str]) -> str | None:
        """OP.GG's patch, from one matchup guide between the two most-played junglers."""
        junglers = sorted(
            (r for r in rows if r.role is Role.JUNGLE and name_key(r.name) in names),
            key=lambda r: -r.games,
        )
        if len(junglers) < 2:
            return None
        a, b = (names[name_key(r.name)] for r in junglers[:2])
        args = {
            "position": "jungle",
            "my_champion": to_opgg_name(self.champions[a].name),
            "opponent_champion": to_opgg_name(self.champions[b].name),
        }
        started = time.monotonic()
        try:
            found = self._online().guide(
                Role.JUNGLE, args["my_champion"], args["opponent_champion"]
            )
        except OpggError as exc:
            self._log(GUIDE, args, time.monotonic() - started, error=str(exc))
            return None
        self.db.put_guide(found, a, b, self.by_key(), self._stamp())
        self._log(
            GUIDE,
            args,
            time.monotonic() - started,
            fingerprint=found.fingerprint,
            patch=found.patch,
        )
        return found.patch

    def _most_played(self, patch: str, role: Role) -> list[str]:
        rates = self.db.role_rates(patch)
        played = [(c, self.db.lane(patch, role, c)) for c, r in rates.items() if role in r]
        return [c for c, counts in sorted(played, key=lambda x: -(x[1].games if x[1] else 0))]

    def _log(
        self,
        tool: str,
        args: Mapping[str, Any],
        seconds: float,
        error: str = "",
        fingerprint: str = "",
        patch: str = "",
    ) -> None:
        self.db.log_fetch(
            tool,
            args,
            self._stamp(),
            not error,
            error,
            round(seconds * 1000),
            fingerprint,
            patch,
        )

    def _error(self, message: str) -> None:
        with self._lock:
            self._errors.append(message)

    def _stamp(self) -> str:
        return self.now().isoformat(timespec="seconds")


def _hours(delta: Any) -> float:
    return delta.total_seconds() / 3600
