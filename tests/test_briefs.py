"""Matchup briefs (M9, docs/KNOWLEDGE.md layer 3): validator, stale detection, use in reports."""

import dataclasses
from pathlib import Path

from scout.analysis.insights import analyze
from scout.data.briefs import BriefContext, parse_briefs, stale, validate_brief, validate_briefs
from scout.data.schemas import MATCHUP_BRIEFS
from scout.model.gamefile import load_game
from scout.model.roles import Role
from scout.report.render import render_text
from scout.report.select import select
from scout.rules.engine import evaluate, load_rules

ROOT = Path(__file__).resolve().parent.parent
RULES = load_rules(ROOT / "scout/rules/league_rules.yaml")
CONTEXT = BriefContext(
    champions=frozenset({"LeeSin", "Elise", "Jhin", "Samira"}),
    ability_numbers={"LeeSin": frozenset({"3"}), "Elise": frozenset({"2"})},
    ability_names={"LeeSin": frozenset({"Sonic Wave"}), "Elise": frozenset({"Cocoon"})},
    item_names=frozenset({"Eclipse"}),
    lane_advantage={("jungle", "LeeSin", "Elise"): "them"},
)


def row(**changes: str) -> dict[str, str]:
    base = {
        "role": "jungle", "champ_id": "LeeSin", "opp_champ_id": "Elise",
        "levels_1_3": "Unfavored: her Cocoon wins early skirmishes; consider a full clear.",
        "levels_3_6": "Look for counter-ganks where she shows.",
        "after_6": "Your ultimate can turn a fight she starts.",
        "first_item": "You catch up once both have an item.",
        "trade_pattern": "Fight when Cocoon is down.",
        "jungle_ask": "Ask mid for priority before contesting scuttle.",
        "reviewed": "n", "reviewed_patch": "", "source": "claude-code", "notes": "",
    }  # fmt: skip
    base.update(changes)
    return {c: base[c] for c in MATCHUP_BRIEFS}


def test_a_good_brief_passes():
    assert validate_brief(row(), CONTEXT) == []


def test_brief_problems():
    def problems(**changes: str) -> list[str]:
        return validate_brief(row(**changes), CONTEXT)

    assert problems(levels_1_3="You win early.") == [
        "levels_1_3 must start with Favored:, Even: or Unfavored:"]  # fmt: skip
    assert problems(levels_1_3="Favored: you win early.") == [
        "levels_1_3 contradicts OP.GG, which gives Elise the early lane"]  # fmt: skip
    assert problems(after_6="Your ult does 400 damage.") == [
        "after_6 has numbers not in either kit: 400"]  # fmt: skip
    assert problems(after_6="Fight at level 6 or after 3 Cocoon hits, and 2 spiderlings.") == []
    assert problems(first_item="Once she has Eclipse she wins.") == [
        "first_item names items (Eclipse); say it in general terms"]  # fmt: skip
    assert problems(trade_pattern="x" * 241) == ["trade_pattern is longer than 240 characters"]
    assert problems(jungle_ask="") == ["jungle_ask is empty"]
    assert problems(reviewed="y") == ["reviewed=y needs reviewed_patch"]
    assert problems(source="robot") == ["source must be one of claude-code, llm, owner"]
    assert problems(opp_champ_id="Nobody") == ["unknown champion 'Nobody'"]


def test_duplicates_are_named():
    found = validate_briefs([row(), row()], CONTEXT)
    assert found == ["LeeSin vs Elise (jungle): duplicate row"]


def test_parse_skips_broken_rows():
    briefs = parse_briefs([row(), row(champ_id="Jhin", role="nowhere")])
    assert list(briefs) == [("jungle", "LeeSin", "Elise")]
    b = briefs[("jungle", "LeeSin", "Elise")]
    assert b.lead == "them"
    assert b.early == "her Cocoon wins early skirmishes; consider a full clear."


def test_stale_briefs():
    rows = [row()]
    assert stale(rows, {}, {("jungle", "LeeSin", "Elise"): "them"}) == []
    assert stale(rows, {}, {("jungle", "LeeSin", "Elise"): "us"}) == [
        ("LeeSin", "LeeSin vs Elise (jungle): OP.GG's lane advantage is now us")]  # fmt: skip
    assert stale(rows, {"Elise": "abilities changed"}, {}) == [
        ("LeeSin", "LeeSin vs Elise (jungle): Elise abilities changed")]  # fmt: skip


def test_the_report_uses_my_matchup_brief(knowledge):
    brief = parse_briefs([row()])
    game = load_game(ROOT / "tests/fixtures/games/samira_naut.yaml", set(knowledge.champions))
    with_brief = dataclasses.replace(knowledge, briefs=brief)
    ins = analyze(dataclasses.replace(game, my_role=Role.JUNGLE), with_brief)
    assert ins.brief is not None
    report = select(ins, evaluate(RULES, ins))
    jungler = next(s for s in report.sections if s.key == "enemy_jungler")
    sources = [i.source for i in jungler.items]
    assert sources[0] == "brief:jungle:LeeSin:Elise"
    assert jungler.items[0].text.startswith(
        "Levels 1-3: her Cocoon wins early skirmishes; consider a full clear. Levels 3-6:")
    assert jungler.items[0].confidence == "med"  # a draft
    text = " ".join(render_text(report).split())
    assert "The matchup brief for Lee Sin vs Elise is a draft, not yet reviewed" in text


def test_a_laner_brief_replaces_the_computed_timeline(knowledge):
    brief = parse_briefs([row(role="bot", champ_id="Jhin", opp_champ_id="Samira",
                              levels_1_3="Unfavored: their all-in wins early.")])  # fmt: skip
    game = load_game(ROOT / "tests/fixtures/games/samira_naut.yaml", set(knowledge.champions))
    ins = analyze(dataclasses.replace(game, my_role=Role.BOT),
                  dataclasses.replace(knowledge, briefs=brief))  # fmt: skip
    report = select(ins, evaluate(RULES, ins))
    lane = next(s for s in report.sections if s.key == "your_lane")
    sources = {i.source for i in lane.items}
    assert "brief:bot:Jhin:Samira" in sources and "insight:lane_timeline" not in sources
    jungle = next(s for s in report.sections if s.key == "jungle")
    assert any(i.text.startswith("Ask your jungler: Ask mid") for i in jungle.items)


def test_briefs_are_only_appended(tmp_path):
    import pytest

    from scout.data.briefs import append_briefs
    from scout.data.store import read_csv

    path = tmp_path / "matchup_briefs.csv"
    append_briefs(path, [row()])
    append_briefs(path, [row(opp_champ_id="Jhin")])
    assert [r["opp_champ_id"] for r in read_csv(path)] == ["Elise", "Jhin"]
    with pytest.raises(ValueError, match="already in matchup_briefs.csv: LeeSin vs Elise"):
        append_briefs(path, [row()])
