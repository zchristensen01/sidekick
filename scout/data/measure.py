"""Figures measured from one ranked game's Match-V5 data (M19): no interpretation, just counts.

Per player (champion and role), against their lane opponent (the enemy with the same position):

| metric | what it counts |
|---|---|
| win | 1 if their team won |
| gold_diff_10, gold_diff_15 | their gold minus their lane opponent's, at 10 and 15 minutes |
| xp_diff_10, xp_diff_15 | the same for experience |
| cs_diff_10, cs_diff_15 | the same for minions plus monsters killed |
| cs_10 | minions plus monsters killed by 10 minutes |
| push_3_10 | share of minutes 3-10 they stood on the enemy's half of the map (laners) |
| level3_s, level4_s | seconds until they reached level 3 and level 4 |
| first_item_s | seconds until their first finished item (Riot's build depth 3, not boots) |
| takedowns_14 | kills plus assists before 14:00 |
| roam_takedowns_14 | kills plus assists before 14:00 on enemies outside their lane (laners) |
| kp_14 | their share of their team's kills before 14:00 (when the team has any) |
| deaths_14 | deaths before 14:00 |

"The enemy's half" uses no map constants: closer to the enemy team's spawn point than to their
own, both read from the timeline's first frame. Player identifiers are never read.
"""

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from scout.model.roles import LANE_ROLES, Role

POSITIONS = {"TOP": Role.TOP, "JUNGLE": Role.JUNGLE, "MIDDLE": Role.MID, "BOTTOM": Role.BOT,
             "UTILITY": Role.SUPPORT}  # fmt: skip
EARLY_MS = 14 * 60_000
MIN_GAME_S = 15 * 60  # shorter games (remakes, early surrenders) aren't measured


@dataclass
class PlayerFigures:
    champ_id: str
    role: Role
    figures: dict[str, float] = field(default_factory=dict)


def patch_of(match: Mapping[str, Any]) -> str:
    """'16.19' from gameVersion '16.19.712.3456'."""
    version = str((match.get("info") or {}).get("gameVersion") or "")
    return ".".join(version.split(".")[:2]) if version.count(".") >= 1 else ""


def measure(match: Mapping[str, Any], timeline: Mapping[str, Any], by_key: Mapping[int, str],
            finished_items: frozenset[int]) -> list[PlayerFigures]:  # fmt: skip
    info = match.get("info") or {}
    if int(info.get("gameDuration") or 0) < MIN_GAME_S:
        return []
    frames = list((timeline.get("info") or {}).get("frames") or [])
    if len(frames) < 11:
        return []
    seats: dict[int, tuple[int, Role, str, bool]] = {}  # pid -> team, role, champ, won
    for p in info.get("participants") or []:
        role = POSITIONS.get(str(p.get("teamPosition") or ""))
        champ = by_key.get(int(p.get("championId") or 0))
        pid = p.get("participantId")
        if role and champ and isinstance(pid, int):
            seats[pid] = (int(p.get("teamId") or 0), role, champ, bool(p.get("win")))
    if len(seats) != 10:
        return []  # a role missing (rare remake data): skip the game rather than guess
    by_seat = {(team, role): pid for pid, (team, role, _, _) in seats.items()}
    spawn = _spawns(frames[0], seats)
    if spawn is None:
        return []
    events = [e for f in frames for e in f.get("events") or [] if isinstance(e, dict)]
    kills = [e for e in events if e.get("type") == "CHAMPION_KILL"
             and int(e.get("timestamp") or 0) < EARLY_MS]  # fmt: skip
    out = []
    for pid, (team, role, champ, won) in seats.items():
        f: dict[str, float] = {"win": 1.0 if won else 0.0}
        enemy_team = next(t for t, _, _, _ in seats.values() if t != team)
        opp = by_seat.get((enemy_team, role))
        for minute in (10, 15):
            if minute < len(frames) and opp is not None:
                mine, theirs = _pf(frames[minute], pid), _pf(frames[minute], opp)
                f[f"gold_diff_{minute}"] = _num(mine, "totalGold") - _num(theirs, "totalGold")
                f[f"xp_diff_{minute}"] = _num(mine, "xp") - _num(theirs, "xp")
                f[f"cs_diff_{minute}"] = _cs(mine) - _cs(theirs)
        f["cs_10"] = _cs(_pf(frames[10], pid))
        if role is not Role.JUNGLE:
            away = [_on_enemy_half(_pf(frames[m], pid), spawn[team], spawn[enemy_team])
                    for m in range(3, 11)]  # fmt: skip
            seen = [a for a in away if a is not None]
            if seen:
                f["push_3_10"] = sum(seen) / len(seen)
        ups = {int(e.get("level") or 0): int(e["timestamp"]) for e in reversed(events)
               if e.get("type") == "LEVEL_UP" and e.get("participantId") == pid}  # fmt: skip
        for level in (3, 4):
            if level in ups:
                f[f"level{level}_s"] = ups[level] / 1000
        bought = next((int(e["timestamp"]) for e in events if e.get("type") == "ITEM_PURCHASED"
                       and e.get("participantId") == pid
                       and e.get("itemId") in finished_items), None)  # fmt: skip
        if bought is not None:
            f["first_item_s"] = bought / 1000
        mine_tk = [e for e in kills if e.get("killerId") == pid
                   or pid in (e.get("assistingParticipantIds") or [])]  # fmt: skip
        f["takedowns_14"] = len(mine_tk)
        f["deaths_14"] = sum(1 for e in kills if e.get("victimId") == pid)
        team_kills = sum(1 for e in kills if seats.get(e.get("killerId"), (0,))[0] == team)
        if team_kills:
            f["kp_14"] = len(mine_tk) / team_kills
        lane = next((ln for ln, roles in LANE_ROLES.items() if role in roles), None)
        if lane is not None:
            home = LANE_ROLES[lane]
            f["roam_takedowns_14"] = sum(
                1 for e in mine_tk if seats.get(e.get("victimId"), (0, None))[1] not in home
            )
        out.append(PlayerFigures(champ, role, f))
    return out


def _pf(frame: Mapping[str, Any], pid: int) -> Mapping[str, Any]:
    return (frame.get("participantFrames") or {}).get(str(pid)) or {}


def _num(pf: Mapping[str, Any], key: str) -> float:
    return float(pf.get(key) or 0)


def _cs(pf: Mapping[str, Any]) -> float:
    return _num(pf, "minionsKilled") + _num(pf, "jungleMinionsKilled")


def _spawns(frame: Mapping[str, Any], seats: Mapping[int, tuple[int, Role, str, bool]]
            ) -> dict[int, tuple[float, float]] | None:  # fmt: skip
    spots: dict[int, list[tuple[float, float]]] = {}
    for pid, (team, _, _, _) in seats.items():
        pos = _pf(frame, pid).get("position") or {}
        if "x" in pos and "y" in pos:
            spots.setdefault(team, []).append((float(pos["x"]), float(pos["y"])))
    if len(spots) != 2:
        return None
    return {t: (sum(x for x, _ in s) / len(s), sum(y for _, y in s) / len(s))
            for t, s in spots.items()}  # fmt: skip


def _on_enemy_half(pf: Mapping[str, Any], own: tuple[float, float],
                   enemy: tuple[float, float]) -> bool | None:  # fmt: skip
    pos = pf.get("position") or {}
    if "x" not in pos or "y" not in pos:
        return None
    here = (float(pos["x"]), float(pos["y"]))
    return math.dist(here, enemy) < math.dist(here, own)


def finished_items(rows: Sequence[Mapping[str, str]]) -> frozenset[int]:
    """Riot's finished items (build depth 3), boots excluded, from items.csv."""
    return frozenset(int(r["item_id"]) for r in rows
                     if r.get("depth") == "3" and r.get("boots") != "y")  # fmt: skip
