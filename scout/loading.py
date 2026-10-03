"""Loading-screen addendum (M11): likely enemy duos and one-tricks, once, then stop.

The loading screen shows every player, so their recent public matches can be checked then
(docs/POLICY.md): two enemies who shared several recent ranked games on the same team are a
likely duo; an enemy whose champion is by far their most-played is a one-trick. Players the
game hides (streamer mode, no puuid) are skipped, never worked out from others. The output
names champions only; identifiers stay in memory and never reach the LLM or a file.
"""

import dataclasses
import itertools
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol

from scout.data.riot import RiotError
from scout.model.roles import Role

RECENT_MATCHES = 20  # recent ranked games checked per player
DUO_GAMES = 2  # shared games on the same team to call it a likely duo
MAX_DETAIL_CHECKS = 4  # match details fetched per pair at most
ONE_TRICK_SHARE = 3.0  # their champion has at least this many times the next one's points
ONE_TRICK_POINTS = 1_000_000  # or at least this many points on it


class Riot(Protocol):
    def account_puuid(self, game_name: str, tag_line: str) -> str | None: ...
    def match_ids(self, puuid: str, count: int = 20) -> list[str]: ...
    def match(self, match_id: str) -> dict[str, Any]: ...
    def top_mastery(self, puuid: str, count: int = 3) -> list[tuple[int, int]]: ...


@dataclass(frozen=True)
class Enemy:
    champion_key: int
    name: str  # champion display name
    role: Role | None
    puuid: str = field(repr=False)  # the client's id; the web API's after `resolve`
    riot_id: tuple[str, str] = field(default=("", ""), repr=False)  # (game name, tag line)


@dataclass(frozen=True)
class Addendum:
    duos: tuple[tuple[str, str], ...]  # champion names
    one_tricks: tuple[str, ...]
    hidden: int
    checked: int
    error: str = ""

    def lines(self) -> list[str]:
        if self.error:
            return [f"Loading screen check skipped: {self.error}."]
        out = []
        for a, b in self.duos:
            out.append(f"Their {a} and {b} have played several recent games together on the same "
                       "team: likely a duo, so expect them to move together.")  # fmt: skip
        for name in self.one_tricks:
            out.append(f"Their {name} player has far more games on {name} than on anything "
                       "else: expect them to know its limits well.")  # fmt: skip
        if self.hidden:
            out.append(f"{self.hidden} enemy player(s) are hidden by the game (streamer mode) and "
                       "weren't checked.")  # fmt: skip
        if not out:
            out.append(f"Loading screen: no likely duos or one-tricks among the {self.checked} "
                       "visible enemies.")  # fmt: skip
        return out


def enemies_at_loading(
    gameflow: Any, enemy_keys: Sequence[int], names: Mapping[int, str],
    roles: Mapping[int, Role],
) -> tuple[list[Enemy], int]:  # fmt: skip
    """(visible enemies, hidden count) from the gameflow session's loading roster. The enemy
    team is whichever side holds the enemy champions from champ select."""
    data = gameflow.get("gameData") if isinstance(gameflow, dict) else None
    if not isinstance(data, dict):
        return [], 0
    wanted = set(enemy_keys)
    for side in ("teamOne", "teamTwo"):
        team = [p for p in data.get(side) or [] if isinstance(p, dict)]
        if wanted and wanted <= {p.get("championId") for p in team}:
            visible = [Enemy(p["championId"], names.get(p["championId"], str(p["championId"])),
                             roles.get(p["championId"]), str(p["puuid"]))
                       for p in team if p.get("puuid")]  # fmt: skip
            return visible, len(team) - len(visible)
    return [], 0


def resolve(
    enemies: Sequence[Enemy],
    riot_id_of: Callable[[str], tuple[str, str] | None],
    riot: Riot,
) -> tuple[list[Enemy], int]:
    """Client ids -> Riot IDs (from the client) -> the web API's ids (Riot's account service).
    Returns the players it could resolve and how many it couldn't (counted as hidden)."""
    found = []
    for e in enemies:
        rid = riot_id_of(e.puuid)
        api = riot.account_puuid(*rid) if rid else None
        if rid and api:
            found.append(dataclasses.replace(e, puuid=api, riot_id=rid))
    return found, len(enemies) - len(found)


def check(riot: Riot, enemies: Sequence[Enemy], hidden: int) -> Addendum:
    try:
        histories = {e.puuid: riot.match_ids(e.puuid, RECENT_MATCHES) for e in enemies}
        details: dict[str, dict[str, Any]] = {}

        def same_team(match_id: str, a: str, b: str) -> bool:
            if match_id not in details:
                details[match_id] = riot.match(match_id)
            teams = {p.get("puuid"): p.get("teamId") for p in
                     (details[match_id].get("info") or {}).get("participants") or []}  # fmt: skip
            return a in teams and b in teams and teams[a] == teams[b]

        duos = likely_duos(enemies, histories, same_team)
        tricks = [e.name for e in enemies
                  if one_trick(riot.top_mastery(e.puuid, 3), e.champion_key)]  # fmt: skip
    except RiotError as exc:
        return Addendum((), (), hidden, len(enemies), str(exc))
    return Addendum(tuple(duos), tuple(tricks), hidden, len(enemies))


def likely_duos(
    enemies: Sequence[Enemy], histories: Mapping[str, Sequence[str]],
    same_team: Callable[[str, str, str], bool],
) -> list[tuple[str, str]]:  # fmt: skip
    found = []
    for a, b in itertools.combinations(enemies, 2):
        shared = [m for m in histories.get(a.puuid, ()) if m in set(histories.get(b.puuid, ()))]
        if len(shared) < DUO_GAMES:
            continue
        together = sum(1 for m in shared[:MAX_DETAIL_CHECKS] if same_team(m, a.puuid, b.puuid))
        if together >= DUO_GAMES:
            found.append((a.name, b.name))
    return found


def one_trick(top: Sequence[tuple[int, int]], playing: int) -> bool:
    """Their champion is their most-played by a wide margin (champion experience, not skill)."""
    if not top or top[0][0] != playing:
        return False
    points = top[0][1]
    second = top[1][1] if len(top) > 1 else 0
    return points >= ONE_TRICK_POINTS or (second > 0 and points >= ONE_TRICK_SHARE * second)
