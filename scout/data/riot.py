"""Riot web API (personal key from .env): Match-V5 and Champion-Mastery-V4, read-only.

Used by the loading-screen addendum (M11) and the post-game check (M10). Never used to look up
players during champ select, never for hidden players (docs/POLICY.md). Identifiers stay in
memory: nothing here is stored or sent to the LLM. Personal-key limits: 20 requests per second
and 100 per 2 minutes per region; calls wait their turn, up to a time budget.
"""

import threading
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import quote

import httpx

LIMITS = ((20, 1.0), (100, 120.0))  # (requests, seconds), personal key


class RiotError(Exception):
    """The Riot API failed: no key, a rejected key, the rate limit, or unreachable."""


@dataclass
class RiotApi:
    key: str = field(repr=False)
    platform: str  # e.g. na1 (Champion-Mastery-V4)
    region: str  # e.g. americas (Match-V5)
    timeout_s: float = 10.0
    max_wait_s: float = 20.0  # longest we'll wait for the rate limit before giving up
    limits: tuple[tuple[int, float], ...] = LIMITS  # (calls, seconds); the collector takes less
    http: httpx.Client | None = None
    clock: Callable[[], float] = time.monotonic
    sleep: Callable[[float], None] = time.sleep
    _sent: deque[float] = field(default_factory=deque)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def __post_init__(self) -> None:
        if self.http is None:
            self.http = httpx.Client(timeout=self.timeout_s)

    def ladder(self, tier: str, division: str, page: int) -> list[str]:
        """Player ids on one page of the ranked solo ladder (League-EXP-V4), for the collector;
        kept in memory only."""
        path = f"/lol/league-exp/v4/entries/RANKED_SOLO_5x5/{tier}/{division}"
        found = self._get(self.platform, path, {"page": page})
        return [str(e["puuid"]) for e in found if isinstance(e, dict) and e.get("puuid")] \
            if isinstance(found, list) else []

    def solo_ids(self, puuid: str, count: int, since_s: int) -> list[str]:
        """A player's ranked solo/duo games (queue 420) since a time, newest first."""
        path = f"/lol/match/v5/matches/by-puuid/{quote(puuid)}/ids"
        found = self._get(self.region, path, {"queue": 420, "count": count, "startTime": since_s})
        return [m for m in found if isinstance(m, str)] if isinstance(found, list) else []

    def account_puuid(self, game_name: str, tag_line: str) -> str | None:
        """The web API's id for a Riot ID (the League client's ids aren't the same)."""
        path = f"/riot/account/v1/accounts/by-riot-id/{quote(game_name)}/{quote(tag_line)}"
        found = self._get(self.region, path)
        return str(found["puuid"]) if isinstance(found, dict) and found.get("puuid") else None

    def match_ids(self, puuid: str, count: int = 20) -> list[str]:
        """The player's most recent ranked match ids, newest first."""
        path = f"/lol/match/v5/matches/by-puuid/{quote(puuid)}/ids"
        found = self._get(self.region, path, {"type": "ranked", "count": count})
        return [m for m in found if isinstance(m, str)] if isinstance(found, list) else []

    def match(self, match_id: str) -> dict[str, Any]:
        found = self._get(self.region, f"/lol/match/v5/matches/{quote(match_id)}")
        return found if isinstance(found, dict) else {}

    def timeline(self, match_id: str) -> dict[str, Any]:
        """The match minute by minute: positions, gold, experience, kills, objectives (M10)."""
        found = self._get(self.region, f"/lol/match/v5/matches/{quote(match_id)}/timeline")
        return found if isinstance(found, dict) else {}

    def top_mastery(self, puuid: str, count: int = 3) -> list[tuple[int, int]]:
        """(champion key, points) for the player's most-played champions."""
        path = f"/lol/champion-mastery/v4/champion-masteries/by-puuid/{quote(puuid)}/top"
        found = self._get(self.platform, path, {"count": count})
        return [(int(m["championId"]), int(m.get("championPoints") or 0))
                for m in found if isinstance(m, dict) and "championId" in m] if isinstance(
                    found, list) else []  # fmt: skip

    def check(self) -> None:
        """One cheap request (the platform's status). Raises RiotError if the key doesn't work.
        Development keys expire every 24 hours; a registered personal key doesn't."""
        self._get(self.platform, "/lol/status/v4/platform-data")

    def close(self) -> None:
        if self.http is not None:
            self.http.close()

    def _get(self, host: str, path: str, params: dict[str, Any] | None = None) -> Any:
        self._wait_turn()
        url = f"https://{host}.api.riotgames.com{path}"
        assert self.http is not None
        try:
            response = self.http.get(url, params=params, headers={"X-Riot-Token": self.key})
        except httpx.HTTPError as exc:
            raise RiotError(f"Riot API unreachable ({type(exc).__name__})") from None
        if response.status_code == 404:
            return None
        if response.status_code in (401, 403):
            raise RiotError("Riot API key rejected: expired or wrong (development keys last 24 "
                            "hours; paste a new one in Settings, Account and Riot key)")
        if response.status_code == 429:
            raise RiotError("Riot API rate limit reached; try again in a couple of minutes")
        if response.status_code >= 400:
            raise RiotError(f"Riot API returned HTTP {response.status_code}")
        return response.json()

    def _wait_turn(self) -> None:
        """Personal-key limits, counted locally. Raises RiotError instead of waiting too long."""
        with self._lock:
            while True:
                now = self.clock()
                while self._sent and now - self._sent[0] > self.limits[-1][1]:
                    self._sent.popleft()
                wait = 0.0
                for count, window in self.limits:
                    recent = [t for t in self._sent if now - t < window]
                    if len(recent) >= count:
                        wait = max(wait, window - (now - recent[-count]))
                if wait <= 0:
                    self._sent.append(now)
                    return
                if wait > self.max_wait_s:
                    raise RiotError("Riot API rate limit: too many calls; skipped")
                self.sleep(wait)
