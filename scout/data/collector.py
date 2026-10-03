"""The collector (M19): real figures from Riot's own match data, Emerald and above.

Players come from Riot's ranked solo ladder (League-EXP-V4), one page at a time, taking turns
from Challenger down to Emerald IV; each player's few most recent ranked solo games
(Match-V5) are fetched, measured (scout/data/measure.py) and counted once. Only the current
and previous patch are kept. Player ids are used in memory to list games and then dropped;
games are remembered by a one-way hash, so nothing stored points back to a player or a game.

Riot's personal-key limit (100 calls per 2 minutes) allows about 45 games every 2 minutes;
`scout collect` runs it by hand, and the owner's app runs it in the background while they're
not in a game (it pauses for champ select so the loading-screen checks get the key's calls).

It stops at PATCH_TARGET games for the current patch and starts again with the next patch, and
each run first drops older patches' data (docs/MATCH_DATA.md).
"""

import hashlib
import json
import random
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from scout.data.measure import POSITIONS, measure, patch_of
from scout.data.riot import RiotError
from scout.data.stats_db import StatsDb
from scout.model.roles import Role
from scout.postgame.grade import MatchError, outcome, read_match

DIVISIONS = ("I", "II", "III", "IV")
LADDER = (("CHALLENGER", "I"), ("GRANDMASTER", "I"), ("MASTER", "I"),
          *((tier, d) for tier in ("DIAMOND", "EMERALD") for d in DIVISIONS))  # fmt: skip
GAMES_PER_PLAYER = 3
# The collector's share of the personal key's limits (20 a second, 100 every 2 minutes), so the
# app's own calls (loading-screen checks, the post-game check) always have room.
COLLECTOR_LIMITS = ((15, 1.0), (80, 120.0))
LOOKBACK_DAYS = 14  # a patch lasts about two weeks
MAX_PAGE = 20  # wrap to page 1 after this many pages of a division
PATCH_TARGET = 4000  # games per patch: then the figures barely move, and collecting pauses
SEEN_DAYS = 30  # "already counted" marks are kept this long (past the look-back, then dropped)


@dataclass
class Summary:
    added: int = 0  # games measured and counted
    old_patch: int = 0  # games skipped: an older patch
    seen: int = 0  # games already counted
    players: int = 0
    error: str = ""
    by_patch: dict[str, int] = field(default_factory=dict)
    full: str = ""  # the patch that already has PATCH_TARGET games (nothing to do)

    def line(self) -> str:
        if self.full and not self.added:
            return (f"Patch {self.full} has its {PATCH_TARGET:,} games: collecting starts again "
                    "with the next patch.")  # fmt: skip
        text = f"{self.added} new games measured ({self.players} players' recent games checked"
        text += f", {self.seen} already counted, {self.old_patch} from older patches)"
        if self.full:
            text += f"; patch {self.full} now has its {PATCH_TARGET:,} games"
        if self.error:
            text += f"; stopped: {self.error}"
        return text + "."


def backtest_record(match: Mapping[str, Any], timeline: Mapping[str, Any],
                    by_key: Mapping[int, str]) -> dict[str, Any] | None:  # fmt: skip
    """Each side's draft and what happened from that side (M20), or None if a side lacks a
    jungler. Champions and roles only: nothing about the players."""
    sides: dict[str, Any] = {}
    people = [p for p in (match.get("info") or {}).get("participants") or []
              if isinstance(p, dict)]  # fmt: skip
    for team in (100, 200):
        draft = {}
        for p in people:
            role = POSITIONS.get(str(p.get("teamPosition") or ""))
            champ = by_key.get(int(p.get("championId") or 0))
            if p.get("teamId") == team and role and champ:
                draft[role.value] = champ
        jungler = next((p for p in people if p.get("teamId") == team
                        and p.get("teamPosition") == "JUNGLE"), None)  # fmt: skip
        if jungler is None or len(draft) != 5:
            return None
        try:
            found = read_match(match, timeline, int(jungler["championId"]), Role.JUNGLE)
        except MatchError:
            return None
        sides[str(team)] = {"draft": draft, "outcome": outcome(found)}
    return {"sides": sides, "version": str((match.get("info") or {}).get("gameVersion") or "")}


def left_this_patch(db: StatsDb, patch: str) -> int:
    """Games still wanted for this patch (0 once it has PATCH_TARGET)."""
    return max(0, PATCH_TARGET - db.collected_games(patch))


class Collector:
    def __init__(self, riot: object, db: StatsDb, by_key: Mapping[int, str],
                 finished_items: frozenset[int], patches: Sequence[str],
                 now: Callable[[], datetime] = lambda: datetime.now().astimezone(),
                 shuffle: Callable[[list[str]], None] = random.shuffle) -> None:  # fmt: skip
        self.riot, self.db, self.by_key = riot, db, by_key
        self.finished, self.patches = finished_items, tuple(patches)
        self.now, self.shuffle = now, shuffle
        self.tier = ""  # the ladder tier of the page being walked, kept with each game record

    def run(self, games: int, stop: Callable[[], bool] = lambda: False) -> Summary:
        """Measure up to `games` new games, never more than the current patch still wants.
        Drops older patches' data first. Never raises: a Riot error ends the run."""
        summary = Summary()
        now = self.now()
        since = int(now.timestamp()) - LOOKBACK_DAYS * 86_400
        self.db.prune(self.patches, (now - timedelta(days=SEEN_DAYS)).isoformat(timespec="seconds"))
        current = self.patches[0] if self.patches else ""

        def full() -> bool:
            if current and left_this_patch(self.db, current) == 0:
                summary.full = current
                return True
            return False

        if full():
            return summary
        try:
            while summary.added < games and not stop() and not full():
                players = self._next_page()
                if not players:
                    continue
                self.shuffle(players)
                for puuid in players:
                    if summary.added >= games or stop() or full():
                        break
                    summary.players += 1
                    for match_id in self.riot.solo_ids(puuid, GAMES_PER_PLAYER, since):
                        if summary.added >= games or stop():
                            break
                        self._one(match_id, summary)
        except RiotError as exc:
            summary.error = str(exc)
        return summary

    def _one(self, match_id: str, summary: Summary) -> None:
        key = hashlib.sha256(match_id.encode()).hexdigest()
        if self.db.seen(key):
            summary.seen += 1
            return
        match = self.riot.match(match_id)
        patch = patch_of(match)
        stamp = self.now().isoformat(timespec="seconds")
        if patch not in self.patches:
            self.db.add_game(key, patch or "unknown", [], stamp)  # remembered, not counted
            summary.old_patch += 1
            return
        timeline = self.riot.timeline(match_id)
        players = measure(match, timeline, self.by_key, self.finished)
        record = backtest_record(match, timeline, self.by_key)
        if record is not None and self.tier:
            record["tier"] = self.tier  # the ladder tier the game was found through
        if players and self.db.add_game(key, patch, players, stamp, record):
            summary.added += 1
            summary.by_patch[patch] = summary.by_patch.get(patch, 0) + 1
        elif not players:
            self.db.add_game(key, patch, [], stamp)  # too short or incomplete: not counted

    def _next_page(self) -> list[str]:
        """The next ladder page, taking turns between tiers and divisions."""
        raw = self.db.state("ladder_cursor")
        cursor = json.loads(raw) if raw else {"step": 0, "pages": {}}
        step = cursor["step"] % len(LADDER)
        tier, division = LADDER[step]
        self.tier = tier
        name = f"{tier}-{division}"
        page = int(cursor["pages"].get(name, 0)) % MAX_PAGE + 1
        players = self.riot.ladder(tier, division, page)
        cursor["pages"][name] = page if players else 0  # past the end: start over next time
        cursor["step"] = step + 1
        self.db.set_state("ladder_cursor", json.dumps(cursor))
        return players
