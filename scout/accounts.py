"""Each League account on this PC keeps its own champions (M22).

The League client says who is logged in (read-only: /lol-summoner/v1/current-summoner), and
Sidekick keeps that account's champions in a file of its own:

    pools/accounts.yaml   whose file is whose, the account seen last, and the suggestions
                          you said no to (the app writes it)
    pools/Name_TAG.yaml   one account's champions, in pool.yaml's format

The account's puuid (Riot's id for an account) is the key, so a Riot ID change keeps the list.
An account Sidekick hasn't seen before starts from a copy of pool.yaml: the list from before
accounts had their own (empty on a new install). pool.yaml itself stays for the offline
commands (`scout pool`, `scout report`). Only your own account is read; `pools/` is gitignored.

The Champions page also suggests champions from your own games:
- recent games: a champion you played in the same lane at least RECENT_MIN times in the
  client's recent match history, not in that lane's list yet;
- mastery: your most-played champions that aren't in any lane's list, each with the lane
  it's played in most (OP.GG's role rates).
Either kind can be turned down; a "no" is remembered per account and lane.
"""

import os
import re
import threading
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from scout.model.roles import Role
from scout.pool import Pool, PoolError, load_pool, save_pool

INDEX = "accounts.yaml"
INDEX_HEADER = (
    "# The League accounts Sidekick has seen on this PC, each with its own champions file.\n"
    "# The app writes this; `declined` holds the suggestions you said no to.\n"
)
RECENT_MIN = 4  # 2026-10-03: suggest a champion once it's played "more than 3 times"
MASTERY_IDEAS = 10  # at most this many mastery suggestions at once
SUMMONERS_RIFT = 11  # the client's map id for Summoner's Rift
# The client's match history follows Riot's match-v4 format: `timeline.lane` is TOP, JUNGLE,
# MIDDLE (or MID), BOTTOM (or BOT); `timeline.role` is SOLO, NONE, DUO, DUO_CARRY, DUO_SUPPORT.
LANES = {"TOP": Role.TOP, "JUNGLE": Role.JUNGLE, "MIDDLE": Role.MID, "MID": Role.MID}
BOTTOM = frozenset({"BOTTOM", "BOT"})
Idea = tuple[Role, str, int]  # (lane, champion id, games played or mastery points)


@dataclass(frozen=True)
class Account:
    puuid: str
    riot_id: str  # "Name#TAG", for people to read


def logged_in(raw: object) -> Account | None:
    """The account in the client's current-summoner answer; None if it has no puuid."""
    if not isinstance(raw, dict):
        return None
    puuid = raw.get("puuid")
    if not isinstance(puuid, str) or not puuid:
        return None
    name, tag = raw.get("gameName"), raw.get("tagLine")
    riot_id = f"{name}#{tag}" if name and tag else str(raw.get("displayName") or "your account")
    return Account(puuid, riot_id)


def file_name(riot_id: str, taken: set[str]) -> str:
    """'Name#TAG' -> 'Name_TAG.yaml', not clashing with `taken` (lower-case names)."""
    stem = re.sub(r"[^\w-]+", "_", riot_id).strip("_") or "account"
    name, n = f"{stem}.yaml", 2
    while name.lower() in taken or name.lower() == INDEX:  # Windows ignores case in names
        name, n = f"{stem}_{n}.yaml", n + 1
    return name


class Accounts:
    """The pools/ folder. One instance is shared by the app's threads."""

    def __init__(self, folder: Path) -> None:
        self.folder = folder
        self._lock = threading.Lock()

    # ------------------------------------------------------------ the index

    def _read(self) -> dict[str, Any]:
        path = self.folder / INDEX
        try:
            raw = yaml.safe_load(path.read_text(encoding="utf-8")) if path.exists() else None
        except yaml.YAMLError as exc:
            raise PoolError(f"pools/{INDEX} isn't valid YAML: {exc}") from None
        index = raw if isinstance(raw, dict) else {}
        accounts = index.get("accounts") if isinstance(index.get("accounts"), dict) else {}
        index["accounts"] = {str(k): v for k, v in accounts.items() if isinstance(v, dict)}
        return index

    def _write(self, index: dict[str, Any]) -> None:
        self.folder.mkdir(parents=True, exist_ok=True)
        text = INDEX_HEADER + yaml.safe_dump(index, sort_keys=False, allow_unicode=True)
        path = self.folder / INDEX
        temp = path.with_name(path.name + ".tmp")
        temp.write_text(text, encoding="utf-8", newline="\n")
        os.replace(temp, path)  # a crash never leaves half a file

    def _entry(self, account: Account) -> dict[str, Any]:
        entry = self._read()["accounts"].get(account.puuid)
        if entry is None or not entry.get("file"):
            raise PoolError(f"Sidekick hasn't seen {account.riot_id} logged in yet.")
        return entry

    # ------------------------------------------------------------ accounts

    def remember(self, account: Account, starting: Callable[[], Pool]) -> None:
        """Note the logged-in account: its file (made from `starting()` the first time), its
        current Riot ID, and that it's the last one seen."""
        with self._lock:
            index = self._read()
            entry = index["accounts"].get(account.puuid) or {}
            changed = not entry.get("file")
            if changed:
                taken = {str(e.get("file", "")).lower() for e in index["accounts"].values()}
                entry = {"riot_id": account.riot_id, "file": file_name(account.riot_id, taken),
                         "declined": {}}  # fmt: skip
                index["accounts"][account.puuid] = entry
            path = self.folder / str(entry["file"])
            if not path.exists():
                save_pool(path, starting())
            if entry.get("riot_id") != account.riot_id or index.get("last") != account.puuid:
                entry["riot_id"], index["last"] = account.riot_id, account.puuid
                changed = True
            if changed:
                self._write(index)

    def get(self, puuid: str) -> Account | None:
        """A remembered account by its puuid."""
        entry = self._read()["accounts"].get(puuid)
        return Account(puuid, str(entry.get("riot_id") or "")) if entry else None

    def last(self) -> Account | None:
        """The account seen last (the Champions page shows it while the client is closed)."""
        last = self._read().get("last")
        return self.get(str(last)) if last else None

    # ------------------------------------------------------------ champions

    def path(self, account: Account) -> Path:
        return self.folder / str(self._entry(account)["file"])

    def load(self, account: Account) -> Pool:
        return load_pool(self.path(account))

    def save(self, account: Account, pool: Pool) -> None:
        with self._lock:
            save_pool(self.path(account), pool)

    def every_pool(self) -> list[Pool]:
        """Every account's champions (the nightly matchup refresh covers them all)."""
        pools = []
        for entry in self._read()["accounts"].values():
            path = self.folder / str(entry.get("file", ""))
            if entry.get("file") and path.exists():
                pools.append(load_pool(path))
        return pools

    # ------------------------------------------------------------ suggestions said no to

    def declined(self, account: Account) -> set[tuple[Role, str]]:
        found = set()
        raw = self._entry(account).get("declined")
        for role in Role:
            champs = raw.get(role.value) if isinstance(raw, dict) else None
            if isinstance(champs, list):
                found |= {(role, str(c)) for c in champs}
        return found

    def decline(self, account: Account, role: Role, champ: str) -> None:
        with self._lock:
            index = self._read()
            entry = index["accounts"].get(account.puuid)
            if entry is None:
                raise PoolError(f"Sidekick hasn't seen {account.riot_id} logged in yet.")
            declined = entry.get("declined") if isinstance(entry.get("declined"), dict) else {}
            champs = declined.get(role.value) if isinstance(declined.get(role.value), list) else []
            if champ not in champs:
                declined[role.value] = sorted([*champs, champ])
            entry["declined"] = declined
            self._write(index)


def merged(pools: Sequence[Mapping[Role, Mapping[str, int]]]) -> Pool:
    """Several lists as one: every champion in each lane, at its highest rating."""
    out: Pool = {role: {} for role in Role}
    for pool in pools:
        for role, champs in pool.items():
            for champ, stars in champs.items():
                out[role][champ] = max(stars, out[role].get(champ, 0))
    return out


# ---------------------------------------------------------------- suggestions


def recent_games(raw: object) -> list[dict[str, Any]] | None:
    """The games in the client's match-history answer; None if it isn't shaped as expected."""
    games = raw.get("games") if isinstance(raw, dict) else None
    if isinstance(games, dict):  # {"games": {"games": [...]}}
        games = games.get("games")
    return [g for g in games if isinstance(g, dict)] if isinstance(games, list) else None


def platform_of(games: Sequence[Mapping[str, Any]]) -> str | None:
    """The server of my recent games: their most common `platformId` (match-v4: "NA1"), in
    lower case as Riot's API names platforms ("na1"); None without games."""
    found = Counter(str(g["platformId"]).lower() for g in games if g.get("platformId"))
    return found.most_common(1)[0][0] if found else None


def _mine(game: Mapping[str, Any], puuid: str) -> Mapping[str, Any] | None:
    """My row in one game: by my puuid, or the only row (the client lists just mine)."""
    rows = [p for p in game.get("participants") or [] if isinstance(p, dict)]
    for ident in game.get("participantIdentities") or []:
        player = ident.get("player") if isinstance(ident, dict) else None
        if isinstance(player, dict) and player.get("puuid") == puuid:
            mine = ident.get("participantId")
            return next((p for p in rows if p.get("participantId") == mine), None)
    return rows[0] if len(rows) == 1 else None


def _lane(timeline: object, champ: str, rates: Mapping[str, Mapping[Role, float]]) -> Role | None:
    """The lane the client says I played; when it can't say, the lane the champion is
    played in most (OP.GG), for a bottom-lane game between bot and support."""
    lane = role = ""
    if isinstance(timeline, dict):
        lane, role = str(timeline.get("lane") or "").upper(), str(timeline.get("role") or "")
    if lane in LANES:
        return LANES[lane]
    choices: tuple[Role, ...] = tuple(Role)
    if lane in BOTTOM:
        if role.upper() == "DUO_SUPPORT":
            return Role.SUPPORT
        if role.upper() == "DUO_CARRY":
            return Role.BOT
        choices = (Role.BOT, Role.SUPPORT)
    shares = rates.get(champ, {})
    best = max(choices, key=lambda r: shares.get(r, 0.0))
    return best if shares.get(best, 0.0) > 0 else None


def recent_counts(
    games: Sequence[Mapping[str, Any]],
    puuid: str,
    by_key: Mapping[int, str],
    rates: Mapping[str, Mapping[Role, float]],
) -> tuple[Counter[tuple[Role, str]], int]:
    """(lane, champion) -> games, and how many games counted: my own Summoner's Rift games
    (normal and ranked; not ARAM, Arena, rotating modes or custom games)."""
    counts: Counter[tuple[Role, str]] = Counter()
    counted = 0
    for game in games:
        if (game.get("mapId") != SUMMONERS_RIFT or game.get("gameMode") != "CLASSIC"
                or game.get("gameType") == "CUSTOM_GAME"):  # fmt: skip
            continue
        me = _mine(game, puuid)
        champ = by_key.get(me.get("championId")) if me is not None else None
        lane = _lane(me.get("timeline"), champ, rates) if me is not None and champ else None
        if champ and lane:
            counts[(lane, champ)] += 1
            counted += 1
    return counts, counted


def recent_ideas(
    counts: Mapping[tuple[Role, str], int],
    pool: Mapping[Role, Mapping[str, int]],
    declined: set[tuple[Role, str]],
    minimum: int = RECENT_MIN,
) -> list[Idea]:
    """Champions played at least `minimum` times in a lane, not in that lane's list and not
    turned down there; most played first."""
    found = [(role, champ, n) for (role, champ), n in counts.items()
             if n >= minimum and champ not in pool.get(role, {})
             and (role, champ) not in declined]  # fmt: skip
    return sorted(found, key=lambda idea: (-idea[2], idea[1]))


def mastery_ideas(
    mastery: Sequence[tuple[str, int]],
    rates: Mapping[str, Mapping[Role, float]],
    pool: Mapping[Role, Mapping[str, int]],
    declined: set[tuple[Role, str]],
    limit: int = MASTERY_IDEAS,
) -> list[Idea]:
    """Most mastery points first: champions in no lane's list yet, each with the lane it's
    played in most (OP.GG), unless turned down for that lane."""
    listed = {champ for champs in pool.values() for champ in champs}
    found: list[Idea] = []
    for champ, points in sorted(mastery, key=lambda m: -m[1]):
        shares = rates.get(champ, {})
        if champ in listed or not shares:
            continue
        lane = max(shares, key=lambda r: shares[r])
        if (lane, champ) not in declined:
            found.append((lane, champ, points))
        if len(found) >= limit:
            break
    return found
