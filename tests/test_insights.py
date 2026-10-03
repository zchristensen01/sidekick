"""Insight formulas (docs/ROLES.md, Shared insights) on small made-up lineups."""

import pytest

from scout.analysis.insights import analyze
from scout.data.schemas import CHAMPION_TRAITS
from scout.data.store import build_knowledge
from scout.model.game import GameState, Pick
from scout.model.roles import Lane, Queue, Role

T, J, M, B, S = Role.TOP, Role.JUNGLE, Role.MID, Role.BOT, Role.SUPPORT
AVERAGE = dict(early=2, engage=1, cc=1, escape=1, scaling=2, roam=1, waveclear=2, frontline=1)


def make(champs: dict[str, dict]) -> object:
    """Knowledge for made-up champions: {id: {trait overrides, range=..., classes=...}}."""
    tables = {"champions.csv": [], "champion_meta.csv": []}
    rows = []
    for n, (cid, spec) in enumerate(champs.items(), 1):
        spec = dict(spec)
        meta = {"champ_id": cid, "range_type": spec.pop("range", "melee"),
                "attack_range": str(spec.pop("attack_range", 175)),
                "damage_type": spec.pop("damage", "physical"),
                "classes": spec.pop("classes", "")}  # fmt: skip
        tables["champions.csv"].append({"champ_id": cid, "key": str(n), "name": cid})
        tables["champion_meta.csv"].append(meta)
        if spec.pop("no_traits", False):
            continue
        row = dict.fromkeys(CHAMPION_TRAITS, "")
        values = AVERAGE | spec
        row.update({k: str(v) for k, v in values.items() if k in AVERAGE})
        row.update(champ_id=cid, spikes=values.get("spikes", "6"), tags=values.get("tags", ""),
                   style=values.get("style", ""), reviewed="n", source="prototype")  # fmt: skip
        rows.append(row)
    return build_knowledge("16.19.1", tables, rows)


def game(ally: dict, enemy: dict, me: Role = J, conf: dict | None = None) -> GameState:
    return GameState(
        "16.19.1", Queue.RANKED_SOLO, me,
        {r: Pick(c, r) for r, c in ally.items()},
        {r: Pick(c, r, (conf or {}).get(r, 1.0)) for r, c in enemy.items()},
    )  # fmt: skip


BASE_ALLY = {T: "AT", J: "AJ", M: "AM", B: "AB", S: "AS"}
BASE_ENEMY = {T: "ET", J: "EJ", M: "EM", B: "EB", S: "ES"}


def lineup(**overrides) -> tuple[object, GameState]:
    champs = {c: {} for c in [*BASE_ALLY.values(), *BASE_ENEMY.values()]}
    for cid, spec in overrides.items():
        champs[cid] = spec
    return make(champs), game(BASE_ALLY, BASE_ENEMY)


def test_lane_power_and_verdict():
    k, g = lineup(ET={"early": 3, "engage": 3, "cc": 2})
    top = analyze(g, k).lanes[Lane.TOP]
    # power = early + engage + 0.5 x cc: ours 2 + 1 + 0.5, theirs 3 + 3 + 1
    assert top.us.power == 3.5 and top.them.power == 7.0
    # volatility = how likely someone dies: the bigger all-in threat plus half the smaller one
    assert (top.diff, top.verdict, top.volatility) == (-3.5, "losing", 6.0)
    assert (top.prio, top.fight, top.label) == ("even", "them", "")
    assert "ET has strong early kill pressure" in top.reasons


def test_even_lane_and_bot_lane_aggregates():
    k, g = lineup(AB={"escape": 0, "scaling": 3}, AS={"engage": 3, "cc": 3, "tags": "peel"})
    ins = analyze(g, k)
    assert ins.lanes[Lane.MID].verdict == "even"
    bot = ins.lanes[Lane.BOT]
    assert bot.us.engage == 3 and bot.us.escape == 0  # max engage; the ADC's escape
    assert bot.us.scaling == 2.5 and bot.us.tags == {"peel"}


def test_missing_traits_make_the_lane_unknown():
    k, g = lineup(EM={"no_traits": True})
    ins = analyze(g, k)
    assert ins.lanes[Lane.MID].verdict == "unknown"
    assert ins.plans[Lane.MID].kind == "unknown"
    assert set(ins.timelines[Lane.MID].phases.values()) == {"unknown"}


def test_top_range_mismatch():
    k, g = lineup(ET={"range": "ranged"})
    assert analyze(g, k).lanes[Lane.TOP].range_mismatch is True
    k, g = lineup(EM={"range": "ranged"})
    assert analyze(g, k).lanes[Lane.MID].range_mismatch is False  # top lane only


def test_gankability_formula():
    # Their top: escape 0. Our top cc 2, our jungler cc 2. Lane even (diff 0), not volatile.
    k, g = lineup(ET={"escape": 0}, AT={"cc": 2}, AJ={"cc": 2})
    gank = analyze(g, k).ganks[Lane.TOP]
    # (3 - 0) x 1.5 + 2 + 0.5 x 2 = 7.5; their power 3.5, ours 4.0 -> +0.5 x 0.5 = 7.75
    assert gank.on_them == 7.75
    assert gank.our_rank == 1
    assert gank.reasons_on_them == ["ET has no escape", "AT has CC to follow up"]


def test_peel_lowers_gankability_and_ganker_raises_threat():
    k, g = lineup(ES={"tags": "peel"})
    k0, g0 = lineup()
    base = analyze(g0, k0).ganks[Lane.BOT].on_them
    assert analyze(g, k).ganks[Lane.BOT].on_them == base - 1.5
    k, g = lineup(EJ={"style": "ganker"})
    threat = analyze(g, k).ganks[Lane.TOP]
    # their gankability of our top, +1 for a ganker, -0.5 x our jungler's early (2)
    assert threat.threat_score == threat.on_us + 1 - 1.0
    assert "EJ is an early ganker" in threat.reasons_on_us


def test_jungle_plans():
    # Losing bot, but their ADC has no escape and our support has CC: ask for a gank.
    k, g = lineup(EB={"early": 3, "engage": 3, "escape": 0}, ES={"early": 3, "engage": 3},
                  AS={"cc": 3})  # fmt: skip
    plan = analyze(g, k).plans[Lane.BOT]
    assert (plan.kind, plan.phase) == ("ask_gank", "levels 3-6")
    # They spike at 6 and we don't: ask for cover before 6.
    k, g = lineup(EM={"spikes": "6", "tags": "ult_engage"}, AM={"spikes": "3"})
    plan = analyze(g, k).plans[Lane.MID]
    assert (plan.kind, plan.phase) == ("ask_cover", "before 6")
    # An even, hard-to-gank lane can hold alone.
    k, g = lineup(AT={"escape": 3})
    assert analyze(g, k).plans[Lane.TOP].kind == "self_sufficient"


def test_danger_when_their_jungler_targets_us_and_ours_is_elsewhere():
    k, g = lineup(
        AT={"escape": 0}, ET={"cc": 3}, EJ={"style": "ganker", "cc": 3},  # top is their target
        EB={"escape": 0}, AB={"cc": 3}, AS={"cc": 3},  # our best gank is bot
    )  # fmt: skip
    ins = analyze(g, k)
    assert ins.ganks[Lane.TOP].their_rank == 1 and ins.ganks[Lane.TOP].threat == "high"
    assert ins.ganks[Lane.BOT].our_rank == 1
    assert ins.plans[Lane.TOP].kind == "danger"


def test_timeline_phases():
    k, g = lineup(AM={"spikes": "2|6", "scaling": 3}, EM={"spikes": "6"})
    timeline = analyze(g, k).timelines[Lane.MID]
    assert timeline.phases["l1_3"] == "even"  # +0.5 for a level 2 spike isn't enough alone
    assert timeline.phases["item1"] == "us"
    assert timeline.reasons["item1"] == ["AM scales better"]
    assert timeline.first("us") == "item1"


def test_priority_side():
    k, g = lineup(AM={"waveclear": 3}, AT={"waveclear": 3}, EM={"waveclear": 1},
                  ET={"waveclear": 1})  # fmt: skip
    prio = analyze(g, k).priority
    assert prio.by_lane[Lane.MID] == "us" and prio.by_lane[Lane.TOP] == "us"
    assert prio.side == "top" and prio.them_side == "none"


def test_cross_map_team_and_threats():
    k, g = lineup(
        AM={"tags": "ult_join"}, EB={"tags": "global"}, ES={"roam": 3},
        EM={"early": 3, "classes": "assassin"}, ET={"scaling": 3},
        AT={"engage": 3, "frontline": 3}, AJ={"engage": 2, "frontline": 3},  # Riot: High
    )  # fmt: skip
    ins = analyze(g, k)
    ours = ins.reach["us"]
    assert [(r.player.champ_id, r.kind, r.lanes) for r in ours] == [
        ("AM", "ult_join", (Lane.TOP, Lane.BOT))
    ]  # fmt: skip
    theirs = {(r.player.champ_id, r.kind) for r in ins.reach["them"]}
    assert theirs == {("EB", "global"), ("ES", "roam")}
    team = ins.teams["us"]
    assert (team.n_engagers, team.n_frontline) == (2, 2)
    assert ins.threats[0].player.champ_id == "EM"
    assert "snowballs off early kills" in ins.threats[0].reasons


@pytest.mark.parametrize("damage", ["physical", "magic"])
def test_team_damage_split(damage):
    champs = {c: {"damage": damage} for c in [*BASE_ALLY.values(), *BASE_ENEMY.values()]}
    ins = analyze(game(BASE_ALLY, BASE_ENEMY), make(champs))
    assert ins.teams["them"].damage[damage] == 5


def test_range_gap_and_range_that_changes():
    k, g = lineup(AB={"range": "ranged", "attack_range": 525},
                  EB={"range": "ranged", "attack_range": 650},
                  ET={"range": "ranged", "attack_range": 175})  # fmt: skip
    ins = analyze(g, k)
    assert ins.lanes[Lane.BOT].range_gap == -125  # the ADCs, not the supports
    assert ins.lineup.them[T].range_varies is True  # "ranged" with a melee base range
    assert ins.lineup.them[B].range_varies is False


def test_skirmishes_include_both_junglers():
    k, g = lineup(AM={"early": 3, "engage": 3, "cc": 2}, AJ={"early": 3, "engage": 2})
    fights = analyze(g, k).skirmishes
    # ours: mean early 3 + max engage 3 + 0.5 x 2 = 7.0; theirs: 2 + 1 + 0.5 = 3.5
    assert (fights[Lane.MID].winner, fights[Lane.MID].diff) == ("us", 3.5)
    assert fights[Lane.MID].us_names == "AM/AJ"
    assert fights[Lane.TOP].winner == "us"  # our jungler's early pressure counts there too


def test_jungle_path_starts_opposite_the_target():
    k, g = lineup(ET={"escape": 0}, AT={"cc": 2})  # top is the best gank
    path = analyze(g, k).path
    assert (path.start_side, path.target) == ("bot", Lane.TOP)
    k, g = lineup(EB={"escape": 0}, ES={"escape": 0}, AS={"cc": 3})  # bot is the best gank
    assert analyze(g, k).path.start_side == "top"


BAIT = ({"waveclear": 0, "early": 3, "engage": 3, "cc": 2},
        {"waveclear": 3, "early": 1, "engage": 0, "cc": 0})  # fmt: skip
SURVIVE = ({"waveclear": 0, "early": 1}, {"waveclear": 3, "early": 3, "engage": 3})
BULLY = ({"waveclear": 3, "early": 3, "engage": 3}, {"waveclear": 1, "early": 1})
RESPECT = ({"waveclear": 3}, {"waveclear": 1, "early": 3, "engage": 3, "cc": 3})


@pytest.mark.parametrize(
    ("sides", "expected"),
    [
        (BAIT, ("them", "us", "bait", "even")),  # they push, we'd win fights
        (({"waveclear": 0}, {"waveclear": 3}), ("them", "even", "pushed", "losing")),
        (SURVIVE, ("them", "them", "survive", "losing")),
        (BULLY, ("us", "us", "bully", "winning")),
        (RESPECT, ("us", "them", "shove_respect", "even")),
    ],
)
def test_priority_times_fight(sides, expected):
    k, g = lineup(AT=sides[0], ET=sides[1])
    top = analyze(g, k).lanes[Lane.TOP]
    assert (top.prio, top.fight, top.label, top.verdict) == expected


def test_engage_without_reach_counts_half_when_shoved():
    """Their push takes away a weak engage's chance to connect (the Braum case)."""
    k, g = lineup(AT={"waveclear": 0, "engage": 2, "cc": 2}, ET={"waveclear": 3, "engage": 0})
    weak = analyze(g, k).lanes[Lane.TOP]
    k, g = lineup(AT={"waveclear": 0, "engage": 2, "cc": 2, "tags": "point_click_cc"},
                  ET={"waveclear": 3, "engage": 0})  # fmt: skip
    reach = analyze(g, k).lanes[Lane.TOP]
    assert reach.diff - weak.diff == pytest.approx(0.5 * (2 + 0.5 * 2))


def test_bot_push_is_judged_as_a_unit():
    k, g = lineup(
        AB={"waveclear": 3}, AS={"waveclear": 0}, EB={"waveclear": 2}, ES={"waveclear": 2}
    )
    bot = analyze(g, k).lanes[Lane.BOT]
    assert bot.us.push == pytest.approx(2.0) and bot.them.push == pytest.approx(2.0)
    assert bot.prio == "even"
