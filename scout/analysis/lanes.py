"""Lane state and lane timeline.

- lane_state: two readings per lane (docs/REVIEW_BRIEF.md, outside review 2026-10-02):
  Priority (who pushes early: waveclear, bot as a unit) and Fight (trades and all-ins; engage
  counts fully only if it can reach someone). Together they give the verdict and a label: bully,
  push edge, shove and respect, bait lane, pushed, survive. Volatility = how likely someone
  dies early (both sides' all-in threat), not how strong the stronger side is.
- with_stats: OP.GG's lane-advantage label decides who wins early when the sample is big
  enough (docs/STATS.md, Stats vs traits); the traits verdict is kept for the disagreement note.
- lane_timeline: who's favored at levels 1-3, 3-6, after 6, after first item, and why.
Starting formulas from docs/ROLES.md (Shared insights); tune them with post-game data (M10).
"""

import dataclasses
from dataclasses import dataclass, field

from scout.analysis.players import Lineup, Player
from scout.analysis.stats import GameStats, lane_advantage
from scout.model.roles import LANE_ROLES, Lane, Role

WIN_AT = 1.5  # fight difference for one side to win trades and all-ins
PRIO_AT = 1.5  # push difference for one side to control the waves
VOLATILE_AT = 4.0  # death likelihood for a volatile lane (5.5+: very volatile)
NO_REACH = 0.5  # all-in weight for a side that neither pushes nor can reach the enemy
RANGE_EDGE = 75  # bot: base attack range gap that wins trades
KILL_SPELLS = frozenset({"ignite", "exhaust"})  # summoner spells that add to an all-in
KILL_SPELL_BONUS = 0.5
LABELS = {  # (priority, fight) -> label, verdict
    ("us", "us"): ("bully", "winning"), ("us", "even"): ("push_edge", "winning"),
    ("us", "them"): ("shove_respect", "even"), ("them", "us"): ("bait", "even"),
    ("them", "even"): ("pushed", "losing"), ("them", "them"): ("survive", "losing"),
}  # fmt: skip
PHASE_AT = 1.0  # phase score difference for one side to be favored
ITEM_PHASE_AT = 0.5
PHASES = ("l1_3", "l3_6", "post6", "item1")
PHASE_LABEL = {
    "l1_3": "levels 1-3", "l3_6": "levels 3-6", "post6": "after 6", "item1": "after first item",
}  # fmt: skip
ULT_TAGS = frozenset({"ult_engage", "global", "ult_join"})


@dataclass(frozen=True)
class SideView:
    """One side of one lane. Values are None when any champion lacks the trait."""

    players: tuple[Player, ...]
    carry: Player | None  # the ADC in bot, otherwise the laner
    early: float | None  # mean
    scaling: float | None  # mean
    engage: int | None  # max
    cc: int | None  # max
    roam: int | None  # max
    waveclear: int | None  # max
    frontline: int | None  # max
    escape: int | None  # the carry's
    range: str | None  # the carry's
    attack_range: float | None  # the carry's base attack range
    range_varies: bool  # the carry's range changes with form or level
    tags: frozenset[str]
    classes: frozenset[str]
    power: float | None  # mean early + max engage + 0.5 x max cc (before the access gate)
    push: float | None = None  # early wave control: best pusher + half the other, as a unit
    trade: float | None = None  # mean early + 0.5 for poke
    allin: float | None = None  # max engage + 0.5 x CC chain (best CC + half the next)
    reach: bool = False  # can start a fight without priority (strong engage, hook, dive)
    spells: frozenset[str] = frozenset()  # summoner spells on this side, when known

    @property
    def names(self) -> str:
        return "/".join(p.name for p in self.players)

    def verb(self, singular: str, plural: str) -> str:
        """'Darius keeps' / 'Jhin/Lulu keep'."""
        return f"{self.names} {singular if len(self.players) == 1 else plural}"


def side_view(players: list[Player]) -> SideView:
    def values(name: str) -> list[int] | None:
        found = [getattr(p, name) for p in players]
        return None if not found or any(v is None for v in found) else found

    def mean(name: str) -> float | None:
        v = values(name)
        return sum(v) / len(v) if v else None

    def peak(name: str) -> int | None:
        v = values(name)
        return max(v) if v else None

    carry = next((p for p in players if p.role is Role.BOT), players[0] if players else None)
    early, engage, cc = mean("early"), peak("engage"), peak("cc")
    power = early + engage + 0.5 * cc if None not in (early, engage, cc) else None
    waves, ccs = values("waveclear"), values("cc")
    push = _unit(waves) if waves else None
    chain = None
    if ccs:
        ranked = sorted(ccs, reverse=True)
        chain = ranked[0] + (0.5 * ranked[1] if len(ranked) > 1 else 0)
    poke = 0.5 if any("poke" in p.tags for p in players) else 0.0
    trade = early + poke if early is not None else None
    spells = frozenset().union(*(p.spells for p in players)) if players else frozenset()
    kill = KILL_SPELL_BONUS if spells & KILL_SPELLS else 0.0  # Ignite / Exhaust (review)
    allin = engage + 0.5 * chain + kill if engage is not None and chain is not None else None
    reach = any((p.engage or 0) >= 3 or p.tags & {"point_click_cc", "dive"}
                or "catcher" in p.classes for p in players)  # fmt: skip
    return SideView(
        players=tuple(players),
        carry=carry,
        early=early,
        scaling=mean("scaling"),
        engage=engage,
        cc=cc,
        roam=peak("roam"),
        waveclear=peak("waveclear"),
        frontline=peak("frontline"),
        escape=carry.escape if carry else None,
        range=carry.range if carry else None,
        attack_range=carry.attack_range if carry else None,
        range_varies=bool(carry and carry.range_varies),
        tags=frozenset().union(*(p.tags for p in players)) if players else frozenset(),
        classes=frozenset().union(*(p.classes for p in players)) if players else frozenset(),
        power=power,
        push=push,
        trade=trade,
        allin=allin,
        reach=reach,
        spells=spells,
    )


def _unit(values: list[int]) -> float:
    """A lane's push as a unit: the best pusher plus half the other (bot), on the 0-3 scale."""
    ranked = sorted(values, reverse=True)
    return ranked[0] if len(ranked) == 1 else (ranked[0] + 0.5 * ranked[1]) / 1.5


@dataclass(frozen=True)
class LaneState:
    lane: Lane
    us: SideView
    them: SideView
    diff: float | None  # our fight score minus theirs
    volatility: float | None  # how likely someone dies early (both sides' all-in threat)
    verdict: str  # winning | even | losing | unknown
    range_mismatch: bool  # top only: ranged vs melee (trait power misses range)
    range_gap: float | None = None  # our carry's base attack range minus theirs
    source: str = "traits"  # traits | stats
    reasons: list[str] = field(default_factory=list)
    traits_verdict: str = ""  # what the traits said, when stats decided the verdict
    shoved: str = ""  # us | them: that side gets pushed under tower (the other has priority)
    prio: str = "even"  # us | them | even: who controls the waves early
    fight: str = "even"  # us | them | even: who wins trades and all-ins
    label: str = ""  # bully | push_edge | shove_respect | bait | pushed | survive | ""

    @property
    def disagrees(self) -> bool:
        """Stats and traits point opposite ways (not just even vs a side)."""
        return {self.verdict, self.traits_verdict} == {"winning", "losing"}


def lane_state(lineup: Lineup, lane: Lane) -> LaneState:
    us, them = side_view(lineup.in_lane("us", lane)), side_view(lineup.in_lane("them", lane))
    if None in (us.trade, us.allin, us.push, them.trade, them.allin, them.push):
        missing = [p.name for p in (*us.players, *them.players) if not p.has_traits]
        reasons = [f"no traits for {', '.join(missing)}"] if missing else ["not all picks known"]
        return LaneState(lane, us, them, None, None, "unknown", False, _gap(us, them),
                         reasons=reasons)  # fmt: skip
    push_diff = us.push - them.push
    prio = "us" if push_diff >= PRIO_AT else "them" if push_diff <= -PRIO_AT else "even"
    # An all-in only counts fully if that side controls the wave or can reach the enemy anyway
    # (a shoved lane: Braum's CC never connects while Sivir/Seraphine push).
    access_us = 1.0 if prio != "them" or us.reach else NO_REACH
    access_them = 1.0 if prio != "us" or them.reach else NO_REACH
    range_us, range_them = _range_edge(lane, us, them)
    fight_us = us.trade + range_us + access_us * us.allin
    fight_them = them.trade + range_them + access_them * them.allin
    diff = fight_us - fight_them
    fight = "us" if diff >= WIN_AT else "them" if diff <= -WIN_AT else "even"
    label, verdict = LABELS.get((prio, fight), ("", {"us": "winning", "them": "losing"}.get(
        fight, "even")))  # fmt: skip
    mismatch = (lane is Lane.TOP and us.range is not None and them.range is not None
                and us.range != them.range)  # fmt: skip
    threat_us = access_us * us.allin + 0.5 * us.early - 0.5 * (them.escape or 0)
    threat_them = access_them * them.allin + 0.5 * them.early - 0.5 * (us.escape or 0)
    volatility = max(threat_us, threat_them) + 0.5 * min(threat_us, threat_them)
    shoved = {"them": "us", "us": "them"}.get(prio, "")
    reasons = _reasons(us, them, prio, fight)
    return LaneState(lane, us, them, round(diff, 2), round(volatility, 2), verdict, mismatch,
                     _gap(us, them), reasons=reasons, shoved=shoved, prio=prio, fight=fight,
                     label=label)  # fmt: skip


def _range_edge(lane: Lane, us: SideView, them: SideView) -> tuple[float, float]:
    """Bot: the ADC with the clearly longer base range wins free trades (+0.5)."""
    gap = _gap(us, them)
    if lane is not Lane.BOT or gap is None or us.range_varies or them.range_varies:
        return 0.0, 0.0
    return (0.5 if gap >= RANGE_EDGE else 0.0), (0.5 if gap <= -RANGE_EDGE else 0.0)


def _reasons(us: SideView, them: SideView, prio: str, fight: str) -> list[str]:
    reasons = []
    if prio != "even":
        pusher = us if prio == "us" else them
        reasons.append(pusher.verb("clears waves much faster", "clear waves much faster"))
    if fight != "even":
        reasons += _power_reasons(us if fight == "us" else them)
    return reasons


def with_stats(state: LaneState, stats: GameStats) -> LaneState:
    """Use OP.GG's lane-advantage labels for the verdict when every shown label agrees
    (bot lane: the ADC and support labels; an even one doesn't contradict a side)."""
    found = [a for r in LANE_ROLES[state.lane] if (a := lane_advantage(stats.matchups.get(r)))]
    sides = {a for a in found if a in ("us", "them")}
    if not found or len(sides) > 1:
        return state
    verdict = {"us": "winning", "them": "losing"}[sides.pop()] if sides else "even"
    reasons = state.reasons
    if verdict != state.verdict:
        stronger = state.us if verdict == "winning" else state.them
        reasons = (
            [f"OP.GG's matchup data gives {stronger.names} the early edge"]
            if verdict != "even"
            else []
        )
    fight = {"winning": "us", "losing": "them"}.get(verdict, state.fight)
    label, implied = LABELS.get((state.prio, fight), ("", verdict))
    if implied != verdict:
        label = ""
    return dataclasses.replace(
        state, verdict=verdict, source="stats", reasons=reasons, traits_verdict=state.verdict,
        fight=fight, label=label,
    )  # fmt: skip


def _gap(us: SideView, them: SideView) -> float | None:
    if us.attack_range is None or them.attack_range is None:
        return None
    return us.attack_range - them.attack_range


def _power_reasons(side: SideView) -> list[str]:
    reasons = []
    top_early = max(side.players, key=lambda p: p.early or 0)
    if (top_early.early or 0) >= 3:
        reasons.append(f"{top_early.name} has strong early kill pressure")
    top_engage = max(side.players, key=lambda p: p.engage or 0)
    if (top_engage.engage or 0) >= 3:
        reasons.append(f"{top_engage.name} can start fights")
    return reasons or [side.verb("has more early power", "have more early power")]


@dataclass(frozen=True)
class LaneTimeline:
    lane: Lane
    phases: dict[str, str]  # phase -> us | them | even | unknown
    reasons: dict[str, list[str]]  # phase -> why

    def first(self, side: str) -> str | None:
        """The first phase this side is favored in, or None."""
        return next((p for p in PHASES if self.phases.get(p) == side), None)


def lane_timeline(state: LaneState) -> LaneTimeline:
    us, them = state.us, state.them
    if state.diff is None:
        unknown = dict.fromkeys(PHASES, "unknown")
        return LaneTimeline(state.lane, unknown, {p: list(state.reasons) for p in PHASES})

    def spikes_at(side: SideView, levels: set[int]) -> list[Player]:
        return [p for p in side.players if levels & set(p.spikes)]

    def ult_threat(side: SideView) -> list[Player]:
        return [p for p in side.players if p.tags & ULT_TAGS]

    scores: dict[str, float] = {}
    reasons: dict[str, list[str]] = {p: [] for p in PHASES}
    for phase, levels in (("l1_3", {2}), ("l3_6", {3, 4, 5})):
        ours, theirs = spikes_at(us, levels), spikes_at(them, levels)
        scores[phase] = state.diff + 0.5 * (bool(ours) - bool(theirs))
        reasons[phase] += _spike_reasons(ours, theirs, levels)
    ours6, theirs6 = spikes_at(us, {6}), spikes_at(them, {6})
    ours_ult, theirs_ult = ult_threat(us), ult_threat(them)
    scores["post6"] = (0.5 * state.diff + 1.0 * (bool(ours6) - bool(theirs6))
                       + 0.5 * (bool(ours_ult) - bool(theirs_ult)))  # fmt: skip
    reasons["post6"] += _spike_reasons(ours6, theirs6, {6})
    scaling_diff = None
    if us.scaling is not None and them.scaling is not None:
        scaling_diff = us.scaling - them.scaling
        scores["item1"] = scaling_diff + 0.25 * state.diff

    phases: dict[str, str] = {}
    for phase in PHASES:
        score = scores.get(phase)
        at = ITEM_PHASE_AT if phase == "item1" else PHASE_AT
        if score is None:
            phases[phase] = "unknown"
        else:
            phases[phase] = "us" if score >= at else "them" if score <= -at else "even"
        if phase in ("l1_3", "l3_6") and phases[phase] != "even" and state.reasons:
            reasons[phase] = list(dict.fromkeys(reasons[phase] + state.reasons))
    if phases["item1"] in ("us", "them") and scaling_diff is not None:
        favored = us if phases["item1"] == "us" else them
        better_scaling = scaling_diff > 0 if phases["item1"] == "us" else scaling_diff < 0
        if better_scaling:
            reasons["item1"].append(favored.verb("scales better", "scale better"))
        else:
            reasons["item1"].append(favored.verb("keeps the early lead", "keep the early lead"))
    if state.shoved:
        # The side that gets shoved under tower isn't favored early, whatever its kill pressure.
        pusher = them if state.shoved == "us" else us
        why = pusher.verb("clears waves much faster", "clear waves much faster")
        for phase in ("l1_3", "l3_6"):
            if phases[phase] == state.shoved:
                phases[phase] = "even"
                reasons[phase] = [why]
    if state.source == "stats":
        # OP.GG's lane-advantage label decided who wins early: levels 1-3 and 3-6 follow it, so
        # the timeline can't say "you" while the verdict says "they win early" (the test game
        # bot_shove: Kog'Maw/Braum vs Sivir/Seraphine).
        side = {"winning": "us", "losing": "them", "even": "even"}[state.verdict]
        for phase in ("l1_3", "l3_6"):
            if phases[phase] != side:
                phases[phase] = side
                reasons[phase] = list(state.reasons)
    late = phases["item1"]
    if (late in ("us", "them") and phases["l1_3"] != late
            and any(r.endswith("the early lead") for r in reasons["item1"])):  # fmt: skip
        phases["item1"], reasons["item1"] = "even", []  # there's no early lead to keep
    return LaneTimeline(state.lane, phases, reasons)


def _spike_reasons(ours: list[Player], theirs: list[Player], levels: set[int]) -> list[str]:
    if bool(ours) == bool(theirs):
        return []
    who = ours or theirs
    when = f"level {min(levels)}" if len(levels) == 1 else "levels 3-5"
    return [f"{who[0].name} spikes at {when}"]
