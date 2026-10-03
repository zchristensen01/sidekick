"""Gankability, jungle threat, and each laner's jungle plan.

- gankability: how easy it is to gank one side of a lane (docs/ROLES.md formula).
- jungle threat: the enemy jungler's threat to our side of a lane, net of our jungler.
- jungle plan: ask_gank / ask_cover / self_sufficient / danger, and when (docs/KNOWLEDGE.md).
"""

from dataclasses import dataclass, field

from scout.analysis.lanes import LaneState, LaneTimeline
from scout.analysis.players import Lineup
from scout.model.roles import Lane, Role

GANKABLE_AT = 6.0  # gankability that makes a lane a real gank target
THREAT_HIGH_AT, THREAT_MED_AT = 6.0, 4.0


@dataclass(frozen=True)
class Gank:
    lane: Lane
    on_them: float | None  # how gankable their side is (our jungler ganking)
    on_us: float | None  # how gankable our side is (their jungler ganking)
    threat_score: float | None  # their jungler's threat to our side, net of our jungler
    threat: str  # low | med | high | unknown
    our_rank: int | None = None  # 1 = our jungler's best gank target
    their_rank: int | None = None  # 1 = their jungler's most likely target among our lanes
    reasons_on_them: list[str] = field(default_factory=list)
    reasons_on_us: list[str] = field(default_factory=list)


def gankability(
    lineup: Lineup, lane: Lane, attacker: str, state: LaneState
) -> tuple[float | None, list[str]]:
    """How easy it is for `attacker`'s jungler to gank the other side of this lane."""
    defender = "them" if attacker == "us" else "us"
    targets = lineup.in_lane(defender, lane)
    helpers = lineup.in_lane(attacker, lane)
    jungler = lineup.side(attacker).get(Role.JUNGLE)
    escapes = [t.escape for t in targets]
    helper_cc = [h.cc for h in helpers]
    if not targets or not helpers or jungler is None or None in escapes or None in helper_cc:
        return None, []
    if jungler.cc is None:
        return None, []
    diff = state.diff or 0.0
    lane_edge = diff if attacker == "us" else -diff
    peel = [t for t in targets if t.has("peel")]
    score = ((3 - min(escapes)) * 1.5 + max(helper_cc) + 0.5 * jungler.cc - 1.5 * len(peel)
             + 0.5 * max(0.0, lane_edge) + (1 if (state.volatility or 0) >= 5 else 0))  # fmt: skip
    reasons: list[str] = []
    least = min(targets, key=lambda t: t.escape if t.escape is not None else 9)
    if (least.escape or 0) == 0:
        reasons.append(f"{least.name} has no escape")
    elif least.escape == 1:
        reasons.append(f"{least.name} has little escape")
    best_cc = max(helpers, key=lambda h: h.cc or 0)
    if (best_cc.cc or 0) >= 2:
        reasons.append(f"{best_cc.name} has CC to follow up")
    if lane_edge >= 1.5:
        reasons.append("your laners are already ahead" if attacker == "us"
                       else "their laners are already ahead")  # fmt: skip
    return round(score, 2), reasons


def ganks(lineup: Lineup, states: dict[Lane, LaneState]) -> dict[Lane, Gank]:
    our_jg, their_jg = lineup.us.get(Role.JUNGLE), lineup.them.get(Role.JUNGLE)
    raw: dict[Lane, Gank] = {}
    for lane, state in states.items():
        on_them, why_them = gankability(lineup, lane, "us", state)
        on_us, why_us = gankability(lineup, lane, "them", state)
        threat_score = None
        if on_us is not None and their_jg is not None and our_jg is not None:
            threat_score = on_us + (1 if their_jg.style == "ganker" else 0)
            threat_score -= 0.5 * (our_jg.early or 0)
            if their_jg.style == "ganker":
                why_us = [*why_us, f"{their_jg.name} is an early ganker"]
        threat = ("unknown" if threat_score is None else "high" if threat_score >= THREAT_HIGH_AT
                  else "med" if threat_score >= THREAT_MED_AT else "low")  # fmt: skip
        raw[lane] = Gank(lane, on_them, on_us, threat_score, threat,
                         reasons_on_them=why_them, reasons_on_us=why_us)  # fmt: skip
    ours = _ranks({lane: g.on_them for lane, g in raw.items()})
    theirs = _ranks({lane: g.threat_score for lane, g in raw.items()})
    return {
        lane: Gank(
            g.lane,
            g.on_them,
            g.on_us,
            g.threat_score,
            g.threat,
            ours.get(lane),
            theirs.get(lane),
            g.reasons_on_them,
            g.reasons_on_us,
        )  # fmt: skip
        for lane, g in raw.items()
    }


def _ranks(scores: dict[Lane, float | None]) -> dict[Lane, int]:
    known = sorted(
        (s, -list(Lane).index(lane), lane) for lane, s in scores.items() if s is not None
    )
    return {lane: rank for rank, (_, _, lane) in enumerate(reversed(known), 1)}


@dataclass(frozen=True)
class JunglePlan:
    lane: Lane
    kind: str  # ask_gank | ask_cover | self_sufficient | danger | unknown
    phase: str  # e.g. "levels 3-6", "before 6"
    reasons: list[str]


def jungle_plan(state: LaneState, timeline: LaneTimeline, gank: Gank) -> JunglePlan:
    """What this lane's players can tell their jungler (docs/KNOWLEDGE.md, Jungle plan)."""
    lane = state.lane
    if state.verdict == "unknown":
        return JunglePlan(lane, "unknown", "", list(state.reasons))
    phases = timeline.phases
    likely_target = gank.their_rank == 1 and gank.threat == "high"
    if likely_target and gank.our_rank != 1:
        return JunglePlan(lane, "danger", "until you see their jungler", gank.reasons_on_us)
    # Shoved under tower all lane counts as losing early: no farm, and their laners stand far up.
    losing_early = state.verdict == "losing" or phases["l1_3"] == "them" or state.shoved == "us"
    if losing_early and (gank.on_them or 0) >= GANKABLE_AT:
        # Junglers reach a lane after their first clear at the earliest (review 2026-10-02).
        when = "levels 3-6" if phases["l1_3"] == "them" else "right after their first clear"
        return JunglePlan(lane, "ask_gank", when, gank.reasons_on_them)
    their_first = timeline.first("them")
    if their_first in ("post6", "item1") and timeline.first("us") in (None, "l1_3", "l3_6"):
        when = "before 6" if their_first == "post6" else "before their first item"
        return JunglePlan(lane, "ask_cover", when, timeline.reasons[their_first])
    if losing_early:
        return JunglePlan(lane, "ask_cover", "after their first clear", list(state.reasons))
    if gank.threat != "high":
        return JunglePlan(lane, "self_sufficient", "early", [])
    return JunglePlan(lane, "ask_cover", "against their jungler", gank.reasons_on_us)
