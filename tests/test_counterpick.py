"""Counter-pick verdicts (M9, docs/COUNTERPICK.md): bands, specific counter vs weak patch, pick
order, structural fallback, role uncertainty. Synthetic numbers; no network."""

import dataclasses
import json
from pathlib import Path

import pytest

from scout.analysis.insights import analyze
from scout.analysis.role_inference import rates_from_wiki_positions
from scout.analysis.stats import GameStats, MatchupStat
from scout.counterpick import Bands, label_for, outlook_from_rate, verdict_text
from scout.data.stats_db import Labels
from scout.data.store import read_csv
from scout.lcu.champselect import ChampionIndex, parse_session
from scout.model.gamefile import load_game
from scout.model.roles import Role
from scout.report.render import render_text
from scout.report.select import select
from scout.rules.engine import evaluate, load_rules

ROOT = Path(__file__).resolve().parent.parent
RULES = load_rules(ROOT / "scout/rules/league_rules.yaml")
BANDS = Bands()


def stat(role: Role, rate: float, expected: float, games: int = 4000, opp: str = "Teemo"):
    return MatchupStat(role, "Darius", opp, games, rate, rate, expected, rate - expected,
                       games >= 500, f"{round(rate * 100)}% over {games:,} games", "",
                       Labels("", "", "", ""))  # fmt: skip


def top_game(knowledge, my_turn: int | None = 2, opp_turn: int | None = 5):
    game = load_game(ROOT / "tests/fixtures/games/teemo_zed_poke.yaml", set(knowledge.champions))
    me, opp = game.ally[Role.TOP], game.enemy[Role.TOP]
    return dataclasses.replace(
        game, my_role=Role.TOP,
        ally={**game.ally, Role.TOP: dataclasses.replace(me, pick_turn=my_turn)},
        enemy={**game.enemy, Role.TOP: dataclasses.replace(opp, pick_turn=opp_turn)},
    )  # fmt: skip


@pytest.mark.parametrize(
    ("rate", "outlook"),
    [(0.52, "favorable"), (0.515, "favorable"), (0.50, "even"), (0.485, "even"),
     (0.47, "soft_counter"), (0.465, "soft_counter"), (0.45, "hard_counter")],
)  # fmt: skip
def test_bands(rate, outlook):
    assert outlook_from_rate(rate, BANDS) == outlook


@pytest.mark.parametrize(
    ("outlook", "specific", "after", "label"),
    [("hard_counter", True, True, "counter_picked"), ("hard_counter", True, False, "bad_draw"),
     ("soft_counter", True, None, "bad_draw"), ("soft_counter", False, True, "weak_patch"),
     ("hard_counter", None, True, "bad_draw"), ("favorable", None, False, "you_countered"),
     ("favorable", None, True, "favorable"), ("favorable", None, None, "favorable"),
     ("even", None, True, "even"), ("unknown", None, True, "unknown")],
)  # fmt: skip
def test_labels(outlook, specific, after, label):
    assert label_for(outlook, specific, after) == label


def test_counter_picked_after_me(knowledge):
    """Teemo locked after Darius, 45% for Darius, 3 points worse than expected."""
    stats = GameStats({Role.TOP: stat(Role.TOP, 0.45, 0.48)})
    ins = analyze(top_game(knowledge), knowledge, stats)
    v = ins.counterpick
    assert (v.outlook, v.specific, v.picked_after_me, v.label) == (
        "hard_counter", True, True, "counter_picked")  # fmt: skip
    assert verdict_text(v) == (
        "Counter-picked: Teemo locked after you and is a hard matchup for Darius (game win rate "
        "45% over 4,000 games), 3 points worse than both champions' overall strength "
        "predicts."
    )
    report = select(ins, evaluate(RULES, ins))
    section = next(s for s in report.sections if s.key == "counterpick")
    assert [i.source for i in section.items][:3] == [
        "insight:counterpick", "COUNTER-PICKED-AFTER", "COUNTER-HARD"]  # fmt: skip
    assert section.items[0].numbers == ("45% over 4,000 games",)


def test_same_numbers_but_i_picked_into_it(knowledge):
    stats = GameStats({Role.TOP: stat(Role.TOP, 0.45, 0.48)})
    v = analyze(top_game(knowledge, my_turn=5, opp_turn=2), knowledge, stats).counterpick
    assert v.label == "bad_draw" and v.picked_after_me is False
    assert "You picked into it, so it isn't a deliberate counter." in verdict_text(v)


def test_weak_patch_is_not_a_counter(knowledge):
    """47% but expected 47.5%: Darius is just weak this patch."""
    stats = GameStats({Role.TOP: stat(Role.TOP, 0.47, 0.475)})
    ins = analyze(top_game(knowledge), knowledge, stats)
    assert ins.counterpick.label == "weak_patch" and ins.counterpick.specific is False
    fired = {f.id for f in evaluate(RULES, ins)}
    assert "COUNTER-WEAK-PATCH" in fired and "COUNTER-PICKED-AFTER" not in fired


def test_you_countered_them(knowledge):
    stats = GameStats({Role.TOP: stat(Role.TOP, 0.53, 0.50)})
    ins = analyze(top_game(knowledge, my_turn=6, opp_turn=3), knowledge, stats)
    assert ins.counterpick.label == "you_countered"
    assert "YOU-COUNTERED" in {f.id for f in evaluate(RULES, ins)}


def test_thin_numbers_fall_back_to_champion_notes(knowledge):
    stats = GameStats({Role.TOP: stat(Role.TOP, 0.40, 0.50, games=200)})  # not shown
    v = analyze(top_game(knowledge), knowledge, stats).counterpick
    assert v.source == "structure" and v.specific is None
    assert "ranged_into_melee" in v.flags  # Teemo is ranged into melee Darius
    assert "no reliable numbers; going by champion notes: they're ranged into your melee" in (
        verdict_text(v))  # fmt: skip


def test_no_pick_order_still_gives_an_outlook(knowledge):
    stats = GameStats({Role.TOP: stat(Role.TOP, 0.45, 0.48)})
    v = analyze(top_game(knowledge, None, None), knowledge, stats).counterpick
    assert v.picked_after_me is None and v.outlook == "hard_counter" and v.label == "bad_draw"


def test_unsure_opponent_gets_alternatives(knowledge):
    game = top_game(knowledge)
    teemo = dataclasses.replace(game.enemy[Role.TOP], role_confidence=0.45)
    game = dataclasses.replace(
        game, enemy={**game.enemy, Role.TOP: teemo},
        enemy_role_odds={Role.TOP: [("Teemo", 0.45), ("Zed", 0.35), ("Lux", 0.05)]},
    )  # fmt: skip
    stats = GameStats({Role.TOP: stat(Role.TOP, 0.45, 0.48)},
                      alternatives={"Zed": stat(Role.TOP, 0.53, 0.5, opp="Zed")})  # fmt: skip
    v = analyze(game, knowledge, stats).counterpick
    assert [(a.name, a.outlook) for a in v.alternatives] == [("Zed", "favorable")]
    assert verdict_text(v).endswith(
        "If Zed is your laner instead (35% likely): favorable (game win rate 53% over 4,000 games)."
    )


def test_jungle_verdict_from_the_early_1v1(knowledge):
    game = load_game(ROOT / "tests/fixtures/games/teemo_zed_poke.yaml", set(knowledge.champions))
    ins = analyze(dataclasses.replace(game, my_role=Role.JUNGLE), knowledge)
    assert ins.counterpick.opponent.role is Role.JUNGLE and ins.counterpick.source == "structure"
    text = render_text(select(ins, evaluate(RULES, ins)))
    assert "COUNTER-PICK" in text


def test_recorded_pick_order(knowledge):
    """A recorded draft: Taric (enemy support) and Leona (my pick); who locked first."""
    path = ROOT / "tests/fixtures/champselect/sample_3_ranked_solo_support.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    static = {n: read_csv(ROOT / "tests/fixtures/static/16.19.1" / n)
              for n in ("champions.csv", "champion_meta.csv", "summoner_spells.csv")}  # fmt: skip
    index = ChampionIndex.from_static("16.19.1", static)
    game = parse_session(data["snapshots"][-1]["session"], index,
                         rates_from_wiki_positions(static["champion_meta.csv"]), 420)  # fmt: skip
    me = game.ally[Role.SUPPORT]
    opp = game.enemy[Role.SUPPORT]
    assert me.pick_turn is not None and opp.pick_turn is not None
    v = analyze(game, knowledge).counterpick
    assert v.picked_after_me == (opp.pick_turn > me.pick_turn)
