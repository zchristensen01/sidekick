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
| first_blood | 1 if they killed or helped kill in the game's first champion kill |
| solo_kills_14 | kills before 14:00 with nobody assisting |
| level2_s | seconds until they reached level 2 |
| level2_first | 1 if they reached level 2 before their lane opponent, 0 if after (laners) |
| plates_14 | plates of the enemy turret in their lane destroyed before 14:00 (laners) |
| gank_10 | 1 if they took part in killing an enemy laner before 10:00 (junglers) |
| first_gank_s | seconds until that first lane takedown, when there was one (junglers) |
| dragons_20, grubs_20 | dragons and voidgrubs their team took before 20:00 (junglers) |
| herald_20 | 1 if their team took the Rift Herald before 20:00 (junglers) |
| first_dragon | 1 if their team took the game's first dragon (junglers) |

Each player's lane opponent is kept too (`PlayerFigures.opp`), so the figures can be counted per
matchup as well (scout/data/stats_db.py `measured_matchups`, `MATCHUP_METRICS`).

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
GANK_MS = 10 * 60_000
OBJECTIVES_MS = 20 * 60_000
MIN_GAME_S = 15 * 60  # shorter games (remakes, early surrenders) aren't measured
LANE_TYPES = {Role.TOP: "TOP_LANE", Role.MID: "MID_LANE", Role.BOT: "BOT_LANE",
              Role.SUPPORT: "BOT_LANE"}  # Riot's laneType on turret events  # fmt: skip
# Counted per matchup too (champion vs lane opponent): the lane read's raw material
MATCHUP_METRICS = ("win", "gold_diff_10", "gold_diff_15", "xp_diff_10", "cs_diff_10",
                   "push_3_10", "solo_kills_14", "level2_first", "deaths_14")  # fmt: skip


@dataclass
class PlayerFigures:
    champ_id: str
    role: Role
    figures: dict[str, float] = field(default_factory=dict)
    opp: str = ""  # the lane opponent's champion (same position, other team)
    team: int = 0  # Riot's team id (100 or 200)


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
    all_kills = sorted((e for e in events if e.get("type") == "CHAMPION_KILL"),
                       key=lambda e: int(e.get("timestamp") or 0))  # fmt: skip
    kills = [e for e in all_kills if int(e.get("timestamp") or 0) < EARLY_MS]
    first_blood = all_kills[0] if all_kills else None
    monsters = [e for e in events if e.get("type") == "ELITE_MONSTER_KILL"]
    plates = [e for e in events if e.get("type") == "TURRET_PLATE_DESTROYED"
              and int(e.get("timestamp") or 0) < EARLY_MS]  # fmt: skip
    level2 = {int(e["participantId"]): int(e["timestamp"]) for e in reversed(events)
              if e.get("type") == "LEVEL_UP" and int(e.get("level") or 0) == 2
              and isinstance(e.get("participantId"), int)}  # fmt: skip
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
        if first_blood is not None:
            f["first_blood"] = 1.0 if _took_part(first_blood, pid) else 0.0
        f["solo_kills_14"] = sum(1 for e in kills if e.get("killerId") == pid
                                 and not e.get("assistingParticipantIds"))  # fmt: skip
        if pid in level2:
            f["level2_s"] = level2[pid] / 1000
        if role is Role.JUNGLE:
            f.update(_jungle(pid, team, seats, all_kills, monsters))
        else:
            if pid in level2 and opp in level2 and level2[pid] != level2[opp]:
                f["level2_first"] = 1.0 if level2[pid] < level2[opp] else 0.0
            f["plates_14"] = sum(1 for e in plates if e.get("teamId") == enemy_team
                                 and e.get("laneType") == LANE_TYPES[role])  # fmt: skip
        out.append(PlayerFigures(champ, role, f, seats[opp][2] if opp is not None else "", team))
    return out


def _took_part(kill: Mapping[str, Any], pid: int) -> bool:
    return kill.get("killerId") == pid or pid in (kill.get("assistingParticipantIds") or [])


def _jungle(pid: int, team: int, seats: Mapping[int, tuple[int, Role, str, bool]],
            kills: Sequence[Mapping[str, Any]],
            monsters: Sequence[Mapping[str, Any]]) -> dict[str, float]:  # fmt: skip
    """A jungler's first gank and their team's early objectives."""
    f: dict[str, float] = {}
    gank = next((e for e in kills if int(e.get("timestamp") or 0) < GANK_MS
                 and _took_part(e, pid)
                 and seats.get(e.get("victimId"), (team, Role.JUNGLE))[0] != team
                 and seats.get(e.get("victimId"), (team, Role.JUNGLE))[1] is not Role.JUNGLE),
                None)  # fmt: skip
    f["gank_10"] = 1.0 if gank is not None else 0.0
    if gank is not None:
        f["first_gank_s"] = int(gank.get("timestamp") or 0) / 1000
    early = [e for e in monsters if int(e.get("timestamp") or 0) < OBJECTIVES_MS
             and e.get("killerTeamId") == team]  # fmt: skip
    f["dragons_20"] = sum(1 for e in early if e.get("monsterType") == "DRAGON")
    f["grubs_20"] = sum(1 for e in early if e.get("monsterType") == "HORDE")
    f["herald_20"] = 1.0 if any(e.get("monsterType") == "RIFTHERALD" for e in early) else 0.0
    dragons = sorted((e for e in monsters if e.get("monsterType") == "DRAGON"),
                     key=lambda e: int(e.get("timestamp") or 0))  # fmt: skip
    if dragons:
        f["first_dragon"] = 1.0 if dragons[0].get("killerTeamId") == team else 0.0
    return f


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
