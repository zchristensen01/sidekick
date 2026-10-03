"""Grade a report's claims against the game's Match-V5 data (M10).

The measures follow the outside review's grading table (docs/TASKS.md M10). The thresholds
below say when a measurement counts as a hit: they're tuning knobs of ours, not League facts,
and the accuracy table is how they get checked. Positions use no map constants: "your half"
of a lane is being closer to your own team's spawn point than to theirs, both read from the
timeline's first frame (everyone starts in their fountain).
"""

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from scout.model.roles import LANE_ROLES, Lane, Role
from scout.postgame.claims import Claim

POSITIONS = {"TOP": Role.TOP, "JUNGLE": Role.JUNGLE, "MIDDLE": Role.MID, "BOTTOM": Role.BOT,
             "UTILITY": Role.SUPPORT}  # fmt: skip
GOLD_BAND = 500  # gold difference at 15 beyond which a lane counts as won or lost
LANE_MINUTE = 15
PRIO_MINUTES = range(3, 11)  # minutes 3-10: where the laners stood
VOLATILE_KILLS = 4  # lane kills + deaths before 14:00 that count as "high"
VOLATILE_BY_MS = 14 * 60_000
GANK_BY_MS = 10 * 60_000
START_MINUTE = 2
FED_SHARE = 0.24  # share of their team's gold at 15 (an even share is 0.20)
FED_KILLS = 3  # or this many kills by 15
LATE_GAME_S, SHORT_GAME_S = 35 * 60, 25 * 60


class MatchError(ValueError):
    """The match data isn't usable (wrong game, missing timeline)."""


@dataclass(frozen=True)
class Result:
    claim: Claim
    actual: str
    hit: bool | None  # None: this game can't test the claim
    measure: str  # plain words with the numbers


@dataclass
class Match:
    ours: int  # our team id (100 or 200)
    seats: dict[tuple[str, Role], int]  # (us | them, role) -> participant id
    champions: dict[int, str]  # participant id -> champion name (Riot's)
    keys: dict[int, int]  # participant id -> champion key
    won: bool
    duration_s: int
    frames: list[dict[str, Any]]
    events: list[dict[str, Any]]
    fountain: dict[str, tuple[float, float]]  # us | them -> spawn point


def read_match(match: Mapping[str, Any], timeline: Mapping[str, Any], my_key: int,
               my_role: Role) -> Match:  # fmt: skip
    """Find us by my champion; read every participant's team and position."""
    info = match.get("info") or {}
    people = [p for p in info.get("participants") or [] if isinstance(p, dict)]
    me = next((p for p in people if p.get("championId") == my_key), None)
    if me is None:
        raise MatchError("my champion isn't in this match")
    ours = me.get("teamId")
    seats, champions, keys = {}, {}, {}
    for p in people:
        role = POSITIONS.get(str(p.get("teamPosition") or ""))
        pid = p.get("participantId")
        if role is None or not isinstance(pid, int):
            continue
        side = "us" if p.get("teamId") == ours else "them"
        seats[(side, role)] = pid
        champions[pid] = str(p.get("championName") or "")
        keys[pid] = int(p.get("championId") or 0)
    frames = list((timeline.get("info") or {}).get("frames") or [])
    if len(frames) < 2:
        raise MatchError("the timeline has no frames")
    events = [e for f in frames for e in f.get("events") or [] if isinstance(e, dict)]
    fountain = {}
    for side in ("us", "them"):
        spots = [_position(frames[0], pid) for (s, _), pid in seats.items() if s == side]
        spots = [x for x in spots if x is not None]
        if not spots:
            raise MatchError("no starting positions in the timeline")
        n = len(spots)
        fountain[side] = (sum(x for x, _ in spots) / n, sum(y for _, y in spots) / n)
    return Match(ours, seats, champions, keys, bool(me.get("win")),
                 int(info.get("gameDuration") or 0), frames, events, fountain)  # fmt: skip


def grade(claims: Sequence[Claim], m: Match) -> list[Result]:
    """Grade claims against a match (the post-game check)."""
    return grade_outcome(claims, outcome(m))


def grade_outcome(claims: Sequence[Claim], out: Mapping[str, Any]) -> list[Result]:
    """Grade claims against an outcome record (outcome(), or one stored by the collector)."""
    graders = {"lane_winner": _lane_winner, "priority": _priority, "volatility": _volatility,
               "gank_lane": _gank_lane, "jungle_start": _jungle_start, "threat": _threat,
               "scaling": _scaling}  # fmt: skip
    results = []
    for claim in claims:
        found = graders.get(claim.kind)
        results.append(found(claim, out) if found else
                       Result(claim, "", None, "not checkable yet"))  # fmt: skip
    return results


def outcome(m: Match) -> dict[str, Any]:
    """What happened, from our side, as a small JSON-ready record: everything the graders read
    and nothing that identifies a player (the collector stores it for the backtest, M20)."""
    lanes = {}
    for lane in Lane:
        ours, theirs = _laners(m, lane, "us"), _laners(m, lane, "them")
        frame = _frame(m, LANE_MINUTE)
        home = total = 0
        for minute in PRIO_MINUTES:
            if minute >= len(m.frames):
                break
            for pid in ours:
                pos = _position(m.frames[minute], pid)
                if pos is not None:
                    total += 1
                    home += _own_half(m, pos)
        laners = set(ours + theirs)
        deaths = sum(1 for e in m.events if e.get("type") == "CHAMPION_KILL"
                     and int(e.get("timestamp") or 0) < VOLATILE_BY_MS
                     and e.get("victimId") in laners)  # fmt: skip
        lanes[lane.value] = {
            "gold_diff": _gold(m, frame, ours) - _gold(m, frame, theirs),
            "home": home, "total": total, "plates": _plates(m, lane), "deaths": deaths,
        }  # fmt: skip
    enemies = {}
    frame = _frame(m, LANE_MINUTE)
    team = [p for (s, _), p in m.seats.items() if s == "them"]
    team_gold = max(1, _gold(m, frame, team))
    by = LANE_MINUTE * 60_000
    for pid in team:
        kills = sum(1 for e in m.events if e.get("type") == "CHAMPION_KILL"
                    and e.get("killerId") == pid and int(e.get("timestamp") or 0) < by)  # fmt: skip
        enemies[m.champions.get(pid, "")] = {"share": _gold(m, frame, [pid]) / team_gold,
                                             "kills": kills}  # fmt: skip
    return {"won": m.won, "duration_s": m.duration_s,
            "minute": min(LANE_MINUTE, len(m.frames) - 1), "lanes": lanes,
            "gank": _first_gank(m), "start": _start_side(m), "enemies": enemies}  # fmt: skip


# ---------------------------------------------------------------- helpers


def _position(frame: Mapping[str, Any], pid: int) -> tuple[float, float] | None:
    p = (frame.get("participantFrames") or {}).get(str(pid)) or {}
    pos = p.get("position") or {}
    return (float(pos["x"]), float(pos["y"])) if "x" in pos and "y" in pos else None


def _frame(m: Match, minute: int) -> dict[str, Any]:
    return m.frames[min(minute, len(m.frames) - 1)]


def _gold(m: Match, frame: Mapping[str, Any], pids: Sequence[int]) -> int:
    pf = frame.get("participantFrames") or {}
    return sum(int((pf.get(str(pid)) or {}).get("totalGold") or 0) for pid in pids)


def _laners(m: Match, lane: Lane, side: str) -> list[int]:
    return [m.seats[(side, r)] for r in LANE_ROLES[lane] if (side, r) in m.seats]


def _own_half(m: Match, pos: tuple[float, float]) -> bool:
    return math.dist(pos, m.fountain["us"]) < math.dist(pos, m.fountain["them"])


def _lane_of(m: Match, pid: int) -> Lane | None:
    role = next((r for (_, r), p in m.seats.items() if p == pid), None)
    return next((lane for lane, roles in LANE_ROLES.items() if role in roles), None)


def _side_of(m: Match, pid: int) -> str:
    return next((s for (s, _), p in m.seats.items() if p == pid), "")


# ---------------------------------------------------------------- what happened


def _plates(m: Match, lane: Lane) -> dict[str, int]:
    name = {Lane.TOP: "TOP_LANE", Lane.MID: "MID_LANE", Lane.BOT: "BOT_LANE"}[lane]
    lost = {"us": 0, "them": 0}
    for e in m.events:
        if (e.get("type") == "TURRET_PLATE_DESTROYED" and e.get("laneType") == name
                and int(e.get("timestamp") or 0) < VOLATILE_BY_MS):  # fmt: skip
            lost["us" if e.get("teamId") == m.ours else "them"] += 1
    return lost


def _first_gank(m: Match) -> dict[str, Any] | None:
    """The first lane kill our jungler joined before 10:00: its lane and minute."""
    jungler = m.seats.get(("us", Role.JUNGLE))
    if jungler is None:
        return None
    for e in sorted((e for e in m.events if e.get("type") == "CHAMPION_KILL"),
                    key=lambda e: int(e.get("timestamp") or 0)):  # fmt: skip
        if int(e.get("timestamp") or 0) >= GANK_BY_MS:
            break
        helpers = e.get("assistingParticipantIds") or []
        victim = e.get("victimId")
        lane = _lane_of(m, victim) if isinstance(victim, int) else None
        if ((e.get("killerId") == jungler or jungler in helpers)
                and _side_of(m, victim) == "them" and lane is not None):  # fmt: skip
            return {"lane": lane.value, "minute": int(e.get("timestamp") or 0) // 60_000}
    return None


def _start_side(m: Match) -> str | None:
    jungler = m.seats.get(("us", Role.JUNGLE))
    pos = _position(_frame(m, START_MINUTE), jungler) if jungler else None
    if pos is None:
        return None
    top, bot = _corner(m, "top"), _corner(m, "bot")
    return "top" if math.dist(pos, top) < math.dist(pos, bot) else "bot"


def _corner(m: Match, side: str) -> tuple[float, float]:
    """The top-side and bottom-side corners, from the two spawn points (no map constants)."""
    (ax, ay), (bx, by) = m.fountain["us"], m.fountain["them"]
    lo_x, hi_x, lo_y, hi_y = min(ax, bx), max(ax, bx), min(ay, by), max(ay, by)
    return (lo_x, hi_y) if side == "top" else (hi_x, lo_y)


# ---------------------------------------------------------------- graders (on the outcome)

Out = Mapping[str, Any]


def _lane_winner(c: Claim, out: Out) -> Result:
    diff = int(out["lanes"][c.lane]["gold_diff"])
    actual = "us" if diff >= GOLD_BAND else "them" if diff <= -GOLD_BAND else "even"
    measure = f"gold difference at {out['minute']}: {diff:+,}"
    return Result(c, actual, actual == c.predicted, measure)


def _priority(c: Claim, out: Out) -> Result:
    lane = out["lanes"][c.lane]
    home, total = int(lane["home"]), int(lane["total"])
    if not total:
        return Result(c, "", None, "no positions in minutes 3-10")
    actual = "them" if home / total >= 0.5 else "us"  # mostly on our half: they had the wave
    plates = lane["plates"]
    measure = (f"your laners stood on your half {home} of {total} times in minutes 3-10; "
               f"plates lost before 14:00: you {plates['us']}, them {plates['them']}")
    return Result(c, actual, actual == c.predicted, measure)


def _volatility(c: Claim, out: Out) -> Result:
    kills = int(out["lanes"][c.lane]["deaths"])
    actual = "high" if kills >= VOLATILE_KILLS else "low"
    return Result(c, actual, actual == c.predicted, f"{kills} deaths in this lane before 14:00")


def _gank_lane(c: Claim, out: Out) -> Result:
    gank = out.get("gank")
    if not gank:
        return Result(c, "", None, "your jungler joined no lane kill before 10:00")
    measure = f"first kill your jungler joined: {gank['lane']}, minute {gank['minute']}"
    return Result(c, gank["lane"], gank["lane"] == c.predicted, measure)


def _jungle_start(c: Claim, out: Out) -> Result:
    side = out.get("start")
    if side is None:
        return Result(c, "", None, "no position at 2:00")
    return Result(c, side, side == c.predicted, f"your jungler was on the {side} side at 2:00")


def _threat(c: Claim, out: Out) -> Result:
    enemies = out.get("enemies") or {}
    found = next((v for name, v in enemies.items()
                  if name.lower() == c.subject.lower()
                  or name.replace(" ", "") == c.subject), None)  # fmt: skip
    if found is None:
        return Result(c, "", None, f"{c.subject} not found in the match")
    share, kills = float(found["share"]), int(found["kills"])
    fed = share >= FED_SHARE or kills >= FED_KILLS
    measure = f"{round(share * 100)}% of their team's gold at 15, {kills} kills by 15"
    return Result(c, "fed" if fed else "not fed", fed, measure)


def _scaling(c: Claim, out: Out) -> Result:
    duration = int(out["duration_s"])
    minutes = duration // 60
    winner = "us" if out["won"] else "them"
    if duration >= LATE_GAME_S:
        return Result(c, winner, winner == c.predicted, f"a {minutes}-minute game, {winner} won")
    if duration < SHORT_GAME_S:
        early = "them" if c.predicted == "us" else "us"
        return Result(c, winner, winner == early, f"a {minutes}-minute game, {winner} won")
    return Result(c, winner, None, f"a {minutes}-minute game: neither short nor long")
