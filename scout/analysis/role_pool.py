"""Which roles a champion is really played in (M19): where OP.GG says at least 10% of its games
are. Data is kept, asked for and trusted only for those champion-role pairs; anything else (Jinx
top) is an off-role pick, and the report says honestly that there's no data for it.

OP.GG's role shares come from its lane meta (data/generated/stats.sqlite). A champion OP.GG
doesn't list yet (brand new) falls back to the LoL Wiki's positions.
"""

from collections.abc import Mapping, Sequence

from scout.model.roles import Role

ROLE_SHARE_MIN = 0.10  # share of the champion's games in that role


def roles_played(champ: str, shares: Mapping[str, Mapping[Role, float]],
                 wiki: Mapping[str, Sequence[Role]] | None = None) -> tuple[Role, ...]:  # fmt: skip
    """The champion's real roles, in role order (OP.GG first, the wiki's list as a fallback)."""
    found = shares.get(champ)
    if found:
        return tuple(r for r in Role if found.get(r, 0.0) >= ROLE_SHARE_MIN)
    return tuple(r for r in Role if r in (wiki or {}).get(champ, ()))


def share(champ: str, role: Role, shares: Mapping[str, Mapping[Role, float]]) -> float | None:
    """OP.GG's share of the champion's games in this role; None when OP.GG has no data."""
    found = shares.get(champ)
    return None if not found else float(found.get(role, 0.0))


def is_off_role(champ: str, role: Role, shares: Mapping[str, Mapping[Role, float]]) -> bool:
    """True only when OP.GG has the champion and under 10% of its games are in this role."""
    found = share(champ, role, shares)
    return found is not None and found < ROLE_SHARE_MIN
