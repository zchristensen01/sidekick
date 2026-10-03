"""Team profile: damage split, engagers, frontline, hard CC, comp type, early vs late.

docs/ROLES.md (Shared insights). Counts use traits (engage, frontline, cc) and static data
(damage type, Riot classes). `frontline` and `cc` are Riot's own ratings (scout/data/sourced.py:
1 Low, 2 Moderate, 3 High): a frontliner is a champion Riot rates High on toughness (Moderate
includes the likes of Evelynn and Samira); "hard CC" counts Moderate or High control.
"""

from collections import Counter
from dataclasses import dataclass, field

from scout.analysis.players import Lineup, Player

ENGAGER_AT, FRONTLINE_AT, HARD_CC_AT = 2, 3, 2


@dataclass(frozen=True)
class TeamProfile:
    side: str
    early: float | None  # mean early of the champions with traits
    scaling: float | None
    n_engagers: int
    n_frontline: int
    n_hard_cc: int
    classes: Counter[str]
    damage: Counter[str]  # physical / magic / mixed
    archetype: str  # engage | poke | pick | split | protect | mixed
    reasons: list[str] = field(default_factory=list)


def team_profile(lineup: Lineup, side: str) -> TeamProfile:
    players = list(lineup.side(side).values())

    def mean(name: str) -> float | None:
        values = [getattr(p, name) for p in players if getattr(p, name) is not None]
        return round(sum(values) / len(values), 2) if values else None

    def count(test) -> int:
        return sum(1 for p in players if test(p))

    engagers = count(lambda p: (p.engage or 0) >= ENGAGER_AT or p.has("ult_engage"))
    frontline = count(lambda p: (p.frontline or 0) >= FRONTLINE_AT)
    hard_cc = count(lambda p: (p.cc or 0) >= HARD_CC_AT)
    classes = Counter(c for p in players for c in p.classes)
    damage = Counter(p.damage_type for p in players if p.damage_type)
    tags = Counter(t for p in players for t in p.tags)
    archetype = _archetype(engagers, tags, players)
    return TeamProfile(side, mean("early"), mean("scaling"), engagers, frontline, hard_cc,
                       classes, damage, archetype)  # fmt: skip


def _archetype(engagers: int, tags: Counter[str], players: list[Player]) -> str:
    if engagers >= 3:
        return "engage"
    if tags["poke"] >= 2:
        return "poke"
    if tags["split_push"] >= 1 and engagers <= 1:
        return "split"
    if tags["peel"] >= 2:
        return "protect"
    if sum(1 for p in players if "catcher" in p.classes or p.has("point_click_cc")) >= 2:
        return "pick"
    return "mixed"
