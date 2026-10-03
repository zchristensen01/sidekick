"""Collected match data (docs/MATCH_DATA.md): the owner's PC only, more figures per game,
per-matchup totals, a cap per patch, older patches dropped, and each own game kept for review."""

import json
from datetime import UTC, datetime

import pytest
from test_measured import FINISHED, FakeRiot, by_key, recorded

from scout.data import collector as collector_module
from scout.data.collector import Collector
from scout.data.measure import measure
from scout.data.stats_db import StatsDb
from scout.model.roles import Role

NOW = datetime(2026, 1, 15, 12, 0, tzinfo=UTC)


def figures(knowledge) -> dict[tuple[str, Role], object]:
    match, timeline = recorded()
    return {(p.champ_id, p.role): p for p in measure(match, timeline, by_key(knowledge), FINISHED)}


def test_more_figures_from_each_game(knowledge):
    found = figures(knowledge)
    jungler = found[("Ambessa", Role.JUNGLE)]
    assert jungler.opp == "Jax"
    assert {k: jungler.figures[k] for k in ("gank_10", "dragons_20", "herald_20",
                                            "first_dragon")} == {
        "gank_10": 1.0, "dragons_20": 2, "herald_20": 1.0, "first_dragon": 1.0}  # fmt: skip
    assert jungler.figures["first_gank_s"] == pytest.approx(196.573)
    assert found[("Jax", Role.JUNGLE)].figures["grubs_20"] == 3
    adc = found[("MissFortune", Role.BOT)]
    assert adc.figures["first_blood"] == 1.0 and adc.figures["plates_14"] == 4
    assert adc.figures["level2_first"] == 1.0 and "gank_10" not in adc.figures
    assert found[("Ezreal", Role.BOT)].figures["level2_first"] == 0.0
    assert found[("Camille", Role.TOP)].figures["solo_kills_14"] == 2
    assert {p.team for p in found.values()} == {100, 200}


def test_matchups_are_counted_and_older_patches_dropped(knowledge):
    db = StatsDb(":memory:")
    players = list(figures(knowledge).values())
    db.add_game("a", "16.19", players, "2026-01-15T10:00:00+00:00")
    db.add_game("b", "16.17", players, "2026-01-01T10:00:00+00:00")  # an old patch
    db.add_game("c", "16.16", [], "2025-12-01T10:00:00+00:00")  # an old "already counted" mark
    pairs = db.measured_matchups("16.19")
    assert pairs[("MissFortune", Role.BOT, "Ezreal")]["win"][0] == 1
    assert "plates_14" not in pairs[("MissFortune", Role.BOT, "Ezreal")]  # matchup metrics only
    done = db.prune(("16.19", "16.18"), "2025-12-15T00:00:00+00:00")
    assert done["measured"] > 0 and done["measured_matchups"] > 0
    assert db.measured("16.17") == {} and db.measured_matchups("16.17") == {}
    assert db.measured("16.19") != {}
    assert db.seen("b") and not db.seen("c")  # recent marks stay: no re-download within 30 days


def test_collecting_stops_at_the_patch_target(knowledge, monkeypatch):
    monkeypatch.setattr(collector_module, "PATCH_TARGET", 2)
    db = StatsDb(":memory:")
    c = Collector(FakeRiot(), db, by_key(knowledge), FINISHED, ("16.19", "16.18"),
                  now=lambda: NOW, shuffle=lambda players: None)  # fmt: skip
    first = c.run(games=10)
    assert first.added == 2 and first.full == "16.19"
    again = c.run(games=10)
    assert again.added == 0 and "has its 2 games" in again.line()
    record = db.games()[0]
    assert record["tier"] == "CHALLENGER"  # the ladder tier the game was found through


def test_collect_is_for_the_owners_pc(scout_home, monkeypatch):
    from typer.testing import CliRunner

    import scout.cli

    monkeypatch.setenv("RIOT_API_KEY", "RGAPI-test")
    result = CliRunner().invoke(scout.cli.app, ["collect", "--games", "1"])
    assert result.exit_code == 1 and "only on the owner's PC" in result.output
    config = scout_home.config_file
    assert "owner: false" in config.read_text(encoding="utf-8")


def test_config_owner_flag(tmp_path, example_config_path):
    from scout.config import ConfigError, load_config

    text = example_config_path.read_text(encoding="utf-8")
    assert load_config(example_config_path).owner is False
    path = tmp_path / "config.yaml"
    path.write_text(text.replace("owner: false", "owner: true"), encoding="utf-8")
    assert load_config(path).owner is True
    path.write_text(text.replace("owner: false", "owner: maybe"), encoding="utf-8")
    with pytest.raises(ConfigError, match="owner"):
        load_config(path)


def test_your_own_game_is_kept_for_the_review(knowledge, tmp_path):
    from test_postgame import FakeRiot as PostgameRiot
    from test_postgame import report_claims

    from scout.postgame import claims as claim_files
    from scout.postgame.check import check, pending, review_path

    game, claims = report_claims(knowledge)
    path = tmp_path / "reports" / "2026-01-01_jungle_Jax.json"
    claim_files.save(path, game, 5123, claims, NOW.isoformat())
    saved = claim_files.load(path)
    results = check(saved, PostgameRiot(), knowledge, "na1")
    kept = json.loads(review_path(path).read_text(encoding="utf-8"))
    assert kept["my_champion"] == "Jax" and kept["lane_opponent"] == "Ambessa"
    assert len(kept["players"]) == 10
    me = next(p for p in kept["players"] if p["champion"] == "Jax")
    assert me["side"] == "us" and "gank_10" in me["figures"]
    assert kept["outcome"]["lanes"] and len(kept["claims"]) == len(results)
    assert "puuid" not in json.dumps(kept) and "Name" not in json.dumps(kept)  # no player names
    assert pending(tmp_path / "reports") == [path]  # the review file isn't taken for claims
