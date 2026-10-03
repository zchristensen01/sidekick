"""CommunityDragon: melee/ranged, damage type, Riot's 1-3 playstyle ratings and difficulty.

Files are read from the folder for the current patch (e.g. `16.19/`), falling back to
`latest/` if that folder doesn't exist yet. Fields: docs/DATA.md (CommunityDragon). Tested
against tests/fixtures/sources/cdragon/.
"""

from dataclasses import dataclass
from typing import Any

BASE = "https://raw.communitydragon.org"
_GAME_DATA = "plugins/rcp-be-lol-game-data/global/default/v1"
DAMAGE_TYPES = {"kPhysical": "physical", "kMagic": "magic", "kMixed": "mixed"}
RATINGS = {  # our name -> playstyleInfo field
    "damage": "damage", "durability": "durability", "cc": "crowdControl",
    "mobility": "mobility", "utility": "utility",
}  # fmt: skip


def metadata_url(folder: str) -> str:
    return f"{BASE}/{folder}/content-metadata.json"


def champion_url(folder: str, key: int) -> str:
    return f"{BASE}/{folder}/{_GAME_DATA}/champions/{key}.json"


@dataclass(frozen=True)
class CdChampion:
    key: int
    champ_id: str  # `alias`, the Data Dragon id
    range_type: str | None  # melee | ranged
    damage_type: str | None  # physical | magic | mixed
    ratings: dict[str, int]  # damage, durability, cc, mobility, utility, difficulty


def parse_champion(raw: Any) -> CdChampion:
    tactical = raw.get("tacticalInfo") or {}
    playstyle = raw.get("playstyleInfo") or {}
    ratings = {
        ours: playstyle[theirs]
        for ours, theirs in RATINGS.items()
        if isinstance(playstyle.get(theirs), int)
    }
    if isinstance(tactical.get("difficulty"), int):
        ratings["difficulty"] = tactical["difficulty"]
    attack = str(tactical.get("attackType") or "").lower()
    return CdChampion(
        key=int(raw["id"]),
        champ_id=str(raw.get("alias", "")),
        range_type=attack if attack in ("melee", "ranged") else None,
        damage_type=DAMAGE_TYPES.get(str(tactical.get("damageType") or "")),
        ratings=ratings,
    )

