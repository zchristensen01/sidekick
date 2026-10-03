"""Players at the loading screen (M16): each visible player's record on the champion they play.

At the loading screen every player is listed, so (like the duo check, docs/POLICY.md) each
visible player's Riot ID is read from the client (read-only) and their OP.GG profile fetched:
solo queue rank, ranked games on this champion this season (won, average kills / deaths /
assists), and their recent games. Players the game hides (streamer mode) are skipped and never
worked out. Riot IDs stay in memory: the cards, the dashboard, the saved report and the LLM
only ever say "their Sivir player".
"""

import dataclasses
import threading
from collections.abc import Callable, Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any

from scout.data.opgg import ChampRecord, OpggError, Profile
from scout.model.roles import Role

MIN_GAMES_FOR_RATE = 5  # fewer games: the count only, no percentage (STATS.md rule 1)
APEX = ("MASTER", "GRANDMASTER", "CHALLENGER")  # no divisions: LP instead
WORKERS = 2  # OP.GG politeness: the client's own throttle still applies


@dataclass(frozen=True)
class Seat:
    """One player at the loading screen."""

    side: str  # us | them
    champion_key: int
    champ_id: str
    name: str  # the champion's display name
    role: Role | None
    puuid: str = field(default="", repr=False)  # the client's id; "" = hidden by the game


@dataclass(frozen=True)
class PlayerCard:
    side: str
    role: Role | None
    champ_id: str
    name: str
    rank: str = ""  # "Gold 2", "Master 120 LP", "unranked in solo queue"
    season: ChampRecord | None = None  # ranked games on this champion this season
    recent_games: int = 0
    recent_wins: int = 0
    note: str = ""  # "hidden by the game", "not found on OP.GG", ...

    @property
    def who(self) -> str:
        return f"{'Your' if self.side == 'us' else 'Their'} {self.name} player"

    def champion_text(self) -> str:
        s = self.season
        if s is None or s.games == 0:
            return f"no ranked games on {self.name} this season"
        text = f"{s.games} ranked game{'s' if s.games != 1 else ''} on {self.name} this season"
        if s.games >= MIN_GAMES_FOR_RATE:
            text += f", {round(100 * s.wins / s.games)}% won"
        return text

    def kda_text(self) -> str:
        s = self.season
        if s is None or s.games == 0:
            return ""
        g = s.games
        return f"{s.kills / g:.1f} / {s.deaths / g:.1f} / {s.assists / g:.1f}"

    def recent_text(self) -> str:
        if not self.recent_games:
            return ""
        return f"won {self.recent_wins} of their last {self.recent_games} games"

    def line(self) -> str:
        if self.note:
            return f"{self.who}: {self.note}."
        parts = [self.champion_text()]
        if self.kda_text():
            parts.append(f"{self.kda_text()} average kills / deaths / assists")
        if self.recent_text():
            parts.append(self.recent_text())
        rank = f" ({self.rank})" if self.rank else ""
        return f"{self.who}{rank}: " + "; ".join(parts) + "."

    def view(self) -> dict[str, Any]:
        """For the dashboard and the writer: display strings only, no identifiers."""
        s = self.season
        rate = (round(100 * s.wins / s.games) if s and s.games >= MIN_GAMES_FOR_RATE
                else None)  # fmt: skip
        return {
            "side": self.side, "role": self.role.value if self.role else None,
            "id": self.champ_id, "champion": self.name, "rank": self.rank,
            "games": s.games if s else 0, "win_rate": rate,
            "on_champion": self.champion_text(), "average_kda": self.kda_text(),
            "recent": self.recent_text(), "note": self.note, "text": self.line(),
        }  # fmt: skip


def seats_at_loading(
    gameflow: Any,
    ally_keys: Sequence[int],
    by_key: Mapping[int, str],
    names: Mapping[str, str],
    roles: Mapping[str, Role],
    my_key: int | None,
) -> list[Seat]:
    """Everyone at the loading screen but me, hidden players included (no puuid). Our team is
    the side holding our champions from champ select."""
    data = gameflow.get("gameData") if isinstance(gameflow, dict) else None
    if not isinstance(data, dict):
        return []
    teams = [[p for p in data.get(side) or [] if isinstance(p, dict)]
             for side in ("teamOne", "teamTwo")]  # fmt: skip
    ours = set(ally_keys)
    seats = []
    for team in teams:
        keys = {p.get("championId") for p in team}
        side = "us" if ours and ours <= keys else "them"
        for p in team:
            key = p.get("championId")
            if not isinstance(key, int) or key not in by_key or key == my_key:
                continue
            champ = by_key[key]
            seats.append(Seat(side, key, champ, names.get(champ, champ), roles.get(champ),
                              str(p.get("puuid") or "")))  # fmt: skip
    return seats


def card(seat: Seat, profile: Profile) -> PlayerCard:
    if profile.tier in APEX:
        rank = f"{profile.tier.title()} {profile.lp or 0} LP"
    elif profile.tier:
        division = f" {profile.division}" if profile.division else ""
        rank = f"{profile.tier.title()}{division}"
    else:
        rank = "unranked in solo queue"
    recent = profile.recent.values()
    return PlayerCard(
        seat.side, seat.role, seat.champ_id, seat.name, rank,
        profile.season.get(seat.champion_key),
        sum(r.games for r in recent), sum(r.wins for r in recent),
    )  # fmt: skip


def gather(
    seats: Sequence[Seat],
    riot_id_of: Callable[[str], tuple[str, str] | None],
    profile_of: Callable[[str, str], Profile],
    stop: threading.Event | None = None,
) -> list[PlayerCard]:
    """A card per seat, in seat order. Never raises: problems become the card's note."""

    def one(seat: Seat) -> PlayerCard:
        blank = PlayerCard(seat.side, seat.role, seat.champ_id, seat.name)
        if not seat.puuid:
            return dataclasses.replace(blank, note="hidden by the game, not checked")
        if stop is not None and stop.is_set():
            return dataclasses.replace(blank, note="not checked")
        riot_id = riot_id_of(seat.puuid)
        if riot_id is None:
            return dataclasses.replace(blank, note="hidden by the game, not checked")
        try:
            return card(seat, profile_of(*riot_id))
        except OpggError as exc:
            missing = "not found" in str(exc).lower()
            reason = "not found on OP.GG" if missing else "OP.GG lookup failed"
            return dataclasses.replace(blank, note=reason)

    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        return list(pool.map(one, seats))
