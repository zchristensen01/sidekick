"""The rules file and engine (docs/RULES.md): validation, every rule's own tests, evaluation."""

from pathlib import Path

import pytest
import yaml

from scout.analysis.insights import analyze
from scout.model.gamefile import load_game
from scout.model.roles import Lane, Role
from scout.rules.context import SCHEMA, contexts
from scout.rules.engine import (
    OPS,
    RulesError,
    _check,
    conflicts,
    evaluate,
    load_rules,
    matches,
    rule_test_values,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
RULES = load_rules(REPO_ROOT / "scout" / "rules" / "league_rules.yaml")
GAMES = sorted((REPO_ROOT / "tests" / "fixtures" / "games").glob("*.yaml"))


@pytest.mark.parametrize("rule", RULES, ids=[r.id for r in RULES])
def test_rule_fires_on_its_own_example(rule):
    assert matches(rule, rule_test_values(rule, "fires")), "tests.fires doesn't fire"
    assert not matches(rule, rule_test_values(rule, "not")), "tests.not fires"


def test_missing_values_never_match():
    for op in OPS:
        assert _check(None, op, [1] if op in ("in", "not_in", "has_any") else 1) is False
    assert _check(frozenset({"poke"}), "lacks", "peel") is True
    assert _check(frozenset({"poke"}), "has_any", ["peel", "poke"]) is True
    assert _check("melee", ">=", 3) is False  # type mismatch is just false


def write_rules(tmp_path, rules: list[dict]) -> Path:
    path = tmp_path / "rules.yaml"
    path.write_text(yaml.safe_dump({"rules": rules}), encoding="utf-8")
    return path


GOOD = {
    "id": "TEST-RULE", "scope": "lane", "section": "your_lane", "confidence": "high",
    "when": [["state.verdict", "==", "losing"]], "say": "{lane} loses.",
    "tests": {"fires": {"state.verdict": "losing"}, "not": {"state.verdict": "even"}},
}  # fmt: skip


@pytest.mark.parametrize(
    ("change", "problem"),
    [
        ({"id": "lowercase"}, "UPPER-KEBAB"),
        ({"scope": "jungle"}, "unknown scope"),
        ({"section": "gank_second"}, "unknown section"),
        ({"section": {"jungle": "gank_first"}}, "needs a `default`"),
        ({"audience": ["adc"]}, "audience must be roles"),
        ({"audience": "their_lane"}, "only for champ and ally"),
        ({"when": [["state.verdict", "~=", "losing"]]}, "unknown op"),
        ({"when": [["them.jg.early", "<=", 1]]}, "isn't available in lane scope"),
        ({"when": []}, "at least one"),
        ({"say": "{name} loses."}, "placeholder {name}"),
        ({"tests": {"fires": {}}}, "needs a `tests` block"),
        ({"tests": {"fires": {"nope": 1}, "not": {}}}, "tests.fires path 'nope'"),
        ({"excludes": ["NOT-A-RULE"]}, "excludes unknown id"),
        ({"priority": 101}, "priority must be"),
        ({"colour": "red"}, "unknown key"),
    ],
)
def test_invalid_rules_are_refused(tmp_path, change, problem):
    with pytest.raises(RulesError, match=problem.replace("{", r"\{").replace("}", r"\}")):
        load_rules(write_rules(tmp_path, [GOOD | change]))


def test_duplicate_ids_are_refused(tmp_path):
    with pytest.raises(RulesError, match="duplicate id TEST-RULE"):
        load_rules(write_rules(tmp_path, [GOOD, GOOD]))


def test_every_path_a_builder_fills_is_in_the_schema(knowledge):
    for path in GAMES:
        insights = analyze(load_game(path, set(knowledge.champions)), knowledge)
        for context in contexts(insights):
            assert set(context.values) <= SCHEMA[context.scope], context.scope


def test_audiences(knowledge):
    game = load_game(
        REPO_ROOT / "tests/fixtures/games/teemo_zed_poke.yaml", set(knowledge.champions)
    )
    fired = evaluate(RULES, analyze(game, knowledge))
    by_id = {}
    for f in fired:
        by_id.setdefault(f.id, []).append(f)
    # Lane rules: the lane's players and the jungler only.
    ranged = by_id["TOP-RANGED-INTO-US"][0]
    assert ranged.lane is Lane.TOP and ranged.audience == {Role.TOP, Role.JUNGLE}
    # Champion rules marked their_lane: that champion's lane opponents and the jungler.
    no_dash = next(f for f in by_id["CHAMP-NO-DASH-CARRY"] if f.subject == "Lux")
    assert no_dash.audience == {Role.BOT, Role.SUPPORT, Role.JUNGLE}
    # Ally rules aren't shown to the champion's own player.
    galio = by_id["MAP-ULT-JOIN-US"][0]
    assert Role.MID not in galio.audience and Role.TOP in galio.audience


@pytest.mark.parametrize("path", GAMES, ids=[p.stem for p in GAMES])
def test_excluded_rules_never_fire_together(path, knowledge):
    fired = evaluate(RULES, analyze(load_game(path, set(knowledge.champions)), knowledge))
    assert conflicts(fired) == []
