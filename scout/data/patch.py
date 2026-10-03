"""Patch and version labels.

Sources disagree on how to name a patch (checked 2026-10):
- Data Dragon version: "16.19.1"  (what we store)
- OP.GG label:         "16.19"    (Data Dragon major.minor)
- In-game / wiki:      "26.19" / "V26.19"

Since 2025 the in-game major is the year (25, 26, ...) and equals Data Dragon major + 10.
Before that (e.g. 14.x in 2024) both used the same number. Riot hasn't documented this, so it
lives only here. See docs/ARCHITECTURE.md.
"""

IN_GAME_MAJOR_OFFSET = 10
FIRST_YEAR_BASED_DDRAGON_MAJOR = 15  # Data Dragon 15.x = in-game 25.x (2025)


def _parts(version: str) -> tuple[int, ...]:
    try:
        parts = tuple(int(p) for p in version.strip().split("."))
    except ValueError:
        raise ValueError(f"not a version string: {version!r}") from None
    if len(parts) < 2:
        raise ValueError(f"not a version string: {version!r}")
    return parts


def previous_patch(patch: str) -> str:
    """'16.19' -> '16.18'; '17.1' -> '16.24' (Riot's patches run 1 to 24 a year)."""
    major, minor = (int(x) for x in patch.split(".")[:2])
    return f"{major}.{minor - 1}" if minor > 1 else f"{major - 1}.24"


def short_patch(version: str) -> str:
    """'16.19.1' -> '16.19' (the label OP.GG uses and the stats database stores)."""
    major, minor = _parts(version)[:2]
    return f"{major}.{minor}"


def display_patch(version: str) -> str:
    """'16.19.1' or '16.19' -> '26.19' (what players see in game). '14.5.1' -> '14.5'."""
    major, minor = _parts(version)[:2]
    if major >= FIRST_YEAR_BASED_DDRAGON_MAJOR:
        major += IN_GAME_MAJOR_OFFSET
    return f"{major}.{minor}"


def from_display_label(label: str) -> str:
    """In-game or wiki label -> short Data Dragon patch: 'V26.12' -> '16.12', 'V14.5' -> '14.5'."""
    major, minor = _parts(label.strip().lstrip("Vv"))[:2]
    if major >= FIRST_YEAR_BASED_DDRAGON_MAJOR + IN_GAME_MAJOR_OFFSET:
        major -= IN_GAME_MAJOR_OFFSET
    return f"{major}.{minor}"


def is_newer(a: str, b: str) -> bool:
    """True if version a is newer than version b ('16.19.1' vs '16.18.1')."""
    return _parts(a) > _parts(b)
