"""Your champions per lane, each with a 1-5 comfort rating (M14).

Saved in pool.yaml next to config.yaml (gitignored: it's yours, and a friend has their own).
`scout pool` writes it; the app's Champions page keeps one list per account in pools/ and
starts a new account from this file (scout/accounts.py); pick suggestions read them.
Until pool.yaml exists, the old `player.champ_pool` lists in config.yaml are used, rated 3.

    jungle:
      LeeSin: 5
      Elise: 4
    support: {}
"""

import os
from collections.abc import Mapping, Sequence
from pathlib import Path

import yaml

from scout.model.roles import Role

Pool = dict[Role, dict[str, int]]
LOWEST, HIGHEST = 1, 5
DEFAULT_STARS = 3
HEADER = (
    "# Your champions per lane, each with a comfort rating: 1 = learning it, 5 = your main.\n"
    "# `scout pool` writes this file; the app's Champions page keeps one per account.\n"
    "# Champion names are Data Dragon ids (LeeSin, MonkeyKing for Wukong).\n"
)


class PoolError(ValueError):
    """pool.yaml is broken, with a message that says how to fix it."""


def parse_pool(raw: object) -> Pool:
    """{role: {champ_id: stars}} from the YAML; every role present, best rated first."""
    if raw is None:
        raw = {}
    if not isinstance(raw, dict):
        raise PoolError("pool.yaml must map lanes to champions, e.g. `jungle: {LeeSin: 5}`.")
    pool: Pool = {role: {} for role in Role}
    for name, champs in raw.items():
        try:
            role = Role(str(name))
        except ValueError:
            raise PoolError(
                f"pool.yaml: `{name}` isn't a lane (top, jungle, mid, bot, support)."
            ) from None
        if champs is None:
            continue
        if isinstance(champs, list):  # a plain list is fine: each champion gets the default
            champs = {c: DEFAULT_STARS for c in champs}
        if not isinstance(champs, dict):
            raise PoolError(f"pool.yaml: {role.value} must list champions with a 1-5 rating.")
        for champ, stars in champs.items():
            if not isinstance(champ, str) or not champ:
                raise PoolError(f"pool.yaml: {role.value} has a champion that isn't a name.")
            if isinstance(stars, bool) or not isinstance(stars, int):
                raise PoolError(f"pool.yaml: {role.value} {champ}: the rating must be 1-5.")
            pool[role][champ] = max(LOWEST, min(HIGHEST, stars))
    return {role: dict(ordered(champs)) for role, champs in pool.items()}


def ordered(champs: Mapping[str, int]) -> list[tuple[str, int]]:
    """Best rated first; ties keep their order."""
    return sorted(champs.items(), key=lambda item: -item[1])


def from_lists(lists: Mapping[Role, Sequence[str]]) -> Pool:
    """The old config.yaml lists, each champion rated the default."""
    return {role: {c: DEFAULT_STARS for c in lists.get(role, ())} for role in Role}


def load_pool(path: Path, fallback: Mapping[Role, Sequence[str]] | None = None) -> Pool:
    """pool.yaml if it exists, else `fallback` (config.yaml's lists). Raises PoolError."""
    if not path.exists():
        return from_lists(fallback or {})
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise PoolError(f"pool.yaml isn't valid YAML: {exc}") from None
    return parse_pool(raw)


def pool_text(pool: Mapping[Role, Mapping[str, int]]) -> str:
    lines = [HEADER.rstrip("\n")]
    for role in Role:
        champs = ordered(pool.get(role, {}))
        if not champs:
            lines.append(f"{role.value}: {{}}")
            continue
        lines.append(f"{role.value}:")
        lines += [f"  {champ}: {stars}" for champ, stars in champs]
    return "\n".join(lines) + "\n"


def save_pool(path: Path, pool: Mapping[Role, Mapping[str, int]]) -> None:
    """Write pool.yaml in one step (a crash never leaves half a file)."""
    text = pool_text(pool)
    parse_pool(yaml.safe_load(text))  # never write a file we couldn't read back
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + ".tmp")
    temp.write_text(text, encoding="utf-8", newline="\n")
    os.replace(temp, path)


def champion_lists(pool: Mapping[Role, Mapping[str, int]]) -> dict[Role, tuple[str, ...]]:
    """Just the champions per role, best rated first (for the nightly matchup refresh)."""
    return {role: tuple(c for c, _ in ordered(pool.get(role, {}))) for role in Role}
