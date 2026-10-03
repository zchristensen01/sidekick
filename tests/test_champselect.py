"""Champ select session -> GameState (docs/LCU.md section 4), on fakes and real recordings."""

import json
from pathlib import Path

import pytest
from lcu_fakes import make_champ_select_session

from scout.analysis.role_inference import rates_from_wiki_positions
from scout.data.store import read_csv
from scout.lcu.champselect import (
    ChampionIndex,
    NotReportable,
    banned_keys,
    confirmed_roles,
    parse_session,
    pick_turns,
)
from scout.model.roles import Queue, Role

FIXTURES = Path(__file__).parent / "fixtures"
STATIC = {name: read_csv(FIXTURES / "static" / "16.19.1" / name)
          for name in ("champions.csv", "champion_meta.csv", "summoner_spells.csv")}  # fmt: skip
INDEX = ChampionIndex.from_static("16.19.1", STATIC)
RATES = rates_from_wiki_positions(STATIC["champion_meta.csv"])
RECORDED = sorted((FIXTURES / "champselect").glob("*.json"))
T, J, M, B, S = Role.TOP, Role.JUNGLE, Role.MID, Role.BOT, Role.SUPPORT

# The fake session's champions: allies Garen, LeeSin, Ahri, Jhin, Lulu; enemies below.
ENEMIES = (122, 60, 7, 51, 89)  # Darius, Elise, LeBlanc, Caitlyn, Leona


def final_session(**kwargs):
    return make_champ_select_session(phase="FINALIZATION", enemy_champs=ENEMIES, **kwargs)


def test_static_fixture_has_smite():
    assert INDEX.smite_key == 11 and INDEX.by_key[64] == "LeeSin"


def test_a_finished_draft():
    game = parse_session(final_session(), INDEX, RATES)
    assert game.queue is Queue.RANKED_SOLO and game.my_role is J
    assert game.my_pick.champ_id == "LeeSin" and game.my_pick.pick_turn == 3
    assert {r: p.champ_id for r, p in game.ally.items()} == {
        T: "Garen", J: "LeeSin", M: "Ahri", B: "Jhin", S: "Lulu"
    }  # fmt: skip
    assert {r: p.champ_id for r, p in game.enemy.items()} == {
        T: "Darius", J: "Elise", M: "Leblanc", B: "Caitlyn", S: "Leona"
    }  # fmt: skip
    assert game.enemy[J].pick_turn == 2 and game.enemy[J].role_confidence > 0.9
    assert game.enemy_role_odds[J][0][0] == "Elise"
    assert game.notes == []


def test_queue_gate_and_missing_position():
    with pytest.raises(NotReportable, match=r"ARAM \(queue 450\) isn't a draft or ranked game"):
        parse_session(final_session(queue_id=450), INDEX, RATES)
    assert parse_session(final_session(queue_id=450), INDEX, RATES, queue_id=400).queue is (
        Queue.NORMAL_DRAFT
    )
    session = final_session()
    session["myTeam"][1]["assignedPosition"] = ""
    with pytest.raises(NotReportable, match="position"):
        parse_session(session, INDEX, RATES)


def test_mid_draft_only_counts_locked_champions():
    session = make_champ_select_session(enemy_champs=(122, 0, 0, 0, 0))
    for turn in session["actions"][3:]:  # turn 3 on hasn't locked yet (I'm hovering Lee Sin)
        for action in turn:
            action["completed"] = False
    game = parse_session(session, INDEX, RATES)
    assert J not in game.ally and set(game.ally) == {T}
    assert {r: p.champ_id for r, p in game.enemy.items()} == {T: "Darius"}


def test_ally_with_smite_is_the_jungler():
    session = final_session()
    session["myTeam"][1]["spell2Id"] = 4  # the assigned jungler (me) took no Smite
    session["myTeam"][2]["spell2Id"] = 11  # the assigned mid laner has Smite
    game = parse_session(session, INDEX, RATES)
    assert game.ally[J].champ_id == "Ahri" and game.ally[M].champ_id == "LeeSin"
    assert game.my_role is M
    assert game.notes == [
        "Role swap: Ahri (assigned mid) has Smite, so they're treated as the jungler and the "
        "assigned jungler as mid."
    ]


def test_unknown_champion_is_a_placeholder_with_one_note():
    session = final_session()
    session["theirTeam"][0]["championId"] = 9999
    session["actions"][2][0]["championId"] = 9999
    session["actions"][0][0].update(championId=9999, completed=True)  # also banned
    game = parse_session(session, INDEX, RATES)
    assert "Unknown9999" in {p.champ_id for p in game.enemy.values()}
    assert game.notes == ["Unknown champion id 9999: probably new; run `scout refresh` to add it."]


def test_pick_turns_ignore_everything_but_completed_picks():
    actions = [
        [{"type": "ban", "championId": 1, "completed": True}],
        [{"type": "ten_bans_reveal", "championId": 0, "completed": True, "actorCellId": -1}],
        [{"type": "pick", "championId": 64, "completed": True},
         {"type": "pick", "championId": 60, "completed": False}],
        [{"type": "vote", "championId": 7, "completed": True}, "junk"],
        [{"type": "pick", "championId": 7, "completed": True}],
    ]  # fmt: skip
    assert pick_turns(actions) == {64: 2, 7: 4}
    assert pick_turns(None) == {}


def test_empty_ban_slots_are_ignored():
    """A skipped ban is championId -1 in the client (seen live 2026-10-02)."""
    actions = [[{"type": "ban", "championId": -1, "completed": True},
                {"type": "ban", "championId": 64, "completed": True},
                {"type": "ban", "championId": 60, "completed": False}]]  # fmt: skip
    assert banned_keys(actions) == [64]


def test_confirmed_roles_from_the_loading_screen():
    roster = {
        "teamOne": [{"championId": 64, "selectedPosition": "JUNGLE"}],
        "teamTwo": [{"championId": 60, "selectedPosition": ""},
                    {"championId": 122, "selectedPosition": ""}],
        "spells": [{"championId": 60, "spell1Id": 11, "spell2Id": 4},
                   {"championId": 122, "spell1Id": 4, "spell2Id": 12}],
    }  # fmt: skip
    assert confirmed_roles(roster, [60, 122], smite_key=11) == {60: J}
    assert confirmed_roles(roster, [64], smite_key=11) == {64: J}
    assert confirmed_roles(None, [60], 11) == {} and confirmed_roles(roster, [60], None) == {}


# ---------------------------------------------------------------- real recorded champ selects


@pytest.mark.parametrize("path", RECORDED, ids=[p.name for p in RECORDED])
def test_recorded_champ_selects_parse(path):
    data = json.loads(path.read_text(encoding="utf-8"))
    meta = data["meta"]
    games = [parse_session(s["session"], INDEX, RATES, meta["queue_id"]) for s in data["snapshots"]]
    final = games[-1]
    assert final.my_role.value == meta["my_role"]
    if meta["my_champion_id"]:  # 0: recording stopped before my pick
        assert INDEX.by_key[meta["my_champion_id"]] == final.my_pick.champ_id
    assert not any("Unknown champion" in n for g in games for n in g.notes)
    if meta["outcome"] == "game_started":
        assert len(final.ally) == 5 and len(final.enemy) == 5
        assert not any(p.champ_id.startswith("Unknown") for p in final.enemy.values())


# Real drafts no role prior can call: off-role picks the stats say almost never happen. The
# loading-screen check (Smite, then the rest re-guessed) is what fixes these; it did, live.
OFF_META = {
    "sample_3_ranked_solo_support.json":
        "Morgana jungle and Tryndamere mid: two off-role picks in one draft",
}  # fmt: skip


@pytest.mark.parametrize(
    "path",
    [pytest.param(p, marks=pytest.mark.xfail(reason=OFF_META[p.name], strict=True))
     if p.name in OFF_META else p for p in RECORDED],
    ids=[p.name for p in RECORDED],
)  # fmt: skip
def test_enemy_roles_match_the_answer_key_or_are_flagged(path):
    """docs/TASKS.md M4: right, or below roles.low_confidence_below (0.6)."""
    data = json.loads(path.read_text(encoding="utf-8"))
    if not data.get("game_start"):
        pytest.skip("recorded before the game-start answer key existed")
    final = parse_session(data["snapshots"][-1]["session"], INDEX, RATES, data["meta"]["queue_id"])
    keys = {INDEX.by_key[k]: k for k in INDEX.by_key}
    enemy_keys = [keys[p.champ_id] for p in final.enemy.values()]
    truth = confirmed_roles(data["game_start"], enemy_keys, INDEX.smite_key)
    for role, pick in final.enemy.items():
        real = truth.get(keys[pick.champ_id])
        if real is not None and real is not role:
            assert pick.role_confidence < 0.6, f"{pick.champ_id}: guessed {role}, was {real}"
