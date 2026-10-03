"""Picks for the whole team (M18): DraftGap-style synergy with locked allies on top of the lane,
and team-fit reasons from sourced facts only. Recorded data and small stubs; no network."""

import dataclasses
from pathlib import Path

from scout.analysis.stats import DuoStat
from scout.model.gamefile import load_game
from scout.model.roles import Role
from scout.picks import Candidate, Option, _rank, _synergy, option_text, team_reasons

ROOT = Path(__file__).resolve().parent.parent


def game(knowledge, my_role=Role.JUNGLE, **ally):
    g = load_game(ROOT / "tests/fixtures/games/samira_naut.yaml", set(knowledge.champions))
    allies = {r: p for r, p in g.ally.items() if r is not my_role}
    for role_name, champ in ally.items():
        role = Role(role_name)
        allies[role] = dataclasses.replace(g.ally.get(role) or g.enemy[role], champ_id=champ,
                                           role=role)  # fmt: skip
    return dataclasses.replace(g, my_role=my_role, ally=allies)


def test_synergy_moves_a_pick_up():
    a = Option(Candidate("A", "pool", 0), "A", "even", 0.52, "52% over 2,000 games")
    pair = "pairs well with your Leona (together 55% over 900 games)"
    b = Option(Candidate("B", "pool", 1), "B", "even", 0.50, "50% over 2,000 games",
               synergy=0.03, synergy_text=pair)  # fmt: skip
    assert [o.name for o in _rank([a, b])] == ["B", "A"]  # 0.50 + 0.03 beats 0.52
    assert pair in option_text(b, "Zed", Role.MID)


class StubLookup:
    """Only `duo`: Lee Sin does well with Ahri, a little worse with Jhin; nothing else known."""

    def duo(self, a, a_role, b, b_role, side="us"):
        found = {"Ahri": (0.55, 0.52, 1200), "Jhin": (0.495, 0.50, 300)}.get(b)
        if a != "LeeSin" or found is None:
            return None
        rate, expected, games = found
        return DuoStat(side, a, b, games, rate, expected, rate - expected, games >= 500,
                       f"{round(rate * 100)}% over {games:,} games")  # fmt: skip


def test_synergy_sums_deltas_and_names_the_best_supported_pair(knowledge):
    g = game(knowledge)
    total, text = _synergy(StubLookup(), Role.JUNGLE, "LeeSin", g, knowledge)
    assert round(total, 3) == round(0.03 - 0.005, 3)  # every ally counts
    assert text == "pairs well with your Ahri (together 55% over 1,200 games)"  # shown only
    assert _synergy(StubLookup(), Role.JUNGLE, "Elise", g, knowledge) == (0.0, "")
    assert _synergy(None, Role.JUNGLE, "LeeSin", g, knowledge) == (0.0, "")


def test_knockups_for_an_ally_whose_ult_needs_airborne(knowledge):
    g = game(knowledge, mid="Yasuo")
    assert {"knockup", "knockback"} & knowledge.facts("LeeSin").mechanics  # the wiki
    reasons = team_reasons("LeeSin", g, knowledge)
    assert reasons[0] == "has knock-ups for your Yasuo's ultimate, which needs airborne targets"
    assert not any("Yasuo" in r for r in team_reasons("Elise", g, knowledge))  # no knock-up


def test_sourced_frontline_and_control_reasons(knowledge):
    squishy = game(knowledge, my_role=Role.SUPPORT, top="Teemo", jungle="Kindred", mid="Ahri",
                   bot="Jhin")  # fmt: skip
    leona = team_reasons("Leona", squishy, knowledge)
    assert "adds a frontliner (Riot rates its toughness high; your team has none)" in leona
    assert "adds crowd control (Riot rates its control high; your team has none)" in leona
    with_tank = game(knowledge, my_role=Role.SUPPORT, top="Malphite", jungle="Kindred",
                     mid="Ahri", bot="Jhin")  # fmt: skip
    assert not any("frontliner" in r for r in team_reasons("Leona", with_tank, knowledge))


def test_drafted_tags_need_the_owners_review(knowledge):
    g = game(knowledge, my_role=Role.TOP)
    g = dataclasses.replace(g, enemy={**g.enemy, Role.MID: dataclasses.replace(
        g.enemy[Role.MID], champ_id="Jinx")})  # two marksmen: Samira, Jinx
    drafted = knowledge.traits[("Teemo", "")]
    tagged = dataclasses.replace(drafted, tags=drafted.tags | {"anti_auto"}, source="llm")
    k = dataclasses.replace(knowledge, traits={**knowledge.traits, ("Teemo", ""): tagged})
    assert not any("auto-attackers" in r for r in team_reasons("Teemo", g, k))
    mine = dataclasses.replace(tagged, source="owner")
    k = dataclasses.replace(knowledge, traits={**knowledge.traits, ("Teemo", ""): mine})
    assert any("auto-attackers" in r for r in team_reasons("Teemo", g, k))


def test_the_draft_fetches_each_allys_synergy_table(knowledge, tmp_path):
    from test_picks import picker
    from test_stats import FakeOpgg, make_service
    from test_watcher import make_watcher, replay

    from scout.data import opgg

    watcher, messages, clock = make_watcher(knowledge, tmp_path)
    server = FakeOpgg()
    service = make_service(server)
    service.refresh_lane_meta()
    watcher.stats = service
    watcher.picker = picker(knowledge, service, pool={Role.JUNGLE: ("LeeSin", "Amumu")})
    replay(watcher, clock)
    service.wait(30)
    asked = [(a["champion"], a["my_position"], a["synergy_position"])
             for t, a in server.calls if t == opgg.SYNERGIES]
    assert any(position == "jungle" for _, _, position in asked)  # each ally with my role
    assert len(asked) == len(set(asked))  # a call that ran isn't repeated on every update
    service.close()
