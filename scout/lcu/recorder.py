"""`scout record`: save scrubbed champ select sessions as test fixtures.

While it runs, it polls the client every `client.poll_seconds`. During champion select it keeps
every distinct session snapshot; when champion select ends (game start, dodge, or Ctrl+C) it
writes one JSON file to tests/fixtures/champselect/. If the game starts, the file also gets the
roster the game shows at loading (champions, positions, summoner spells), the answer key for
enemy roles. Everything is scrubbed before it's kept (docs/LCU.md section 7, docs/POLICY.md).
Read-only, like everything in scout/lcu/.
"""

import json
import re
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Protocol

from scout import __version__
from scout.lcu.client import (
    CHAMP_SELECT_SESSION,
    GAME_VERSION,
    GAMEFLOW_PHASE,
    GAMEFLOW_SESSION,
    LcuError,
    LcuUnavailable,
)
from scout.model.roles import has_positions, queue_from_id, role_from_lcu

# Removed or blanked wherever they appear in a recording (docs/LCU.md section 7).
DROP_KEYS = ("chatDetails",)
BLANK_KEYS = (
    "puuid", "summonerId", "obfuscatedPuuid", "obfuscatedSummonerId", "gameName", "tagLine",
    "gameId", "internalName", "summonerInternalName", "summonerName",
)  # fmt: skip
# Blanked only at the top level: the champ select session's own id (a long token, seen
# 2026-10-02). Elsewhere `id` is a harmless number (action ids, swap ids).
BLANK_TOP_LEVEL_KEYS = ("id",)

# Safety net for identifiers Riot adds later under new names: any long token-like string (a
# puuid is 78 characters, chat tokens are longer) is blanked too, and reported.
TOKEN_LIKE = re.compile(r"[A-Za-z0-9+/=_.-]{32,}")

# The only parts of the gameflow session we keep. The rest holds server addresses and, from the
# loading screen on, every player's identity; champ select tests need none of it.
GAMEFLOW_KEEP: dict[str, Any] = {
    "phase": True,
    "gameData": {
        "isCustomGame": True,
        "queue": {
            "id": True, "type": True, "gameMode": True, "mapId": True, "isRanked": True,
            "description": True,
        },
    },
    "map": {"id": True},
    "gameDodge": {"phase": True, "state": True},
}  # fmt: skip

# At game start, per player: only these (game_roster()).
ROSTER_PLAYER_KEEP = {"championId": True, "selectedPosition": True, "selectedRole": True}
ROSTER_SPELLS_KEEP = {"championId": True, "spell1Id": True, "spell2Id": True}

# These change constantly without changing the draft, so a change in only these isn't a new
# snapshot.
DEDUP_IGNORE = frozenset({
    "counter", "recoveryCounter", "adjustedTimeLeftInPhase", "internalNowInEpochMs",
    "totalTimeInPhase", "selectedSkinId", "wardSkinId",
})  # fmt: skip

IN_GAME_PHASES = frozenset(
    {"GameStart", "InProgress", "Reconnect", "WaitingForStats", "PreEndOfGame", "EndOfGame"}
)
CLIENT_WAIT_S = 3.0  # how often to look for the client while it's closed


class Reader(Protocol):
    def get(self, path: str) -> Any: ...


# ---------------------------------------------------------------- scrubbing


def scrub(data: Any) -> tuple[Any, list[str]]:
    """A scrubbed copy of `data`, and the paths of token-like strings that were blanked."""
    flagged: set[str] = set()

    def walk(value: Any, path: str) -> Any:
        if isinstance(value, dict):
            out: dict[str, Any] = {}
            for key, item in value.items():
                if key in DROP_KEYS:
                    continue
                blank = key in BLANK_KEYS or (not path and key in BLANK_TOP_LEVEL_KEYS)
                out[key] = _blank(item) if blank else walk(item, _join(path, key))
            return out
        if isinstance(value, list):
            return [walk(item, f"{path}[]") for item in value]
        if isinstance(value, str) and TOKEN_LIKE.fullmatch(value):
            flagged.add(path)
            return ""
        return value

    return walk(data, ""), sorted(flagged)


def find_unscrubbed(data: Any) -> list[str]:
    """Paths of anything scrub() removes or blanks. Empty for a clean recording."""
    problems: set[str] = set()

    def walk(value: Any, path: str) -> None:
        if isinstance(value, dict):
            for key, item in value.items():
                where = _join(path, key)
                if key in DROP_KEYS or (key in BLANK_KEYS and item not in ("", 0, None)):
                    problems.add(where)
                else:
                    walk(item, where)
        elif isinstance(value, list):
            for item in value:
                walk(item, f"{path}[]")
        elif isinstance(value, str) and TOKEN_LIKE.fullmatch(value):
            problems.add(path)

    walk(data, "")
    return sorted(problems)


def game_roster(gameflow: Any) -> dict[str, Any]:
    """Who played what at game start: champion, position and summoner spells, no identities.

    The answer key for enemy role inference (docs/ROLES.md): enemy positions and spells are
    hidden in champ select but shown once the game loads. {} until the client fills it in.
    """
    data = gameflow.get("gameData") if isinstance(gameflow, dict) else None
    if not isinstance(data, dict):
        return {}
    roster = {
        team: [keep_only(player, ROSTER_PLAYER_KEEP) for player in data.get(team) or []]
        for team in ("teamOne", "teamTwo")
    }
    if not roster["teamOne"] and not roster["teamTwo"]:
        return {}
    picks = data.get("playerChampionSelections") or []
    roster["spells"] = [keep_only(pick, ROSTER_SPELLS_KEEP) for pick in picks]
    clean, _ = scrub(roster)
    return clean


def keep_only(data: Any, spec: dict[str, Any]) -> dict[str, Any]:
    """The parts of `data` named in `spec` (nested dicts of key -> True or a sub-spec)."""
    if not isinstance(data, dict):
        return {}
    out: dict[str, Any] = {}
    for key, sub in spec.items():
        if key in data:
            out[key] = keep_only(data[key], sub) if isinstance(sub, dict) else data[key]
    return out


def _blank(value: Any) -> Any:
    if isinstance(value, str):
        return ""
    if isinstance(value, int | float) and not isinstance(value, bool):
        return 0
    return None


def _join(path: str, key: str) -> str:
    return f"{path}.{key}" if path else key


def _without(value: Any, keys: frozenset[str]) -> Any:
    if isinstance(value, dict):
        return {k: _without(v, keys) for k, v in value.items() if k not in keys}
    if isinstance(value, list):
        return [_without(v, keys) for v in value]
    return value


# ---------------------------------------------------------------- one champ select


@dataclass
class Recording:
    started_s: float  # clock reading at the start, for each snapshot's elapsed_s
    recorded_at: datetime
    queue_id: int | None
    gameflow: dict[str, Any]
    game_version: str | None
    game_id: Any  # unscrubbed, kept in memory only to notice a new champ select
    snapshots: list[dict[str, Any]] = field(default_factory=list)
    blanked_tokens: set[str] = field(default_factory=set)
    game_phase: str = ""  # set once the game starts
    game_start: dict[str, Any] | None = None  # game_roster() at game start
    _last_key: str = ""

    def add(self, session: dict[str, Any], now_s: float) -> bool:
        """Keep a snapshot if the draft changed since the last one. True if kept."""
        clean, flagged = scrub(session)
        self.blanked_tokens.update(flagged)
        key = json.dumps(_without(clean, DEDUP_IGNORE), sort_keys=True)
        if key == self._last_key:
            return False
        self._last_key = key
        timer = clean.get("timer") if isinstance(clean.get("timer"), dict) else {}
        self.snapshots.append({
            "elapsed_s": round(now_s - self.started_s, 1),
            "phase": timer.get("phase", ""),
            "session": clean,
        })  # fmt: skip
        return True

    def me(self) -> dict[str, Any]:
        """My player entry in the latest snapshot ({} if not found)."""
        session = self.snapshots[-1]["session"] if self.snapshots else {}
        for player in session.get("myTeam") or []:
            if player.get("cellId") == session.get("localPlayerCellId"):
                return player
        return {}

    def fixture(self, outcome: str, end_phase: str) -> dict[str, Any]:
        me = self.me()
        role = role_from_lcu(str(me.get("assignedPosition") or ""))
        return {
            "meta": {
                "recorded_at": self.recorded_at.isoformat(timespec="seconds"),
                "scout_version": __version__,
                "game_version": self.game_version,
                "queue_id": self.queue_id,
                "queue": _queue_name(self.queue_id),
                "my_role": role.value if role else None,
                "my_champion_id": me.get("championId") or 0,
                "outcome": outcome,
                "end_phase": end_phase,
                "snapshot_count": len(self.snapshots),
                "blanked_tokens": sorted(self.blanked_tokens),
            },
            "gameflow": self.gameflow,
            "snapshots": self.snapshots,
            "game_start": self.game_start,
        }

    def file_stem(self, outcome: str) -> str:
        """<date>_<queue>_<my role>_champ<id>, plus _dodged or _stopped if no game started."""
        me = self.me()
        role = role_from_lcu(str(me.get("assignedPosition") or ""))
        suffix = "" if outcome == "game_started" else f"_{outcome}"
        return (
            f"{self.recorded_at:%Y-%m-%d}_{_queue_name(self.queue_id)}_"
            f"{role.value if role else 'norole'}_champ{me.get('championId') or 0}{suffix}"
        )


def _queue_name(queue_id: int | None) -> str:
    if queue_id is None:
        return "unknown_queue"
    queue = queue_from_id(queue_id)
    return queue.value if has_positions(queue) else f"queue{queue_id}"


def _queue_id(gameflow: Any, session: dict[str, Any]) -> int | None:
    queue = keep_only(gameflow, {"gameData": {"queue": {"id": True}}})
    queue_id = queue.get("gameData", {}).get("queue", {}).get("id", session.get("queueId"))
    return queue_id if isinstance(queue_id, int) else None


# ---------------------------------------------------------------- polling


class Recorder:
    """Turns polls of the client into recordings, one file per champion select."""

    def __init__(
        self,
        client: Reader,
        out_dir: Path,
        *,
        all_queues: bool = False,
        echo: Callable[[str], None] = print,
        clock: Callable[[], float] = time.monotonic,
        now: Callable[[], datetime] = lambda: datetime.now().astimezone(),
    ) -> None:
        self.client = client
        self.out_dir = out_dir
        self.all_queues = all_queues
        self.echo = echo
        self.clock = clock
        self.now = now
        self.current: Recording | None = None
        self._skipping = False  # in a champ select we chose not to record

    def step(self) -> Path | None:
        """One poll. Returns the file written during this poll, if any.

        Raises LcuUnavailable if the client is closed; a recording in progress is kept, so it
        continues if the client comes back.
        """
        phase = self.client.get(GAMEFLOW_PHASE)
        session = self.client.get(CHAMP_SELECT_SESSION) if phase == "ChampSelect" else None
        gameflow = None
        if phase in IN_GAME_PHASES and self.current is not None:
            gameflow = self.client.get(GAMEFLOW_SESSION)
        return self.process(phase, session, gameflow)

    def process(self, phase: Any, session: Any, gameflow: Any = None) -> Path | None:
        """Handle one poll's reads (`scout watch` passes the ones it already made).

        `session` is the champ select session (when the phase is ChampSelect); `gameflow` the
        gameflow session (when the game is starting and a recording is in progress).
        """
        if phase != "ChampSelect":
            self._skipping = False
            if self.current is None:
                return None
            if phase not in IN_GAME_PHASES:
                return self._finish("dodged", str(phase or ""))
            # The game started: save who played what (the answer key for enemy roles). The
            # client fills the roster in during loading, so wait for it until InProgress.
            roster = game_roster(gameflow)
            self.current.game_phase = phase
            if phase == "GameStart" and not roster.get("spells"):
                return None
            self.current.game_start = roster or None
            return self._finish("game_started", phase)

        if not isinstance(session, dict) or self._skipping:  # None while champ select starts
            return None
        saved = None
        game_id = session.get("gameId")
        current_id = self.current.game_id if self.current else None
        if current_id and game_id and game_id != current_id:
            saved = self._finish("dodged", "ChampSelect")  # missed the phase change between
        if self.current is None:
            self.current = self._start(session)
            if self.current is None:
                self._skipping = True
                return saved
        self.current.add(session, self.clock())
        return saved

    def stop(self) -> Path | None:
        """Save a champion select in progress (on Ctrl+C or exit)."""
        if self.current is None:
            return None
        if self.current.game_phase:  # the game started; the roster just never showed up
            return self._finish("game_started", self.current.game_phase)
        return self._finish("stopped", "")

    def _start(self, session: dict[str, Any]) -> Recording | None:
        gameflow = self.client.get(GAMEFLOW_SESSION)
        queue_id = _queue_id(gameflow, session)
        if not self.all_queues and (queue_id is None or not has_positions(queue_from_id(queue_id))):
            self.echo(
                f"Champion select in queue {queue_id}: not a draft queue, not recording "
                "(--all-queues records it)."
            )
            return None
        self.echo(f"Champion select started ({_queue_name(queue_id)}). Recording...")
        gameflow_kept, _ = scrub(keep_only(gameflow, GAMEFLOW_KEEP))
        return Recording(
            started_s=self.clock(),
            recorded_at=self.now(),
            queue_id=queue_id,
            gameflow=gameflow_kept,
            game_version=self._game_version(),
            game_id=session.get("gameId"),
        )

    def _game_version(self) -> str | None:
        try:
            version = self.client.get(GAME_VERSION)
        except LcuUnavailable:
            raise
        except LcuError:
            return None  # nice to have; never worth losing a recording over
        if not isinstance(version, str):
            return None
        # "16.19.8230722+branch.releases-16-19.code.public...": keep the part before "+"
        return version.partition("+")[0]

    def _finish(self, outcome: str, end_phase: str) -> Path | None:
        recording, self.current = self.current, None
        if recording is None or not recording.snapshots:
            return None
        fixture = recording.fixture(outcome, end_phase)
        leftovers = find_unscrubbed(fixture)
        if leftovers:  # never write anything unscrubbed; keep recording the next games
            self.echo(f"Not saved: unscrubbed values at {', '.join(leftovers)}. Please report.")
            return None
        self.out_dir.mkdir(parents=True, exist_ok=True)
        path = _free_path(self.out_dir, recording.file_stem(outcome))
        text = json.dumps(fixture, indent=2, ensure_ascii=False) + "\n"
        path.write_text(text, encoding="utf-8", newline="\n")
        self.echo(f"Saved {path} ({len(recording.snapshots)} snapshots, {outcome}).")
        if recording.blanked_tokens:
            self.echo(
                "Note: blanked unexpected token-like values at "
                f"{', '.join(sorted(recording.blanked_tokens))}. If that's a new identifier "
                "field, add it to BLANK_KEYS in scout/lcu/recorder.py."
            )
        return path


def _free_path(folder: Path, stem: str) -> Path:
    path = folder / f"{stem}.json"
    n = 2
    while path.exists():
        path = folder / f"{stem}_{n}.json"
        n += 1
    return path


def run(
    recorder: Recorder,
    poll_seconds: float,
    *,
    echo: Callable[[str], None] = print,
    sleep: Callable[[float], None] = time.sleep,
) -> None:
    """Poll until Ctrl+C, waiting for the client whenever it's closed. Saves on the way out."""
    connected: bool | None = None
    try:
        while True:
            try:
                recorder.step()
                if connected is not True:
                    echo("Connected to the League client. Waiting for champion select.")
                connected = True
            except LcuUnavailable:
                if connected is not False:
                    echo("Waiting for the League client to open...")
                connected = False
            sleep(poll_seconds if connected else max(poll_seconds, CLIENT_WAIT_S))
    except KeyboardInterrupt:
        echo("Stopping.")
    finally:
        recorder.stop()
