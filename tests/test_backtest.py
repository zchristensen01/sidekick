"""M20: the collector's per-game records and the backtest that grades every read on them."""

import json
from datetime import UTC, datetime
from pathlib import Path

from scout.data.collector import backtest_record
from scout.data.measure import measure
from scout.data.stats_db import StatsDb
from scout.model.roles import Role
from scout.postgame import backtest as bt
from scout.postgame.grade import grade, grade_outcome, outcome, read_match
from scout.rules.engine import load_rules
from tests.test_measured import FINISHED, FakeRiot, by_key, recorded
from tests.test_postgame import report_claims

ROOT = Path(__file__).resolve().parent.parent
RULES = load_rules(ROOT / "scout" / "rules" / "league_rules.yaml")
NOW = datetime(2026, 10, 4, 12, 0, tzinfo=UTC)


def stored(knowledge) -> dict:
    """The sample game's backtest record, as it comes back out of the database."""
    match, timeline = recorded()
    return json.loads(json.dumps(backtest_record(match, timeline, by_key(knowledge))))


def test_the_record_holds_both_drafts_and_nothing_about_players(knowledge):
    record = stored(knowledge)
    assert set(record["sides"]) == {"100", "200"}
    for side in record["sides"].values():
        assert set(side["draft"]) == {r.value for r in Role}
        assert set(side["outcome"]) >= {"won", "duration_s", "lanes", "gank", "start", "enemies"}
    text = json.dumps(record)
    match, _ = recorded()
    for p in match["info"]["participants"]:
        assert str(p.get("puuid") or "@@") not in text
    assert str(match["info"].get("gameId") or "@@") not in text


def test_a_stored_outcome_grades_like_the_live_check(knowledge):
    match, timeline = recorded()
    _, claims = report_claims(knowledge)
    m = read_match(match, timeline, knowledge.facts("Jax").key, Role.JUNGLE)
    record = stored(knowledge)
    ours = record["sides"][str(m.ours)]["outcome"]
    assert ours == json.loads(json.dumps(outcome(m)))
    live = [(r.claim.id, r.actual, r.hit, r.measure) for r in grade(claims, m)]
    later = [(r.claim.id, r.actual, r.hit, r.measure) for r in grade_outcome(claims, ours)]
    assert live == later


def test_the_collector_stores_one_record_per_game(knowledge):
    from scout.data.collector import Collector

    db = StatsDb(":memory:")
    Collector(FakeRiot(), db, by_key(knowledge), FINISHED, ("16.19",), now=lambda: NOW,
              shuffle=lambda players: None).run(games=2)  # fmt: skip
    games = db.games()
    assert len(games) == 2 and all(g["patch"] == "16.19" and g["sides"] for g in games)
    assert "NA1_" not in repr(games)  # game ids only as a hash, and not in the record


def test_the_backtest_grades_each_side_against_the_baseline(knowledge, tmp_path):
    record = {**stored(knowledge), "patch": "16.19"}
    tally = bt.run([record, {"sides": {}}], knowledge, RULES)
    assert tally.games == 1 and tally.sides == 2
    winners = tally.lines[("kind", "lane_winner")]
    assert winners.claims >= 2 and winners.graded == sum(winners.actual.values())
    for line in tally.lines.values():
        assert line.hits <= line.graded <= line.claims
        if line.graded:
            assert 0 < line.baseline <= 1 and 0 <= line.rate <= 1
    assert any(what == "rule" for what, _ in tally.lines)
    out = tmp_path / "backtest.csv"
    bt.save(out, tally)
    header = out.read_text(encoding="utf-8").splitlines()[0]
    assert header == ",".join(bt.COLUMNS)
    lines = bt.summary(tally, min_graded=1)
    assert lines[0] == "1 games, 2 drafts (each side's) checked."
    assert any("lane_winner: right" in line for line in lines)


def test_scout_backtest_command(scout_home, knowledge, monkeypatch):
    from typer.testing import CliRunner

    import scout.cli

    monkeypatch.setattr(scout.cli, "load_knowledge", lambda paths, version: knowledge)
    empty = CliRunner().invoke(scout.cli.app, ["backtest"])
    assert empty.exit_code == 0 and "No stored games yet" in empty.output
    match, timeline = recorded()
    db = StatsDb(scout_home.stats_db)
    players = measure(match, timeline, by_key(knowledge), FINISHED)
    db.add_game("h1", "16.19", players, "t", stored(knowledge))
    db.close()
    result = CliRunner().invoke(scout.cli.app, ["backtest"])
    assert result.exit_code == 0, result.output
    assert "1 games, 2 drafts" in result.output
    assert (scout_home.history_dir / "backtest.csv").exists()


def test_each_call_carries_its_track_record_to_the_writer(knowledge, tmp_path):
    from dataclasses import replace

    from scout.analysis.insights import analyze
    from scout.data.store import write_csv
    from scout.model.gamefile import load_game
    from scout.postgame.claims import Claim
    from scout.report.builder import build_input
    from scout.report.select import select
    from scout.rules.engine import evaluate

    path = tmp_path / "backtest.csv"
    rows = [("predicted", "lane_winner=us", 200, 120, 0.45),
            ("call", "bot lane_winner=us", 150, 60, 0.5),
            ("predicted", "lane_winner=even", 90, 60, 0.4),  # too few to show
            ("predicted", "threat=fed", 300, 150, 0.5)]  # fmt: skip
    write_csv(path, bt.COLUMNS, [dict(zip(("what", "name", "graded", "hits", "baseline"), r,
                                          strict=True)) for r in rows])  # fmt: skip
    assert bt.load_track(tmp_path / "missing.csv") == {}
    known = replace(knowledge, track=bt.load_track(path))
    claims = [Claim("bot:winner", "lane_winner", "us", "bot"),
              Claim("top:winner", "lane_winner", "us", "top"),
              Claim("mid:winner", "lane_winner", "even", "mid")]  # fmt: skip
    track = bt.track_record(claims, known)
    assert track == [
        {"call": "bot lane won by your team: 500+ gold ahead at 15:00", "right": "40%",
         "usual_result": "50%", "games": "150", "beats_usual": "no"},  # its own lane first
        {"call": "top lane won by your team: 500+ gold ahead at 15:00", "right": "60%",
         "usual_result": "45%", "games": "200", "beats_usual": "yes"},  # every lane
    ]  # fmt: skip

    game = load_game(ROOT / "tests/fixtures/games/postgame_sample.yaml", set(knowledge.champions))
    ins = analyze(game, knowledge)
    report = select(ins, evaluate(RULES, ins))
    assert "track_record" not in build_input(report, ins, knowledge, 120)
    payload = build_input(report, ins, known, 120)
    assert any(t["call"].endswith("gets fed") and t["games"] == "300"
               for t in payload["track_record"])
