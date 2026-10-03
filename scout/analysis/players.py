"""One champion in one seat, with the traits for the role it plays, and the two lineups.

Every insight reads these, so missing data has one meaning everywhere: a trait value of None
(no traits row, or a blank cell) makes any comparison that needs it false (docs/RULES.md).
"""

import dataclasses
from collections.abc import Iterable
from dataclasses import dataclass

from scout.analysis import role_pool
from scout.analysis.stats import GameStats, length_note, scaling_level
from scout.data.store import Knowledge, traits_for
from scout.model.game import GameState, Pick
from scout.model.roles import Lane, Role, roles_in

SCALES = ("early", "engage", "cc", "escape", "scaling", "roam", "waveclear", "frontline")


@dataclass(frozen=True)
class Player:
    champ_id: str
    name: str  # display name, e.g. "Wukong"
    role: Role
    side: str  # "us" or "them"
    confidence: float  # 1.0 for allies; the role guess for enemies
    pick_turn: int | None
    early: int | None
    engage: int | None
    cc: int | None
    escape: int | None
    scaling: int | None
    roam: int | None
    waveclear: int | None
    frontline: int | None
    spikes: tuple[int, ...]
    tags: frozenset[str]
    style: str
    range: str | None  # melee | ranged
    attack_range: float | None  # base attack range in game units
    move_speed: float | None
    range_varies: bool  # base range and range type disagree (form or level changes range)
    classes: frozenset[str]
    damage_type: str | None
    reviewed: bool
    has_traits: bool
    key_note: str
    ult_note: str
    spike_note: str
    spells: frozenset[str] = frozenset()  # summoner spells, when known
    sources: tuple[tuple[str, str], ...] = ()  # (field, source): Traits.sources, plus "opgg"
    scaling_note: str = ""  # OP.GG's game-length numbers, when they set `scaling`
    role_share: float | None = None  # OP.GG: share of this champion's games in this role
    off_role: bool = False  # under 10% of its games: there's no real data for it here
    measured: tuple[str, ...] = ()  # M19: figures from Riot's match data, as display strings
    measured_source: str = ""  # "Riot match data, Emerald+, patch 16.19, 1,240 games"
    measured_changes: tuple[str, ...] = ()  # what moved since last patch

    def has(self, tag: str) -> bool:
        return tag in self.tags

    def source_of(self, name: str) -> str:
        found = dict(self.sources)
        return found.get(name) or found.get("all") or "drafted"


@dataclass(frozen=True)
class Lineup:
    us: dict[Role, Player]
    them: dict[Role, Player]
    my_role: Role

    def side(self, side: str) -> dict[Role, Player]:
        return self.us if side == "us" else self.them

    def in_lane(self, side: str, lane: Lane) -> list[Player]:
        team = self.side(side)
        return [team[r] for r in roles_in(lane) if r in team]

    def players(self) -> Iterable[Player]:
        return [*self.us.values(), *self.them.values()]


MELEE_RANGE_UP_TO = 300  # base attack range at or below this reads as melee


def _range_varies(range_type: str | None, attack_range: float | None) -> bool:
    """True when the base range contradicts the range type (Gnar, Jayce: ranged in a form)."""
    if range_type is None or attack_range is None:
        return False
    return (range_type == "ranged") != (attack_range > MELEE_RANGE_UP_TO)


def build_lineup(game: GameState, knowledge: Knowledge) -> Lineup:
    def player(pick: Pick, side: str) -> Player:
        facts = knowledge.facts(pick.champ_id)
        traits = traits_for(knowledge.traits, pick.champ_id, pick.role)
        values = {name: getattr(traits, name) if traits else None for name in SCALES}
        return Player(
            champ_id=pick.champ_id,
            name=facts.name,
            role=pick.role,
            side=side,
            confidence=pick.role_confidence,
            pick_turn=pick.pick_turn,
            spells=frozenset(pick.spells),
            **values,
            spikes=traits.spikes if traits else (),
            tags=traits.tags if traits else frozenset(),
            style=traits.style if traits else "",
            range=facts.range_type,
            attack_range=facts.attack_range,
            move_speed=facts.move_speed,
            range_varies=_range_varies(facts.range_type, facts.attack_range),
            classes=facts.classes,
            damage_type=facts.damage_type,
            reviewed=bool(traits and traits.reviewed),
            has_traits=traits is not None,
            key_note=traits.key_note if traits else "",
            ult_note=traits.ult_note if traits else "",
            spike_note=traits.spike_note if traits else "",
            sources=traits.sources if traits else (),
        )

    return Lineup(
        us={role: player(pick, "us") for role, pick in game.ally.items()},
        them={role: player(pick, "them") for role, pick in game.enemy.items()},
        my_role=game.my_role,
    )


def with_role_shares(lineup: Lineup, stats: GameStats) -> Lineup:
    """Each pick's OP.GG role share; under 10% marks it off-role (M19: honest gaps)."""

    def one(p: Player) -> Player:
        found = role_pool.share(p.champ_id, p.role, stats.role_shares)
        if found is None:
            return p
        return dataclasses.replace(p, role_share=found,
                                   off_role=role_pool.is_off_role(p.champ_id, p.role,
                                                                  stats.role_shares))  # fmt: skip

    return dataclasses.replace(lineup, us={r: one(p) for r, p in lineup.us.items()},
                               them={r: one(p) for r, p in lineup.them.items()})  # fmt: skip


def _owner_row(p: Player) -> bool:
    """A row the owner wrote (source=owner): its values beat every source (TRAITS.md)."""
    return dict(p.sources).get("all") == "owner"


def with_measured(lineup: Lineup, stats: GameStats) -> Lineup:
    """Figures measured from Riot's match data set early, waveclear (lane push) and roam where
    there are enough games, replacing drafted values (M19), and travel as display strings."""

    def one(p: Player) -> Player:
        found = stats.measured.get((p.champ_id, p.role))
        if found is None:
            return p
        values = {name: found.levels[name] for name in ("early", "waveclear", "roam")
                  if name in found.levels and not _owner_row(p)}  # fmt: skip
        sources = dict(p.sources) | {name: "riot-measured" for name in values}
        return dataclasses.replace(p, **values, sources=tuple(sorted(sources.items())),
                                   measured=tuple(found.lines()),
                                   measured_source=found.source(),
                                   measured_changes=found.changes)  # fmt: skip

    return dataclasses.replace(lineup, us={r: one(p) for r, p in lineup.us.items()},
                               them={r: one(p) for r, p in lineup.them.items()})  # fmt: skip


def with_data_scaling(lineup: Lineup, stats: GameStats) -> Lineup:
    """OP.GG's win rate by game length sets `scaling` wherever the draft has it (M15: sourced
    over drafted), with the numbers kept for the report to quote."""

    def one(p: Player) -> Player:
        index, pair = stats.scaling.get(p.champ_id), stats.lengths.get(p.champ_id)
        if index is None or pair is None:
            return p
        if _owner_row(p):  # the owner's own value stays; OP.GG's numbers are still quoted
            return dataclasses.replace(p, scaling_note=length_note(*pair))
        sources = tuple(sorted((dict(p.sources) | {"scaling": "opgg"}).items()))
        return dataclasses.replace(p, scaling=scaling_level(index), sources=sources,
                                   scaling_note=length_note(*pair))  # fmt: skip

    return dataclasses.replace(lineup, us={r: one(p) for r, p in lineup.us.items()},
                               them={r: one(p) for r, p in lineup.them.items()})  # fmt: skip
