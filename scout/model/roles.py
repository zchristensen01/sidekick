"""Roles, lanes and queues, and how the League client's names map onto them.

Internal names are used everywhere: roles `top, jungle, mid, bot, support` ("bot" is the ADC)
and lanes `top, mid, bot`. The League client says `middle`, `bottom`, `utility`; those are
mapped only here, at the edge. See docs/ROLES.md.
"""

from enum import StrEnum


class Role(StrEnum):
    TOP = "top"
    JUNGLE = "jungle"
    MID = "mid"
    BOT = "bot"
    SUPPORT = "support"


class Lane(StrEnum):
    TOP = "top"
    MID = "mid"
    BOT = "bot"


class Queue(StrEnum):
    NORMAL_DRAFT = "normal_draft"
    RANKED_SOLO = "ranked_solo"
    RANKED_FLEX = "ranked_flex"
    CLASH = "clash"
    OTHER = "other"


# Which lane each role plays in. The jungler has no lane.
ROLE_LANE: dict[Role, Lane | None] = {
    Role.TOP: Lane.TOP,
    Role.JUNGLE: None,
    Role.MID: Lane.MID,
    Role.BOT: Lane.BOT,
    Role.SUPPORT: Lane.BOT,
}

# Which roles play in each lane. Bot lane is a 2v2.
LANE_ROLES: dict[Lane, tuple[Role, ...]] = {
    Lane.TOP: (Role.TOP,),
    Lane.MID: (Role.MID,),
    Lane.BOT: (Role.BOT, Role.SUPPORT),
}

# League client `assignedPosition` values. Enemies always have "" (hidden).
LCU_POSITION_ROLE: dict[str, Role] = {
    "top": Role.TOP,
    "jungle": Role.JUNGLE,
    "middle": Role.MID,
    "bottom": Role.BOT,
    "utility": Role.SUPPORT,
}

# Draft queues with assigned positions, from Riot's queues.json
# (https://static.developer.riotgames.com/docs/lol/queues.json). Every other queue is OTHER
# and gets no report. See docs/LCU.md section 4.
QUEUE_BY_ID: dict[int, Queue] = {
    400: Queue.NORMAL_DRAFT,
    420: Queue.RANKED_SOLO,
    440: Queue.RANKED_FLEX,
    700: Queue.CLASH,
}


# Names for queues we skip, so the message says what was skipped. From Riot's queues.json
# (checked 2026-10-02). Anything else is shown by number.
SKIPPED_QUEUE_NAMES: dict[int, str] = {
    100: "ARAM", 450: "ARAM", 720: "ARAM Clash", 2400: "ARAM: Mayhem", 430: "Blind Pick",
    480: "Swiftplay", 490: "Quickplay", 900: "ARURF", 1900: "URF", 1700: "Arena",
    1710: "Arena", 2300: "Brawl",
}  # fmt: skip


def queue_label(queue_id: int | None) -> str:
    """'ARAM (queue 450)', 'custom game', or 'queue 1234'."""
    if queue_id is None or queue_id <= 0:
        return "a custom game"
    name = SKIPPED_QUEUE_NAMES.get(queue_id)
    return f"{name} (queue {queue_id})" if name else f"queue {queue_id}"


def lane_of(role: Role) -> Lane | None:
    """The lane a role plays in, or None for the jungler."""
    return ROLE_LANE[role]


def roles_in(lane: Lane) -> tuple[Role, ...]:
    """The roles that play in a lane (two for bot)."""
    return LANE_ROLES[lane]


def role_from_lcu(position: str) -> Role | None:
    """Map a League client position ("middle", "utility", ...) to a Role. "" or unknown -> None."""
    return LCU_POSITION_ROLE.get(position.strip().lower())


def queue_from_id(queue_id: int) -> Queue:
    """Map a League client queue id to a Queue. Unsupported queues are Queue.OTHER."""
    return QUEUE_BY_ID.get(queue_id, Queue.OTHER)


def has_positions(queue: Queue) -> bool:
    """True for the draft queues this app reports on."""
    return queue is not Queue.OTHER
