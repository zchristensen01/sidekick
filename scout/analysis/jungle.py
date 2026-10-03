"""Jungle matchup and map priority.

- jungle_matchup: early 1v1, invade risk, styles, each jungler's likely first gank side.
- priority: which lanes can move first, so which side of the map has priority.
docs/ROLES.md (Shared insights).
"""

from dataclasses import dataclass, field

from scout.analysis.ganks import Gank
from scout.analysis.lanes import VOLATILE_AT, LaneState
from scout.analysis.players import Lineup, Player
from scout.model.roles import Lane, Role

PRIORITY_AT = 1.0


@dataclass(frozen=True)
class Priority:
    by_lane: dict[Lane, str]  # us | them | even | unknown: who can move first
    side: str  # top | bot | none: where our side of the map has priority
    them_side: str  # the same for them
    reasons: list[str] = field(default_factory=list)


def priority(states: dict[Lane, LaneState]) -> Priority:
    by_lane: dict[Lane, str] = {}
    scores: dict[Lane, float] = {}
    for lane, state in states.items():
        us_clear, them_clear = state.us.waveclear, state.them.waveclear
        if us_clear is None or them_clear is None or state.diff is None:
            by_lane[lane] = "unknown"
            continue
        score = (us_clear - them_clear) + 0.5 * state.diff
        scores[lane] = score
        by_lane[lane] = (
            "us" if score >= PRIORITY_AT else "them" if score <= -PRIORITY_AT else "even"
        )

    def side_for(who: str) -> str:
        if by_lane.get(Lane.MID) != who:
            return "none"
        sides = [lane for lane in (Lane.TOP, Lane.BOT) if by_lane.get(lane) == who]
        if not sides:
            return "none"
        sign = 1 if who == "us" else -1
        return max(sides, key=lambda lane: sign * scores[lane]).value

    reasons = [f"{lane.value} can move first" for lane, who in by_lane.items() if who == "us"]
    return Priority(by_lane, side_for("us"), side_for("them"), reasons)


@dataclass(frozen=True)
class JungleMatchup:
    us: Player | None
    them: Player | None
    diff: int | None  # our jungler's early minus theirs
    invade_risk: bool  # they're a strong invader and their lanes can move first
    our_first_gank: Lane | None  # our best gank target
    their_first_gank: Lane | None  # their most likely first target among our lanes
    reasons: list[str] = field(default_factory=list)


def jungle_matchup(lineup: Lineup, ganks: dict[Lane, Gank], prio: Priority) -> JungleMatchup:
    us, them = lineup.us.get(Role.JUNGLE), lineup.them.get(Role.JUNGLE)
    diff = None
    if us and them and us.early is not None and them.early is not None:
        diff = us.early - them.early
    their_lanes_first = [lane for lane, who in prio.by_lane.items() if who == "them"]
    invade_risk = bool(
        them and them.has("invade_strong") and Lane.MID in their_lanes_first
        and len(their_lanes_first) >= 2
    )  # fmt: skip
    ours = next((g.lane for g in ganks.values() if g.our_rank == 1), None)
    theirs = next((g.lane for g in ganks.values() if g.their_rank == 1), None)
    reasons = []
    if diff is not None and diff != 0:
        stronger = us if diff > 0 else them
        reasons.append(f"{stronger.name} is stronger early 1v1")
    if invade_risk and them:
        reasons.append(f"{them.name} invades well and their lanes can move first")
    return JungleMatchup(us, them, diff, invade_risk, ours, theirs, reasons)


SKIRMISH_AT = 1.0  # power difference for one side to win a 2v2 or 3v3 early


@dataclass(frozen=True)
class Skirmish:
    """Who wins early fights where a lane and both junglers meet (river, scuttle, dragon)."""

    lane: Lane
    winner: str  # us | them | even | unknown
    diff: float | None
    us_names: str
    them_names: str


def skirmishes(lineup: Lineup) -> dict[Lane, Skirmish]:
    """Each lane's laners plus their jungler, side against side: mean early, max engage, CC."""
    out: dict[Lane, Skirmish] = {}
    for lane in Lane:
        sides = {}
        for side in ("us", "them"):
            group = lineup.in_lane(side, lane)
            jungler = lineup.side(side).get(Role.JUNGLE)
            if jungler is not None:
                group = [*group, jungler]
            sides[side] = (group, _power(group))
        (ours, us_power), (theirs, them_power) = sides["us"], sides["them"]
        names = ("/".join(p.name for p in ours), "/".join(p.name for p in theirs))
        if us_power is None or them_power is None:
            out[lane] = Skirmish(lane, "unknown", None, *names)
            continue
        diff = round(us_power - them_power, 2)
        winner = "us" if diff >= SKIRMISH_AT else "them" if diff <= -SKIRMISH_AT else "even"
        out[lane] = Skirmish(lane, winner, diff, *names)
    return out


def _power(group: list[Player]) -> float | None:
    early = [p.early for p in group]
    engage = [p.engage for p in group]
    cc = [p.cc for p in group]
    if not group or None in early or None in engage or None in cc:
        return None
    return sum(early) / len(early) + max(engage) + 0.5 * max(cc)


@dataclass(frozen=True)
class JunglePath:
    """A suggested early route: where to start, where to end the first clear, what to watch."""

    start_side: str  # top | bot | either
    target: Lane | None  # where to look for the first gank
    counter: Lane | None  # where their jungler most likely shows first (counter-gank chance)
    reasons: list[str] = field(default_factory=list)


def jungle_path(
    ganks: dict[Lane, Gank], lanes: dict[Lane, LaneState], prio: Priority, matchup: JungleMatchup
) -> JunglePath:
    """Start on the side opposite the first gank target so the clear ends next to it.

    The target is our best gank lane; a volatile lane where both sides can kill each other
    early is preferred when it's nearly as gankable, because that's where the first jungler to
    arrive decides the lane.
    """
    ranked = sorted((g for g in ganks.values() if g.on_them is not None),
                    key=lambda g: -(g.on_them or 0))  # fmt: skip
    if not ranked:
        return JunglePath("either", None, matchup.their_first_gank, ["not enough traits"])
    best = ranked[0]
    for g in ranked[1:]:
        volatile = (lanes[g.lane].volatility or 0) >= VOLATILE_AT and lanes[
            best.lane
        ].volatility is not None
        if (
            volatile
            and (g.on_them or 0) >= (best.on_them or 0) - 1.0
            and ((lanes[best.lane].volatility or 0) < VOLATILE_AT)
        ):
            best = g
            break
    target = best.lane
    reasons = [f"{target.value}: {'; '.join(best.reasons_on_them)}"] if best.reasons_on_them else []
    if (lanes[target].volatility or 0) >= VOLATILE_AT:
        reasons.append(f"{target.value} is volatile, so the first jungler there decides it")
    if target is Lane.TOP:
        start = "bot"
    elif target is Lane.BOT:
        start = "top"
    else:
        start = "top" if prio.side == "bot" else "bot" if prio.side == "top" else "either"
    return JunglePath(start, target, matchup.their_first_gank, reasons)
