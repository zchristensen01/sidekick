"""Data Dragon (Riot's static CDN): versions, champions, abilities, summoner spells, items.

URLs, fields and traps: docs/DATA.md (Data Dragon). Parsers are tested against
tests/fixtures/sources/ddragon/.
"""

import html
import re
from dataclasses import dataclass
from typing import Any

BASE = "https://ddragon.leagueoflegends.com"
VERSIONS_URL = f"{BASE}/api/versions.json"
SLOTS = ("Q", "W", "E", "R")  # order of `spells` in championFull.json; the passive is "P"
SUMMONERS_RIFT = "11"
CLASSIC_MODE = "CLASSIC"
_VERSION = re.compile(r"\d+\.\d+\.\d+")


def champion_full_url(version: str) -> str:
    return f"{BASE}/cdn/{version}/data/en_US/championFull.json"


def summoner_url(version: str) -> str:
    return f"{BASE}/cdn/{version}/data/en_US/summoner.json"


def item_url(version: str) -> str:
    return f"{BASE}/cdn/{version}/data/en_US/item.json"


@dataclass(frozen=True)
class Ability:
    slot: str  # P, Q, W, E, R
    name: str
    max_rank: int | None  # None for the passive
    cooldowns: tuple[float, ...]  # one per rank; empty for the passive
    description: str  # Riot's text, HTML stripped


@dataclass(frozen=True)
class DdChampion:
    champ_id: str  # "LeeSin"
    key: int  # 64, the League client's championId
    name: str  # "Lee Sin"
    tags: tuple[str, ...]  # Riot's legacy classes: ("Fighter", "Assassin")
    abilities: tuple[Ability, ...]  # P, Q, W, E, R
    ally_tips: tuple[str, ...] = ()  # Riot's tips for playing this champion
    enemy_tips: tuple[str, ...] = ()  # Riot's tips for playing against it


def latest_version(versions: Any) -> str:
    """The newest real version in versions.json (it also lists old `lolpatch_*` entries)."""
    for version in versions if isinstance(versions, list) else []:
        if isinstance(version, str) and _VERSION.fullmatch(version):
            return version
    raise ValueError("versions.json has no version like 16.19.1")


def parse_champions(full: Any) -> dict[str, DdChampion]:
    """Champions by Data Dragon id from championFull.json. Mode-only entries are dropped."""
    champions: dict[str, DdChampion] = {}
    for champ_id, raw in (full.get("data") or {}).items():
        key = str(raw.get("key", ""))
        if not key.isdigit() or int(key) >= 60000 or champ_id.startswith("Jade_"):
            continue  # not a Summoner's Rift champion (e.g. Jade_* mode variants)
        passive = raw.get("passive") or {}
        abilities = [
            Ability(
                "P", str(passive.get("name", "")), None, (), clean_text(passive.get("description"))
            )
        ]
        for slot, spell in zip(SLOTS, raw.get("spells") or [], strict=False):
            cooldowns = tuple(float(c) for c in spell.get("cooldown") or [])
            max_rank = int(spell.get("maxrank") or len(cooldowns) or 0) or None
            abilities.append(
                Ability(
                    slot,
                    str(spell.get("name", "")),
                    max_rank,
                    cooldowns[:max_rank] if max_rank else cooldowns,
                    clean_text(spell.get("description")),
                )
            )
        champions[champ_id] = DdChampion(
            champ_id=champ_id,
            key=int(key),
            name=str(raw.get("name", champ_id)),
            tags=tuple(raw.get("tags") or ()),
            abilities=tuple(abilities),
            ally_tips=tips(raw.get("allytips")),
            enemy_tips=tips(raw.get("enemytips")),
        )
    return champions


SENTENCE_ENDS = (".", "!", "?", '"', "'", ")", "”", "’")


def tips(raw: Any) -> tuple[str, ...]:
    """Riot's tips, cleaned. Riot's data sometimes splits one tip around a keyword ("...If
    making a ", "Vessel", " is your goal..."): a piece that doesn't end a sentence and meets
    its neighbour at a space belongs with it, so they're joined back."""
    out: list[str] = []
    for piece in (t for t in raw or [] if isinstance(t, str) and t):
        seam = out and (out[-1].endswith(" ") or piece.startswith(" "))
        if seam and not out[-1].rstrip().endswith(SENTENCE_ENDS):
            out[-1] += piece
        else:
            out.append(piece)
    return tuple(t for t in (clean_text(x) for x in out) if t)


def parse_summoner_spells(summoner: Any) -> list[tuple[int, str, str]]:
    """(key, spell id, name) for Summoner's Rift spells, by numeric key (Smite is 11)."""
    spells = []
    for spell_id, raw in (summoner.get("data") or {}).items():
        if CLASSIC_MODE in (raw.get("modes") or []) and str(raw.get("key", "")).isdigit():
            spells.append((int(raw["key"]), spell_id, str(raw.get("name", spell_id))))
    return sorted(spells)


def parse_items(items: Any) -> list[tuple[int, str, int, int, bool]]:
    """(item id, name, total gold, build depth, boots?) for items you can buy on Summoner's
    Rift. Depth is Riot's own build-tree depth: 3 marks a finished item."""
    out = []
    for item_id, raw in (items.get("data") or {}).items():
        gold = raw.get("gold") or {}
        if (raw.get("maps") or {}).get(SUMMONERS_RIFT) and gold.get("purchasable"):
            depth = raw.get("depth") if isinstance(raw.get("depth"), int) else 1
            boots = "Boots" in (raw.get("tags") or [])
            out.append((int(item_id), str(raw.get("name", "")), int(gold.get("total") or 0),
                        depth, boots))  # fmt: skip
    return sorted(out)


def clean_text(text: Any) -> str:
    """Riot's ability text as one plain line: tags removed, entities decoded, spaces collapsed."""
    if not isinstance(text, str):
        return ""
    text = re.sub(r"<br\s*/?>", " ", text, flags=re.I)
    text = re.sub(r"<[^>]+>", "", text)
    return re.sub(r"\s+", " ", html.unescape(text)).strip()
