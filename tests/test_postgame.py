"""The post-game check (M10): claims saved with the final report, graded against a recorded,
scrubbed Match-V5 game (a made-up red-side Jax game), history and accuracy files,
`scout postgame`, and the automatic check after a game. No network."""

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from scout.analysis.insights import analyze
from scout.model.gamefile import load_game
from scout.model.roles import Role
from scout.postgame import claims as claim_files
from scout.postgame import history
from scout.postgame.check import check, match_id, pending, record, summary
from scout.postgame.grade import MatchError, grade, read_match
from scout.report.select import select
from scout.rules.engine import evaluate, load_rules

ROOT = Path(__file__).resolve().parent.parent
FIXTURE = ROOT / "tests" / "fixtures" / "postgame"
RULES = load_rules(ROOT / "scout" / "rules" / "league_rules.yaml")
NOW = datetime(2026, 10, 3, 12, 0, tzinfo=UTC)


def recorded() -> tuple[dict, dict]:
    return (json.loads((FIXTURE / "match.json").read_text(encoding="utf-8")),
            json.loads((FIXTURE / "timeline.json").read_text(encoding="utf-8")))  # fmt: skip


def report_claims(knowledge):
    game = load_game(ROOT / "tests/fixtures/games/postgame_sample.yaml", set(knowledge.champions))
    ins = analyze(game, knowledge)
    fired = evaluate(RULES, ins)
    report = select(ins, fired)
    shown = {i.source for s in report.sections for i in s.items}
    return game, claim_files.claims_from(ins, fired, shown)


class FakeRiot:
    platform = "na1"

    def __init__(self, published: bool = True) -> None:
        self.published, self.asked = published, []

    def match(self, found):
        self.asked.append(found)
        return recorded()[0] if self.published else {}

    def timeline(self, found):
        return recorded()[1]


def test_the_fixture_has_no_identifiers():
    text = (FIXTURE / "match.json").read_text() + (FIXTURE / "timeline.json").read_text()
    for field in ("puuid", "riotIdGameName", "summonerName", "summonerId"):
        assert field not in text


def test_claims_cover_the_review_table(knowledge):
    _, claims = report_claims(knowledge)
    kinds = {c.kind for c in claims}
    assert {"lane_winner", "volatility", "gank_lane", "threat"} <= kinds
    bot = next(c for c in claims if c.id == "bot:winner")
    assert bot.lane == "bot" and set(bot.inputs) >= {"prio", "fight", "volatility", "label"}


def test_grading_the_recorded_game(knowledge):
    game, claims = report_claims(knowledge)
    match, timeline = recorded()
    m = read_match(match, timeline, knowledge.facts("Jax").key, Role.JUNGLE)
    assert m.ours == 200 and not m.won and m.duration_s == 1586
    assert m.fountain["us"][0] > m.fountain["them"][0]  # red spawns top right
    results = {r.claim.id: r for r in grade(claims, m)}
    top = results["top:winner"]
    assert top.actual == "us" and top.measure == "gold difference at 15: +1,805"
    assert results["bot:volatility"].measure == "11 deaths in this lane before 14:00"
    assert results["bot:volatility"].actual == "high"
    gank = results["jungle:first_gank"]
    assert gank.actual == "bot" and "minute 3" in gank.measure
    threat = next(r for r in results.values() if r.claim.kind == "threat")
    assert threat.actual == "not fed" and threat.hit is False  # Camille: 2 kills by 15
    karma = grade([claim_files.Claim("threat:Karma", "threat", "fed", subject="Karma")], m)[0]
    assert karma.actual == "fed" and karma.hit is True  # 8 kills by 15
    lines = summary(list(results.values()))
    assert lines[0].startswith("Post-game check: ") and "predictions held" in lines[0]


def test_wrong_game_or_no_match_yet(knowledge):
    match, timeline = recorded()
    with pytest.raises(MatchError, match="isn't in this match"):
        read_match(match, timeline, knowledge.facts("Ahri").key, Role.MID)
    assert match_id("na1", 5123) == "NA1_5123"


def test_check_record_and_accuracy(knowledge, tmp_path):
    game, claims = report_claims(knowledge)
    path = tmp_path / "reports" / "2026-01-01_jungle_Jax.json"
    claim_files.save(path, game, 5123, claims, NOW.isoformat())
    assert pending(tmp_path / "reports") == [path]
    saved = claim_files.load(path)
    with pytest.raises(MatchError, match="hasn't published"):
        check(saved, FakeRiot(published=False), knowledge, "na1")
    riot = FakeRiot()
    results = check(saved, riot, knowledge, "na1")
    assert riot.asked == ["NA1_5123"]  # the game id, no player lookup
    folder = tmp_path / "history"
    record(folder, saved, results, NOW)
    assert pending(tmp_path / "reports") == []  # graded
    rows = (folder / "postgame.csv").read_text(encoding="utf-8").splitlines()
    assert len(rows) == len(results) + 1 and rows[0].startswith("graded_at,report,patch")
    accuracy = {(r["what"], r["name"]): r for r in history.rebuild_accuracy(folder)}
    assert accuracy[("kind", "threat")]["hit_rate"] == "0.00"  # Camille wasn't fed
    assert any(what == "rule" for what, _ in accuracy)


def test_scout_postgame_command(scout_home, knowledge, monkeypatch):
    from typer.testing import CliRunner

    import scout.cli

    game, claims = report_claims(knowledge)
    reports = scout_home.root / "reports"
    claim_files.save(reports / "2026-01-01_jungle_Jax.json", game, 5123, claims, "x")
    monkeypatch.setenv("RIOT_API_KEY", "RGAPI-test")
    monkeypatch.setattr(scout.cli, "RiotApi", lambda *a, **k: type("R", (FakeRiot,), {
        "close": lambda self: None})())  # fmt: skip
    monkeypatch.setattr(scout.cli, "load_knowledge", lambda paths, version: knowledge)
    result = CliRunner().invoke(scout.cli.app, ["postgame"], input="Dodge the Q at level 2\n")
    assert result.exit_code == 0, result.output
    assert "Post-game check:" in result.output
    notes = (scout_home.manual_dir / "matchup_notes.csv").read_text(encoding="utf-8")
    assert "jungle,Jax,Ambessa,Dodge the Q at level 2," in notes
    again = CliRunner().invoke(scout.cli.app, ["postgame"])
    assert "Nothing to check" in again.output


def test_watch_saves_claims_and_checks_after_the_game(knowledge, tmp_path):
    from test_watcher import loading_roster, make_watcher, replay

    watcher, messages, clock = make_watcher(knowledge, tmp_path)
    watcher.write_in_background = False
    watcher.riot = FakeRiot(published=False)  # this replay isn't the sample match
    watcher.history_dir = tmp_path / "history"
    watcher.postgame_waits_s = (0,)
    watcher.account_name = lambda: "Player#NA1"
    replay(watcher, clock)
    roster = loading_roster(smite_on=154)
    roster["gameData"]["gameId"] = 4242
    watcher.process("GameStart", None, roster)
    claims_file = next(p for p in tmp_path.glob("*.json") if not p.name.endswith(".view.json"))
    saved = claim_files.load(claims_file)
    assert saved.game_id == 4242 and saved.claims
    screen = json.loads(claims_file.with_name(claims_file.stem + ".view.json").read_text(
        encoding="utf-8"))  # M23: the final screen is kept for History, next to the report
    assert screen["view"]["phase"] == "final" and screen["meta"]["account"] == "Player#NA1"
    watcher.process("EndOfGame", None, {"gameData": {}})
    assert watcher.riot.asked == ["NA1_4242"]
    assert any("wasn't published in time" in m for m in messages)
