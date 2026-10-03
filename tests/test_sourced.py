"""Sourced champion values (M15): Riot's ratings and text and the LoL Wiki's mechanics in place
of drafted notes, OP.GG's game-length data for scaling. Recorded data only."""

import dataclasses
from pathlib import Path

import pytest
from test_stats import FakeOpgg, make_service

from scout.analysis import stats as st
from scout.analysis.insights import analyze
from scout.data.sourced import apply
from scout.model.champ import Traits
from scout.model.gamefile import load_game
from scout.model.roles import Role

ROOT = Path(__file__).resolve().parent.parent
DRAFT = Traits(early=2, engage=1, cc=0, escape=3, scaling=2, frontline=0,
               tags=frozenset({"airborne", "poke", "stealth"}), source="llm")  # fmt: skip
RIOT = {"cc": 3, "mobility": 1, "durability": 2}


def test_riot_and_wiki_replace_drafted_values():
    t = apply(DRAFT, frozenset({"pull", "stun"}), RIOT, ["Throws a hook."])
    assert (t.cc, t.escape, t.frontline) == (3, 0, 2)  # Low mobility and no dash or blink: 0
    assert t.tags == {"airborne", "poke"}  # pull is airborne (wiki); no stealth on the wiki
    assert t.source_of("cc") == "riot" and t.source_of("escape") == "riot+wiki"
    assert t.source_of("tag:airborne") == "wiki" and t.source_of("tag:poke") == "llm"
    assert t.source_of("early") == "llm" and t.early == 2  # no source yet: stays drafted
    with_blink = apply(DRAFT, frozenset({"blink"}), RIOT, [])
    assert with_blink.escape == 1 and with_blink.source_of("escape") == "riot"
    assert "airborne" not in with_blink.tags


def test_needs_airborne_comes_from_riots_text():
    yasuo = apply(None, frozenset(), {}, ["Blinks to an Airborne enemy champion, dealing..."])
    assert yasuo.tags == {"needs_airborne"} and yasuo.source_of("tag:needs_airborne") == "riot"
    knocker = apply(Traits(tags=frozenset({"needs_airborne"}), source="llm"), frozenset(), {},
                    ["At 2 stacks, fires a whirlwind that knocks Airborne."])  # fmt: skip
    assert "needs_airborne" not in knocker.tags


def test_owners_own_row_wins_and_nothing_means_nothing():
    mine = dataclasses.replace(DRAFT, source="owner")
    kept = apply(mine, frozenset({"dash"}), RIOT, [])
    assert (kept.cc, kept.escape) == (0, 3) and kept.source_of("cc") == "owner"
    assert apply(None, frozenset(), {}, []) is None


def test_knowledge_uses_the_sources(knowledge):
    vex, sivir = knowledge.facts("Vex"), knowledge.facts("Sivir")
    assert vex.traits.escape == 2 and "dash" in vex.mechanics  # drafted said 0: the wiki says dash
    assert sivir.traits.escape == 0 and not sivir.mechanics & {"dash", "blink"}
    assert dict(sivir.ratings)["mobility"] == 1
    assert "airborne" in knowledge.facts("Lulu").traits.tags  # Wild Growth: wiki Knockup


@pytest.mark.parametrize("index, level", [(10.5, 3), (6.0, 3), (5.9, 2), (-2.9, 2), (-3.0, 1),
                                          (-5.1, 1), (-6.0, 0), (-7.8, 0)])  # fmt: skip
def test_scaling_levels(index, level):
    assert st.scaling_level(index) == level


def test_opgg_game_length_sets_scaling(knowledge):
    g = load_game(ROOT / "tests/fixtures/games/samira_naut.yaml", set(knowledge.champions))
    stats = st.GameStats(scaling={"Jhin": 10.5, "Yasuo": -7.8},
                         lengths={"Jhin": (0.448, 0.553), "Yasuo": (0.56, 0.48)})  # fmt: skip
    ins = analyze(g, knowledge, stats)
    jhin, yasuo = ins.lineup.us[Role.BOT], ins.lineup.them[Role.MID]
    assert (jhin.scaling, yasuo.scaling) == (3, 0)
    assert jhin.source_of("scaling") == "opgg"
    assert jhin.scaling_note == "OP.GG: 45% of games under 25 minutes, 55% of games past 35"
    garen = ins.lineup.us[Role.TOP]
    assert garen.source_of("scaling") != "opgg"  # no data for Garen: the drafted note


def test_the_draft_fetch_covers_every_enemy(knowledge):
    g = load_game(ROOT / "tests/fixtures/games/samira_naut.yaml", set(knowledge.champions))
    server = FakeOpgg()
    service = make_service(server)
    service.prefetch(g)
    service.wait(30)
    asked = {a["my_champion"] for t, a in server.calls if t == "lol_get_lane_matchup_guide"}
    for pick in g.enemy.values():
        name = knowledge.facts(pick.champ_id).name.upper().replace(" ", "_").replace("'", "")
        assert name in {champ.replace("'", "") for champ in asked}, name
    service.close()


def test_every_game_fact_is_cited(repo_paths):
    from scout.data.schemas import GAME_FACTS
    from scout.data.store import read_csv

    path = repo_paths.manual_dir / "game_facts.csv"
    rows = read_csv(path)
    assert rows and tuple(rows[0]) == GAME_FACTS
    for row in rows:
        assert row["source"] and row["source_url"].startswith("https://"), row["fact_id"]
        assert row["patch"] and row["checked_on"], row["fact_id"]
        assert row["source_url"].startswith(("https://www.leagueoflegends.com/",
                                             "https://wiki.leagueoflegends.com/")), row["fact_id"]


def test_game_facts_reach_the_jungler_and_the_writer(scout_home, repo_paths, knowledge):
    import shutil

    from scout.data.store import load_knowledge, read_csv
    from scout.report.builder import build_input
    from scout.report.select import select
    from scout.rules.engine import evaluate, load_rules

    shutil.copy(repo_paths.manual_dir / "game_facts.csv", scout_home.manual_dir)
    loaded = load_knowledge(scout_home, "16.19.1")
    assert [f["fact_id"] for f in loaded.facts_about("role_quest", "top")] == ["quest_top"]
    facts = dataclasses.replace(knowledge, game_facts=loaded.game_facts)
    g = load_game(ROOT / "tests/fixtures/games/samira_naut.yaml", set(knowledge.champions))
    ins = analyze(dataclasses.replace(g, my_role=Role.JUNGLE), facts)
    report = select(ins, evaluate(load_rules(ROOT / "scout/rules/league_rules.yaml"), ins))
    start = next(s for s in report.sections if s.key == "start_objectives")
    assert any(i.source == "fact:game:objective" and "Baron Nashor spawns at 20:00" in i.text
               for i in start.items)  # fmt: skip
    payload = build_input(report, ins, facts, 150)
    assert any("Primal Smite" in f["text"] for f in payload["game_facts"])  # my role's quest
    assert not any("Bounty of Worlds" in f["text"] for f in payload["game_facts"])
    assert read_csv(scout_home.manual_dir / "game_facts.csv")


def test_an_off_role_pick_is_named_and_the_ai_may_reason_labelled(knowledge):
    """M19: Jinx top has no data; the report says so and the writer may add its own read,
    which must start with "No data; AI read:" and cite `reasoning`."""
    from scout.report.builder import build_input
    from scout.report.select import select as select_report
    from scout.report.validator import Line as WrittenLine
    from scout.report.validator import Written, WrittenSection, validate
    from scout.rules.engine import evaluate, load_rules

    g = load_game(ROOT / "tests/fixtures/games/samira_naut.yaml", set(knowledge.champions))
    enemy = {**g.enemy, Role.TOP: dataclasses.replace(g.enemy[Role.TOP], champ_id="Jinx")}
    g = dataclasses.replace(g, enemy=enemy, my_role=Role.TOP)
    stats = st.GameStats(role_shares={"Jinx": {Role.BOT: 0.95, Role.TOP: 0.02},
                                      "Garen": {Role.TOP: 0.9}})  # fmt: skip
    ins = analyze(g, knowledge, stats)
    jinx = ins.lineup.them[Role.TOP]
    assert jinx.off_role and jinx.role_share == 0.02
    assert not ins.lineup.us[Role.TOP].off_role
    report = select_report(ins, evaluate(load_rules(ROOT / "scout/rules/league_rules.yaml"), ins))
    assert any(w.startswith("No data for Jinx top: OP.GG has 2% of Jinx's games there")
               for w in report.warnings)  # fmt: skip
    payload = build_input(report, ins, knowledge, 120)
    assert payload["facts"]["Jinx"]["off_role"] and payload["facts"]["Jinx"]["no_data"]
    key = report.sections[0].key

    def check(text: str, sources: tuple[str, ...]) -> list[str]:
        written = Written((WrittenSection(key, (WrittenLine(text, sources),)),))
        return [p for p in validate(written, payload) if "words" not in p and "missing" not in p]

    labelled = "No data; AI read: her rockets out-range you, so trade short."
    assert check(labelled, ("reasoning",)) == []
    unlabelled = check("Her rockets out-range you.", ("reasoning",))
    assert any("doesn't start with" in p for p in unlabelled)
    plain = analyze(g, knowledge)  # no OP.GG role shares: no claim either way
    assert not plain.lineup.them[Role.TOP].off_role
