"""Everything we know about one champion, merged from generated and manual data.

Built by scout/data/store.py (M2-M3). Missing pieces stay None and are reported as warnings;
they never crash the pipeline. Field meanings: docs/TRAITS.md and docs/DATA.md.
"""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Traits:
    """One row of data/manual/champion_traits.csv (docs/TRAITS.md)."""

    early: int | None = None
    engage: int | None = None
    cc: int | None = None
    escape: int | None = None
    scaling: int | None = None
    roam: int | None = None
    waveclear: int | None = None
    frontline: int | None = None
    spikes: tuple[int, ...] = ()
    tags: frozenset[str] = frozenset()
    style: str = ""
    key_note: str = ""
    ult_note: str = ""
    spike_note: str = ""
    reviewed: bool = False
    reviewed_patch: str = ""
    source: str = ""
    # Where each value came from: (field, source) pairs, e.g. ("cc", "riot"), ("tag:airborne",
    # "wiki"), ("early", "llm"). Filled by scout/data/sourced.py; empty for a raw CSV row.
    sources: tuple[tuple[str, str], ...] = ()

    def source_of(self, name: str) -> str:
        """'riot', 'wiki', 'riot+wiki', 'opgg', 'owner', or the drafted row's source ('llm')."""
        found = dict(self.sources)
        return found.get(name) or found.get("all") or self.source or "drafted"


@dataclass(frozen=True)
class ChampFacts:
    champ_id: str
    name: str
    key: int  # numeric id used by the League client
    range_type: str | None = None  # melee | ranged
    attack_range: float | None = None  # base attack range (wiki)
    move_speed: float | None = None
    damage_type: str | None = None  # physical | magic | mixed
    classes: frozenset[str] = frozenset()  # Riot subclasses, e.g. {"diver"}
    traits: Traits | None = None  # None = no traits row yet
    mechanics: frozenset[str] = frozenset()  # the wiki's categories: {"knockup", "dash", ...}
    ratings: tuple[tuple[str, int], ...] = ()  # Riot's 1-3 ratings: ("cc", 3), ("mobility", 1)
    warnings: tuple[str, ...] = field(default=())
