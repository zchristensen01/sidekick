"""Counter-pick detection and the counter-pick block for the report.

Pick turns, outlook from shrunk matchup rates, specific counter vs weak patch, structural
fallback, role uncertainty. docs/COUNTERPICK.md, docs/STATS.md.

Labels: counter_picked (they locked after me, bad outlook, a specific counter), bad_draw (bad
outlook, but I picked into it or it isn't provably specific), weak_patch (bad outlook from
numbers, but no worse than both champions' overall strength predicts), even, you_countered (I
locked after them and it favors me), favorable, unknown.
"""

import dataclasses
from dataclasses import dataclass

from scout.analysis.lanes import LaneState
from scout.analysis.players import Player
from scout.analysis.stats import GameStats, MatchupStat
from scout.model.game import GameState

OUTLOOKS = ("favorable", "even", "soft_counter", "hard_counter", "unknown")
BAD = frozenset({"soft_counter", "hard_counter"})
ALTERNATIVE_AT = 0.15  # role-guess alternatives at least this likely get their own verdict
WORDS = {"favorable": "favorable", "even": "even", "soft_counter": "a slight disadvantage",
         "hard_counter": "a hard matchup", "unknown": "unknown"}  # fmt: skip


@dataclass(frozen=True)
class Bands:
    """config.yaml `counterpick` (percent) and `roles.low_confidence_below`."""

    favorable_at: float = 51.5
    even_from: float = 48.5
    soft_from: float = 46.5
    specific_delta: float = 1.5  # points worse than expected = a specific counter
    low_confidence: float = 0.6


DEFAULT_BANDS = Bands()


@dataclass(frozen=True)
class Alternative:
    name: str
    probability: float
    outlook: str
    display: str  # "" when there are no numbers for this pair


@dataclass(frozen=True)
class Verdict:
    me: Player
    opponent: Player
    confidence: float  # how sure we are the opponent plays my role
    picked_after_me: bool | None  # None: pick order unknown
    outlook: str
    specific: bool | None  # None: not knowable (structure only)
    label: str
    source: str  # opgg | structure | none
    display: str = ""  # "45% over 1,840 games"
    delta_display: str = ""
    previous_patch: bool = False
    flags: tuple[str, ...] = ()  # structural signals behind a structure verdict
    alternatives: tuple[Alternative, ...] = ()
    p_hat: float | None = None  # the shrunk matchup rate, when the numbers decided
    games: int | None = None


def outlook_from_rate(rate: float, bands: Bands) -> str:
    pct = rate * 100
    if pct >= bands.favorable_at:
        return "favorable"
    if pct >= bands.even_from:
        return "even"
    if pct >= bands.soft_from:
        return "soft_counter"
    return "hard_counter"


def label_for(outlook: str, specific: bool | None, picked_after_me: bool | None) -> str:
    if outlook == "unknown":
        return "unknown"
    if outlook in BAD:
        if specific is False:
            return "weak_patch"
        if specific and picked_after_me:
            return "counter_picked"
        return "bad_draw"
    if outlook == "favorable":
        return "you_countered" if picked_after_me is False else "favorable"
    return "even"


def structural_outlook(
    me: Player, opp: Player, lane: LaneState | None, jungle_diff: int | None
) -> tuple[str, tuple[str, ...]]:
    """A soft read from traits when the numbers are missing or thin (never `specific`)."""
    flags = []
    if lane is not None:
        if lane.range_mismatch and lane.them.range == "ranged" and lane.us.range == "melee":
            flags.append("ranged_into_melee")
        if (me.engage or 0) >= 3 and opp.tags & {"peel", "disengage"}:
            flags.append("engage_into_peel")
        if lane.verdict == "unknown":
            return "unknown", tuple(flags)
        diff = lane.diff or 0.0
        if lane.verdict == "winning":
            base = 0
        elif lane.verdict == "even":
            base = 1
        else:
            base = 3 if diff <= -3 else 2
    elif jungle_diff is not None:
        base = 0 if jungle_diff >= 1 else 1 if jungle_diff == 0 else 2 if jungle_diff == -1 else 3
    else:
        return "unknown", ()
    if lane is not None and lane.verdict == "losing" and diff <= -1.5:
        flags.append("loses_early")
    worse = base + sum(1 for f in flags if f != "loses_early")
    outlook = ("favorable", "even", "soft_counter", "hard_counter")[min(worse, 3)]
    return outlook, tuple(flags)


def counterpick(
    game: GameState,
    me: Player | None,
    opp: Player | None,
    stats: GameStats,
    lane: LaneState | None,
    jungle_diff: int | None,
    bands: Bands = DEFAULT_BANDS,
    names: dict[str, str] | None = None,
) -> Verdict | None:
    """The verdict for my matchup, or None if my lane opponent isn't known."""
    if me is None or opp is None:
        return None
    my_turn, opp_turn = me.pick_turn, opp.pick_turn
    after = None if my_turn is None or opp_turn is None else opp_turn > my_turn
    stat = stats.matchups.get(game.my_role)
    if stat is not None and stat.shown:
        outlook = outlook_from_rate(stat.rate, bands)
        delta_points = stat.delta * 100
        specific = delta_points <= -bands.specific_delta if outlook in BAD else None
        verdict = Verdict(
            me=me, opponent=opp, confidence=opp.confidence, picked_after_me=after,
            outlook=outlook, specific=specific, label=label_for(outlook, specific, after),
            source="opgg", display=stat.display, delta_display=_delta_text(delta_points),
            previous_patch=stat.mostly_previous, p_hat=stat.rate, games=stat.games,
        )  # fmt: skip
    else:
        outlook, flags = structural_outlook(me, opp, lane, jungle_diff)
        verdict = Verdict(
            me=me, opponent=opp, confidence=opp.confidence, picked_after_me=after,
            outlook=outlook, specific=None, label=label_for(outlook, None, after),
            source="structure" if outlook != "unknown" else "none", flags=flags,
        )  # fmt: skip
    if opp.confidence < bands.low_confidence:
        verdict = _with_alternatives(verdict, game, stats, bands, names or {})
    return verdict


def _with_alternatives(verdict: Verdict, game: GameState, stats: GameStats, bands: Bands,
                       names: dict[str, str]) -> Verdict:  # fmt: skip
    found = []
    for champ, probability in game.enemy_role_odds.get(game.my_role, []):
        if champ == verdict.opponent.champ_id or probability < ALTERNATIVE_AT:
            continue
        stat: MatchupStat | None = stats.alternatives.get(champ)
        if stat is not None and stat.shown:
            outlook = outlook_from_rate(stat.rate, bands)
            found.append(Alternative(names.get(champ, champ), probability, outlook, stat.display))
        else:
            found.append(Alternative(names.get(champ, champ), probability, "unknown", ""))
        if len(found) == 2:
            break
    return dataclasses.replace(verdict, alternatives=tuple(found))


def _delta_text(points: float) -> str:
    whole = round(abs(points))
    if whole < 1:
        return "about what both champions' overall strength predicts"
    worse = "worse" if points < 0 else "better"
    unit = "point" if whole == 1 else "points"
    return f"{whole} {unit} {worse} than both champions' overall strength predicts"


# ---------------------------------------------------------------- report text


def verdict_text(v: Verdict) -> str:
    """One line: the verdict with its evidence."""
    me, opp = v.me.name, v.opponent.name
    # A whole-game win rate, not a lane read: labelled so (review 2026-10-02).
    evidence = f" (game win rate {v.display})" if v.display else ""
    if v.source == "structure":
        why = ", ".join(FLAG_TEXT[f] for f in v.flags if f in FLAG_TEXT)
        evidence = " (no reliable numbers; going by champion notes" + (f": {why}" if why else "")
        evidence += ")"
    if v.label == "unknown":
        text = f"{me} vs {opp}: no reliable numbers and not enough champion notes for a verdict."
    elif v.label == "counter_picked":
        text = (f"Counter-picked: {opp} locked after you and is {WORDS[v.outlook]} for {me}"
                f"{evidence}, {v.delta_display}.")  # fmt: skip
    elif v.label == "bad_draw":
        when = " You picked into it, so it isn't a deliberate counter." if (
            v.picked_after_me is False) else ""  # fmt: skip
        text = f"Tough draw: {opp} is {WORDS[v.outlook]} for {me}{evidence}.{when}"
    elif v.label == "weak_patch":
        text = (f"{opp} isn't a special counter to {me}{evidence}: {v.delta_display}, so {me} is "
                "just weaker this patch.")  # fmt: skip
    elif v.label == "you_countered":
        text = f"You countered {opp}: {WORDS[v.outlook]} for {me}{evidence}."
    else:
        text = f"{me} vs {opp}: {WORDS[v.outlook]}{evidence}."
    for alt in v.alternatives:
        detail = f" (game win rate {alt.display})" if alt.display else ""
        text += (f" If {alt.name} is your laner instead ({round(alt.probability * 100)}% likely):"
                 f" {WORDS[alt.outlook]}{detail}.")  # fmt: skip
    return text


FLAG_TEXT = {
    "ranged_into_melee": "they're ranged into your melee",
    "engage_into_peel": "your engage runs into their peel",
    "loses_early": "you lose the early levels",
}
