"""Threats: the ranked "don't let get fed" list of enemy champions, with reasons.

Enemy combos come from pair rules (scout/rules/league_rules.yaml, scope pair); cross-map
threats from scout/analysis/roam.py. docs/ROLES.md (Shared insights).
"""

from dataclasses import dataclass

from scout.analysis.players import Lineup, Player
from scout.model.roles import Role

SNOWBALL_CLASSES = frozenset({"assassin", "skirmisher", "diver"})
CARRY_ROLES = frozenset({Role.MID, Role.BOT})


@dataclass(frozen=True)
class Threat:
    player: Player
    score: float
    reasons: list[str]


def feed_ranking(lineup: Lineup) -> list[Threat]:
    """Enemy champions by how much damage an early lead does, biggest first."""
    threats = []
    for p in lineup.them.values():
        if not p.has_traits:
            continue
        score = 0.8 * (p.early or 0) + 0.6 * (p.scaling or 0)
        reasons = []
        if p.classes & SNOWBALL_CLASSES:
            score += 1.5
            reasons.append("snowballs off early kills")
        if p.role in CARRY_ROLES:
            score += 1.0
            reasons.append("carries fights with gold")
        if (p.scaling or 0) >= 3:
            reasons.append(f"scales hard ({p.scaling_note})" if p.scaling_note else "scales hard")
        if p.has("dive"):
            score += 0.5
            reasons.append("dives your backline")
        if (p.early or 0) >= 3:
            reasons.append("strong early")
        threats.append(Threat(p, round(score, 2), reasons))
    return sorted(threats, key=lambda t: -t.score)
