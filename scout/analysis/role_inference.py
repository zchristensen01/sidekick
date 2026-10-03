"""Enemy role inference: which enemy champion plays which role.

Champ select hides enemy positions, so we score every way to give the locked enemy champions
the open roles: the product of each champion's rate for its role, with a floor so an off-role
pick is unlikely but possible. Normalized, the top assignment is the guess; per role, a
champion's probability is the sum over the assignments where it plays that role. Works for
partial teams (2 locked champions -> 20 assignments). docs/ROLES.md (Enemy roles and pick
order).

Role rates: OP.GG's role rates (share of a champion's games in each role, from lane meta);
champions OP.GG doesn't list yet (new ones) fall back to the wiki's position lists, where
Riot's in-client positions count double (docs/STATS.md, Stats vs traits).
"""

import itertools
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from scout.model.game import RoleAssignment
from scout.model.roles import Role

FLOOR = 0.005  # a champion's rate in a role it's never played in
TOP_ALTERNATIVES = 5
CLIENT_POSITION_WEIGHT = 2.0  # wiki: Riot's in-client positions vs stats sites' extra ones

RoleRates = Mapping[str, Mapping[Role, float]]


@dataclass(frozen=True)
class RoleGuess:
    best: dict[Role, str]  # role -> champ_id, for the locked champions
    alternatives: list[RoleAssignment]  # most likely first (the best one included)
    by_role: dict[
        Role, list[tuple[str, float]]
    ]  # role -> [(champ_id, probability)], likeliest first

    def confidence(self, role: Role) -> float:
        """Probability that the guessed champion really plays this role."""
        champ = self.best.get(role)
        return next((p for c, p in self.by_role.get(role, []) if c == champ), 0.0)

    def likely(self, role: Role, at_least: float) -> str | None:
        """The champion in this role if it's at least this likely, else None."""
        candidates = self.by_role.get(role, [])
        return candidates[0][0] if candidates and candidates[0][1] >= at_least else None


def infer_roles(
    champ_ids: Sequence[str],
    role_rates: RoleRates,
    open_roles: Sequence[Role] = tuple(Role),
    floor: float = FLOOR,
) -> RoleGuess:
    """Score every assignment of these champions to the open roles."""
    if len(champ_ids) > len(open_roles):
        raise ValueError(f"{len(champ_ids)} champions but only {len(open_roles)} open roles")
    if not champ_ids:
        return RoleGuess({}, [], {})
    scored: list[tuple[float, tuple[Role, ...]]] = []
    for roles in itertools.permutations(open_roles, len(champ_ids)):
        score = math.prod(
            max(role_rates.get(champ, {}).get(role, 0.0), floor)
            for champ, role in zip(champ_ids, roles, strict=True)
        )
        scored.append((score, roles))
    total = sum(score for score, _ in scored)
    # Ties keep a stable order: by role order, so the same draft always gives the same guess.
    scored.sort(key=lambda item: -item[0])

    by_role: dict[Role, dict[str, float]] = {role: {} for role in open_roles}
    for score, roles in scored:
        for champ, role in zip(champ_ids, roles, strict=True):
            by_role[role][champ] = by_role[role].get(champ, 0.0) + score / total

    def assignment(roles: tuple[Role, ...]) -> dict[Role, str]:
        return dict(
            sorted(zip(roles, champ_ids, strict=True), key=lambda pair: list(Role).index(pair[0]))
        )

    return RoleGuess(
        best=assignment(scored[0][1]),
        alternatives=[
            RoleAssignment(assignment(roles), score / total)
            for score, roles in scored[:TOP_ALTERNATIVES]
        ],
        by_role={
            role: sorted(probs.items(), key=lambda item: -item[1])
            for role, probs in by_role.items()
            if probs
        },
    )


def merged_rates(
    stats_rates: Mapping[str, Mapping[Role, float]],
    wiki_rates: Mapping[str, Mapping[Role, float]],
) -> dict[str, dict[Role, float]]:
    """OP.GG's rates for every champion it lists; the wiki prior for the rest."""
    merged = {c: dict(r) for c, r in wiki_rates.items()}
    merged.update({c: dict(r) for c, r in stats_rates.items() if r})
    return merged


def rates_from_wiki_positions(
    meta_rows: Sequence[Mapping[str, str]],
) -> dict[str, dict[Role, float]]:
    """Rough role rates from champion_meta.csv: every listed position, in-client ones double."""
    rates: dict[str, dict[Role, float]] = {}
    for row in meta_rows:
        listed = [Role(p) for p in row.get("positions", "").split("|") if p]
        client = {Role(p) for p in row.get("client_positions", "").split("|") if p}
        weights = {role: CLIENT_POSITION_WEIGHT if role in client else 1.0 for role in listed}
        total = sum(weights.values())
        if total:
            rates[row["champ_id"]] = {role: w / total for role, w in weights.items()}
    return rates
