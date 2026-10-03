"""Roams and cross-map reach.

- roam: the mid and support roam threat on both teams, and each roamer's best target.
- cross_map: champions whose ult or roaming reaches other lanes (`ult_join`, `global`, high
  `roam`), which lanes, and from when (docs/KNOWLEDGE.md, Cross-map threats).
"""

from dataclasses import dataclass

from scout.analysis.ganks import Gank
from scout.analysis.players import Lineup, Player
from scout.model.roles import Lane, Role, lane_of

ROAMS_EVERYWHERE_AT = 3  # roam trait that reaches other lanes early


@dataclass(frozen=True)
class Roam:
    player: Player
    score: float | None  # roam, plus half of waveclear for mids (they push, then leave)
    target: Lane | None  # the most gankable side lane of the other team


def roams(lineup: Lineup, ganks: dict[Lane, Gank]) -> dict[str, dict[Role, Roam]]:
    out: dict[str, dict[Role, Roam]] = {"us": {}, "them": {}}
    for side in ("us", "them"):
        for role in (Role.MID, Role.SUPPORT):
            player = lineup.side(side).get(role)
            if player is None:
                continue
            score = None
            if player.roam is not None:
                score = float(player.roam)
                if role is Role.MID and player.waveclear is not None:
                    score += 0.5 * player.waveclear
            side_lanes = [lane for lane in (Lane.TOP, Lane.BOT, Lane.MID) if lane != lane_of(role)]

            def gankable(lane: Lane, side: str = side) -> float:
                g = ganks.get(lane)
                value = (g.on_them if side == "us" else g.on_us) if g else None
                return value if value is not None else -1.0

            target = max(side_lanes, key=gankable)
            out[side][role] = Roam(player, score, target if gankable(target) >= 0 else None)
    return out


@dataclass(frozen=True)
class Reach:
    player: Player
    kind: str  # ult_join | global | roam
    lanes: tuple[Lane, ...]  # lanes they can reach (not their own)
    when: str  # "after 6" or "early"


def cross_map(lineup: Lineup) -> dict[str, list[Reach]]:
    out: dict[str, list[Reach]] = {"us": [], "them": []}
    for player in lineup.players():
        home = lane_of(player.role)
        others = tuple(lane for lane in Lane if lane != home)
        if player.has("ult_join"):
            out[player.side].append(Reach(player, "ult_join", others, "after 6"))
        elif player.has("global"):
            out[player.side].append(Reach(player, "global", others, "after 6"))
        elif (player.roam or 0) >= ROAMS_EVERYWHERE_AT and player.role is not Role.JUNGLE:
            out[player.side].append(Reach(player, "roam", others, "early"))
    return out


def reaching(reach: dict[str, list[Reach]], side: str, lane: Lane) -> list[Player]:
    return [r.player for r in reach[side] if lane in r.lanes]
