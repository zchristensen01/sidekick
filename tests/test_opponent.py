"""Know your opponent (2026-10-02): each lane opponent's passive and Riot's tip against
them, from Riot's own data (Data Dragon `passive` and `enemytips`), never written by us."""

import dataclasses
import json
from pathlib import Path

from scout.analysis.insights import analyze
from scout.model.gamefile import load_game
from scout.model.roles import Role
from scout.report.builder import build_input
from scout.report.render import render_text
from scout.report.select import select
from scout.rules.engine import evaluate, load_rules

ROOT = Path(__file__).resolve().parent.parent
RULES = load_rules(ROOT / "scout/rules/league_rules.yaml")
# Copied from Data Dragon 16.19.1 championFull.json.
SIVIR_PASSIVE = {"champ_id": "Sivir", "slot": "P", "name": "Fleet of Foot", "max_rank": "",
                 "cooldowns": "", "description": "Sivir gains a short burst of Move Speed when "
                 "she attacks an enemy champion."}  # fmt: skip
SIVIR_TIPS = (
    "Boomerang Blade costs a lot of mana to cast, so dodging it sets Sivir back. If it hits you "
    "on the way out, avoid its path on the way back.",
    "Sivir is a powerful pushing champion, so leaving her unattended in a lane for too long will "
    "often result in your turrets being destroyed.",
)


def with_sivir(knowledge):
    abilities = {**knowledge.abilities, "Sivir": (SIVIR_PASSIVE,)}
    tips = {**knowledge.tips, ("Sivir", "enemy"): SIVIR_TIPS}
    return dataclasses.replace(knowledge, abilities=abilities, tips=tips)


def report(knowledge, role):
    game = load_game(
        ROOT / "tests/fixtures/games/bot_shove.yaml", set(knowledge.champions)
    )
    ins = analyze(dataclasses.replace(game, my_role=role), with_sivir(knowledge))
    return ins, select(ins, evaluate(RULES, ins))


def test_bot_lane_hears_what_their_adc_does(knowledge):
    for role in (Role.BOT, Role.SUPPORT):
        _, r = report(knowledge, role)
        section = next(s for s in r.sections if s.key == "opponent")
        texts = [i.text for i in section.items]
        assert ("Sivir's passive, Fleet of Foot: Sivir gains a short burst of Move Speed when "
                "she attacks an enemy champion.") in texts  # fmt: skip
        assert f"Riot's tip against Sivir: {SIVIR_TIPS[0]}" in texts
        assert {i.source for i in section.items} >= {"riot:passive:Sivir", "riot:tip:Sivir"}


def test_other_roles_dont_get_bot_lanes_opponent(knowledge):
    _, r = report(knowledge, Role.TOP)
    assert "Sivir's passive" not in render_text(r)


def test_the_writer_gets_the_whole_kit_and_riots_tips(knowledge):
    ins, r = report(knowledge, Role.SUPPORT)
    payload = build_input(r, ins, ins.knowledge, 120)
    sivir = payload["facts"]["Sivir"]
    assert sivir["abilities"]["Passive"]["name"] == "Fleet of Foot"
    assert sivir["riot_tips_against"] == list(SIVIR_TIPS)
    assert sivir["summoner_spells"] == ["barrier", "flash"]
    json.dumps(payload)
