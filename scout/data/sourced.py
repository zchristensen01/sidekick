"""Sourced champion values (M15): Riot's and the LoL Wiki's facts in place of drafted notes.

The rule (2026-10-03): nothing about a champion is our own conclusion when a reputable source
says it. So, in memory (champion_traits.csv is never rewritten):

- `cc`, `escape`, `frontline` are Riot's own ratings (the client's playstyle info, via
  CommunityDragon): Control, Mobility, Toughness, each 1 Low / 2 Moderate / 3 High. `escape` is
  0 only when Riot rates mobility Low and the wiki lists no dash or blink at all.
- Tags `airborne` and `stealth` are the wiki's mechanic categories (Airborne = knock-up,
  knock-back, knock-aside or pull: the wiki's "Types of Crowd Control").
- Tag `needs_airborne` is Riot's ability text ("Blinks to an Airborne enemy champion").
- `scaling` comes from OP.GG's win rate by game length when the draft has it (per game, in
  scout/analysis/players.py).

- `early`, `waveclear` and `roam` come from Riot's match data where a champion has 50+ measured
  games in the role (M19, scout/analysis/measured.py, per game in players.py).

Everything else (engage, spikes, other tags, the notes) stays a drafted note until a source
exists. A row the owner wrote (`source=owner`) still wins over every source: the owner has the
final word (CLAUDE.md).
"""

import dataclasses
import re
from collections.abc import Iterable, Mapping

from scout.model.champ import Traits

AIRBORNE = frozenset({"knockup", "knockback", "knock_aside", "pull"})
MOVES = frozenset({"dash", "blink"})
NEEDS_AIRBORNE = re.compile(r"\ban Airborne enemy\b")
RATED = {"cc": "cc", "escape": "mobility", "frontline": "durability"}  # trait -> Riot rating
WIKI_TAGS = {"airborne": AIRBORNE, "stealth": frozenset({"stealth"})}
DRAFTED = ("early", "engage", "scaling", "roam", "waveclear", "spikes", "style", "key_note",
           "ult_note", "spike_note")  # fmt: skip


def apply(
    traits: Traits | None,
    mechanics: frozenset[str],
    ratings: Mapping[str, int],
    ability_texts: Iterable[str],
) -> Traits | None:
    """The traits with every sourced value filled in and each field's source recorded."""
    texts = [t for t in ability_texts if t]
    if traits is None and not (mechanics or ratings or texts):
        return None
    base = traits or Traits(source="sourced")
    drafted = base.source or "drafted"
    if base.source == "owner":
        return dataclasses.replace(base, sources=(("all", "owner"),))
    values: dict[str, object] = {}
    sources: dict[str, str] = {name: drafted for name in DRAFTED if _has(base, name)}
    for name, rating in RATED.items():
        level = ratings.get(rating)
        if level is None:
            if getattr(base, name) is not None:
                sources[name] = drafted
            continue
        values[name], sources[name] = level, "riot"
        if name == "escape" and level <= 1 and mechanics and not mechanics & MOVES:
            values[name], sources[name] = 0, "riot+wiki"
    tags = set(base.tags)
    for tag in tags:
        sources[f"tag:{tag}"] = drafted
    if mechanics:
        for tag, kinds in WIKI_TAGS.items():
            tags.discard(tag)
            if mechanics & kinds:
                tags.add(tag)
                sources[f"tag:{tag}"] = "wiki"
            else:
                sources.pop(f"tag:{tag}", None)
    if texts:
        tags.discard("needs_airborne")
        sources.pop("tag:needs_airborne", None)
        if any(NEEDS_AIRBORNE.search(t) for t in texts):
            tags.add("needs_airborne")
            sources["tag:needs_airborne"] = "riot"
    return dataclasses.replace(base, **values, tags=frozenset(tags),
                               sources=tuple(sorted(sources.items())))  # fmt: skip


def _has(traits: Traits, name: str) -> bool:
    value = getattr(traits, name)
    return value not in (None, "", ())
