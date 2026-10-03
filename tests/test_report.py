"""Reports for every role: golden games, always-on sections, warnings, notes, rendering."""

import dataclasses
import shutil
from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner

from scout.analysis.insights import analyze
from scout.cli import app
from scout.model.gamefile import load_game
from scout.model.roles import Role
from scout.report.render import render_text
from scout.report.select import ALWAYS, MAX_ITEMS, ORDER, WIDE_SECTIONS, select
from scout.rules.engine import evaluate, load_rules

REPO_ROOT = Path(__file__).resolve().parent.parent
RULES = load_rules(REPO_ROOT / "scout" / "rules" / "league_rules.yaml")
GAMES = REPO_ROOT / "tests" / "fixtures" / "games"
GOLDEN = sorted((REPO_ROOT / "tests" / "golden").glob("*.yaml"))


def report_for(knowledge, game_name: str, role: Role, notes=()):
    game = load_game(GAMES / f"{game_name}.yaml", set(knowledge.champions))
    insights = analyze(dataclasses.replace(game, my_role=role), knowledge)
    return select(insights, evaluate(RULES, insights), notes)


def shown_rules(report) -> set[str]:
    return {i.source for s in report.sections for i in s.items if ":" not in i.source}


@pytest.mark.parametrize("path", GOLDEN, ids=[p.stem for p in GOLDEN])
def test_golden(path, knowledge):
    golden = yaml.safe_load(path.read_text(encoding="utf-8"))
    report = report_for(knowledge, golden["game"], Role(golden["role"]))
    assert [s.key for s in report.sections] == golden["sections"]
    shown = shown_rules(report)
    assert set(golden["fired"]) <= shown, f"missing: {set(golden['fired']) - shown}"
    assert not shown & set(golden["not_fired"])


def test_two_golden_games_per_role():
    roles = [yaml.safe_load(p.read_text(encoding="utf-8"))["role"] for p in GOLDEN]
    assert all(roles.count(r.value) >= 2 for r in Role)


@pytest.mark.parametrize("role", list(Role))
def test_always_sections_and_order(knowledge, role):
    report = report_for(knowledge, "samira_naut", role)
    keys = [s.key for s in report.sections]
    assert ALWAYS[role] <= set(keys)
    assert keys == [k for k in ORDER[role] if k in keys]
    assert all(s.items for s in report.sections)
    assert all(len(s.items) <= WIDE_SECTIONS.get(s.key, MAX_ITEMS) for s in report.sections)


def test_same_draft_same_report(knowledge):
    first = report_for(knowledge, "teemo_zed_poke", Role.MID)
    assert render_text(first) == render_text(report_for(knowledge, "teemo_zed_poke", Role.MID))


def test_role_guesses_and_unreviewed_traits_are_warned(knowledge):
    report = report_for(knowledge, "unsure_jungler", Role.JUNGLE)
    assert "Gragas as their jungle is a guess (41% sure)." in report.warnings
    assert any("still drafts" in w and "Riot's ratings" in w for w in report.warnings)


def test_your_notes_for_my_matchup(knowledge):
    notes = [
        {"role": "support", "champ_id": "Lulu", "opp_champ_id": "Nautilus", "note": "Hold W."},
        {"role": "support", "champ_id": "Lulu", "opp_champ_id": "Leona", "note": "Not this one."},
    ]
    report = report_for(knowledge, "samira_naut", Role.SUPPORT, notes)
    assert report.your_notes == ["Hold W."]
    assert "YOUR NOTES\n- Hold W." in render_text(report)


def test_render_shows_sources_only_in_debug(knowledge):
    report = report_for(knowledge, "samira_naut", Role.JUNGLE)
    text, debug = render_text(report), render_text(report, debug=True)
    assert text.startswith("Sidekick: jungle Lee Sin (patch 26.19, ranked solo)")
    assert "BEST GANK OPTIONS" in text and "[BOT-KILL-LANE-THEM]" not in text
    assert "[BOT-KILL-LANE-THEM]" in debug


def test_cli_report(scout_home):
    static = REPO_ROOT / "tests" / "fixtures" / "static" / "16.19.1"
    for name in ("champions.csv", "champion_meta.csv"):
        shutil.copy(static / name, scout_home.static_dir("16.19.1") / name)
    shutil.copy(static / "champion_traits.csv", scout_home.manual_dir / "champion_traits.csv")
    game = GAMES / "samira_naut.yaml"
    result = CliRunner().invoke(app, ["report", "--file", str(game), "--role", "support"])
    assert result.exit_code == 0, result.output
    assert result.output.startswith("Sidekick: support Lulu")
