"""The game being scouted: who picked what, in which role. See docs/ARCHITECTURE.md (Core types).

A GameState is built either from a live champ select session (scout/lcu/champselect.py, M4) or
from a hand-written fixture YAML (tests/fixtures/games/, M4). Everything downstream reads only this.
"""

from dataclasses import dataclass, field

from scout.model.roles import Lane, Queue, Role, lane_of


@dataclass(frozen=True)
class Pick:
    champ_id: str  # Data Dragon id, e.g. "LeeSin", "MonkeyKing" (Wukong)
    role: Role
    role_confidence: float = 1.0  # 1.0 for allies; inferred for enemies
    pick_turn: int | None = None  # draft turn this champion was locked in, if known
    spells: tuple[str, ...] = ()  # summoner spells, lowercase names ("flash", "ignite"); ()
    # until known: ours from champ select, theirs from the loading screen


@dataclass(frozen=True)
class RoleAssignment:
    """One plausible way to assign the enemy champions to roles."""

    roles: dict[Role, str]  # role -> champ_id
    probability: float


@dataclass
class GameState:
    ddragon_version: str  # e.g. "16.19.1"; display labels come from scout/data/patch.py
    queue: Queue
    my_role: Role
    ally: dict[Role, Pick]
    enemy: dict[Role, Pick]
    enemy_role_alternatives: list[RoleAssignment] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)  # e.g. "role swap detected"
    bans: list[str] = field(default_factory=list)
    # role -> [(champ_id, probability)], likeliest first; empty for hand-written games
    enemy_role_odds: dict[Role, list[tuple[str, float]]] = field(default_factory=dict)
    side: str = ""  # blue | red (our team's map side) | "" unknown

    @property
    def my_pick(self) -> Pick:
        return self.ally[self.my_role]

    @property
    def my_lane(self) -> Lane | None:
        return lane_of(self.my_role)

    def lane_opponent(self) -> Pick | None:
        """The enemy in my role (enemy support for a support, enemy jungler for a jungler)."""
        return self.enemy.get(self.my_role)
