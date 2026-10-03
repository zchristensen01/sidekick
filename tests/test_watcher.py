"""`scout watch`: the state machine, replayed on a sample draft and on fakes."""

import copy
import itertools
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from lcu_fakes import make_champ_select_session

from scout.analysis.role_inference import rates_from_wiki_positions
from scout.data.store import read_csv
from scout.lcu.champselect import ChampionIndex
from scout.lcu.client import LcuError, LcuUnavailable
from scout.lcu.watcher import Watcher, run
from scout.rules.engine import load_rules

ROOT = Path(__file__).resolve().parent.parent
STATIC = {name: read_csv(ROOT / "tests/fixtures/static/16.19.1" / name)
          for name in ("champions.csv", "champion_meta.csv", "summoner_spells.csv")}  # fmt: skip
INDEX = ChampionIndex.from_static("16.19.1", STATIC)
RATES = rates_from_wiki_positions(STATIC["champion_meta.csv"])
RULES = load_rules(ROOT / "scout/rules/league_rules.yaml")
RECORDING = json.loads(
    (ROOT / "tests/fixtures/champselect/sample_1_ranked_solo_jungle.json").read_text(
        encoding="utf-8"
    )
)
NOW = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
JUNGLER, TOPLANER, SMITE = 79, 799, 11  # Gragas (guessed jungle), Ambessa (guessed top)


class Clock:
    def __init__(self) -> None:
        self.t = 0.0

    def __call__(self) -> float:
        return self.t


def make_watcher(knowledge, tmp_path) -> tuple[Watcher, list[str], Clock]:
    messages: list[str] = []
    clock = Clock()
    watcher = Watcher(client=None, knowledge=knowledge, rules=RULES, rates=RATES, index=INDEX,
                      reports_dir=tmp_path, echo=messages.append, clock=clock,
                      now=lambda: NOW)  # fmt: skip
    return watcher, messages, clock


def replay(watcher: Watcher, clock: Clock) -> None:
    for snapshot in RECORDING["snapshots"]:
        clock.t = snapshot["elapsed_s"]
        watcher.process("ChampSelect", snapshot["session"])


def loading_roster(smite_on: int) -> dict:
    enemies = [p["championId"] for p in RECORDING["snapshots"][-1]["session"]["theirTeam"]]
    return {"gameData": {
        "teamOne": [], "teamTwo": [{"championId": k, "selectedPosition": ""} for k in enemies],
        "playerChampionSelections": [
            {"championId": k, "spell1Id": 4, "spell2Id": SMITE if k == smite_on else 14}
            for k in enemies
        ],
    }}  # fmt: skip


def test_no_report_when_picks_lock(knowledge, tmp_path):
    """One report per game, at the loading screen (2026-10-03: never the draft read)."""
    watcher, messages, clock = make_watcher(knowledge, tmp_path)
    views = []
    watcher.on_view = views.append
    replay(watcher, clock)
    assert watcher.state == "final"
    assert not any(m.startswith(("Report", "Final report")) for m in messages)
    assert "Picks locked. The report comes at the loading screen." in messages
    assert list(tmp_path.glob("*.md")) == []  # nothing made yet
    assert views[-1]["screen"] == "status" and views[-1]["state"] == "picks_locked"


def test_the_report_comes_at_the_loading_screen(knowledge, tmp_path):
    """With no AI writer, the rules version is the report, shown at once at loading."""
    watcher, _, clock = make_watcher(knowledge, tmp_path)
    shown = []
    watcher.on_report = lambda title, text: shown.append((title, text))
    replay(watcher, clock)
    assert shown == []
    watcher.process("GameStart", None, loading_roster(smite_on=JUNGLER))
    assert [title for title, _ in shown] == ["Report with roles confirmed (jungle, Jax)"]
    assert shown[0][1].startswith("Sidekick: jungle Jax")
    saved = list(tmp_path.glob("*.md"))
    assert [p.name for p in saved] == ["2026-01-01_120000_jungle_Jax.md"]


def test_loading_screen_confirms_the_jungler(knowledge, tmp_path):
    watcher, messages, clock = make_watcher(knowledge, tmp_path)
    replay(watcher, clock)
    watcher.process("GameStart", None, {"gameData": {}})  # roster not filled in yet
    assert watcher.state == "loading"
    watcher.process("GameStart", None, loading_roster(smite_on=JUNGLER))
    assert "Confirmed at loading: Gragas is their jungle." in messages
    assert watcher.state == "in_game"
    report = next(tmp_path.glob("*.md")).read_text(encoding="utf-8")
    assert report.startswith("# Report with roles confirmed")
    assert "Gragas as their jungle is a guess" not in report


def test_loading_screen_corrects_a_wrong_guess(knowledge, tmp_path):
    watcher, messages, clock = make_watcher(knowledge, tmp_path)
    replay(watcher, clock)
    watcher.process("InProgress", None, loading_roster(smite_on=TOPLANER))
    assert any(m.startswith("Corrected at loading: Ambessa is their jungle, not their")
               for m in messages)  # fmt: skip
    enemy = watcher.live.game.enemy
    assert [p.champ_id for r, p in enemy.items() if r.value == "jungle"] == ["Ambessa"]


def test_game_without_a_roster_keeps_the_guess(knowledge, tmp_path):
    watcher, messages, clock = make_watcher(knowledge, tmp_path)
    replay(watcher, clock)
    watcher.process("InProgress", None, {"gameData": {}})
    assert watcher.state == "in_game"
    assert any("roles stay guessed" in m for m in messages)
    report = next(tmp_path.glob("*.md")).read_text(encoding="utf-8")
    assert report.startswith("# Final report (roles guessed)")  # still one report


def test_dodge_discards_the_report(knowledge, tmp_path):
    watcher, messages, clock = make_watcher(knowledge, tmp_path)
    replay(watcher, clock)
    watcher.process("Matchmaking", None)
    assert messages[-1] == "Champion select ended without a game (Matchmaking)."
    assert list(tmp_path.glob("*.md")) == [] and watcher.state == "idle"


def test_a_trade_after_picks_lock_is_in_the_report(knowledge, tmp_path):
    watcher, messages, clock = make_watcher(knowledge, tmp_path)
    final = make_champ_select_session(phase="FINALIZATION", enemy_champs=(122, 60, 7, 51, 89))
    watcher.process("ChampSelect", final)
    before = {r: p.champ_id for r, p in watcher.live.game.ally.items()}
    traded = copy.deepcopy(final)
    traded["myTeam"][2]["championId"] = 202  # Ahri and Jhin trade
    traded["myTeam"][3]["championId"] = 103
    clock.t = 1.0
    watcher.process("ChampSelect", traded)
    assert not any(m.startswith(("Report", "Updated report")) for m in messages)
    watcher.process("GameStart", None, loading_roster(smite_on=JUNGLER))
    after = {r: p.champ_id for r, p in watcher.live.game.ally.items()}
    assert after != before and sorted(after.values()) == sorted(before.values())
    assert sum(m.startswith(("Final report", "Report with roles confirmed")) for m in messages) == 1


def test_aram_never_gets_a_report(knowledge, tmp_path):
    watcher, messages, clock = make_watcher(knowledge, tmp_path)
    aram = make_champ_select_session(phase="FINALIZATION", enemy_champs=(122, 60, 7, 51, 89),
                                     queue_id=450)  # fmt: skip
    for _ in range(3):
        watcher.process("ChampSelect", aram)
    watcher.process("GameStart", None, loading_roster(smite_on=JUNGLER))
    assert messages == [
        "Champion select started.",
        "No report: ARAM (queue 450) isn't a draft or ranked game; no report.",
    ]
    assert list(tmp_path.glob("*.md")) == []


def test_run_survives_bad_data_and_stops_on_ctrl_c(knowledge, tmp_path):
    watcher, _, _ = make_watcher(knowledge, tmp_path)
    reads = itertools.chain(
        [LcuUnavailable("closed"), KeyError("timer"), "Lobby"], itertools.repeat(None)
    )

    class Client:
        def get(self, path):
            value = next(reads)
            if isinstance(value, Exception):
                raise value
            return value

    watcher.client = Client()
    messages: list[str] = []
    waits = iter(range(3))

    def wait(seconds):
        if next(waits, None) is None:
            raise KeyboardInterrupt

    run(watcher, 1.0, wait=wait, echo=messages.append, error_log=tmp_path / "errors.log")
    assert messages[0] == "Waiting for the League client to open..."
    assert messages[1].startswith("Couldn't read champ select (KeyError")
    assert messages[2] == "Connected to the League client. Waiting for champion select."
    assert messages[-1] == "Stopping."
    assert "KeyError" in (tmp_path / "errors.log").read_text(encoding="utf-8")


def test_run_stops_on_a_certificate_problem(knowledge, tmp_path):
    watcher, _, _ = make_watcher(knowledge, tmp_path)

    class Client:
        def get(self, path):
            raise LcuError("certificate didn't verify")

    watcher.client = Client()
    with pytest.raises(LcuError):
        run(watcher, 1.0, wait=lambda s: None, echo=lambda m: None)
