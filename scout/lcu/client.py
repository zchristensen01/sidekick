"""Read-only REST client for the League client.

GET only, by design (CLAUDE.md hard rule 1). There is deliberately no generic request method,
and tests/test_lcu_readonly.py fails if a write method appears. Only the endpoints listed in
ENDPOINTS (and in docs/LCU.md section 2) can be read.
"""

import re
import ssl
from collections.abc import Callable
from typing import Any

import httpx

from scout.lcu.connection import LcuCredentials, ssl_context

GAMEFLOW_PHASE = "/lol-gameflow/v1/gameflow-phase"
GAMEFLOW_SESSION = "/lol-gameflow/v1/session"
CHAMP_SELECT_SESSION = "/lol-champ-select/v1/session"
GAME_VERSION = "/lol-patch/v1/game-version"

# Every endpoint the app reads. Add one only when a milestone needs it, and list it in
# docs/LCU.md section 2 too (a test checks).
CHAMPION_MASTERY = "/lol-champion-mastery/v1/local-player/champion-mastery"
CURRENT_SUMMONER = "/lol-summoner/v1/current-summoner"  # who is logged in (M22)
RECENT_GAMES = "/lol-match-history/v1/products/lol/current-summoner/matches"  # mine (M22)
ENDPOINTS = frozenset({GAMEFLOW_PHASE, GAMEFLOW_SESSION, CHAMP_SELECT_SESSION, GAME_VERSION,
                       CHAMPION_MASTERY, CURRENT_SUMMONER, RECENT_GAMES})  # fmt: skip
# Paths with one id in them. Only the shapes below; the id must look like a client player id.
SUMMONER_BY_PUUID = "/lol-summoner/v2/summoners/puuid/{puuid}"
TEMPLATES = frozenset({SUMMONER_BY_PUUID})
_ID = r"[0-9A-Za-z-]{20,100}"


def allowed(path: str) -> bool:
    """True for a listed endpoint or a listed template filled with one plain id."""
    if path in ENDPOINTS:
        return True
    return any(re.fullmatch(re.escape(t).replace(r"\{puuid\}", _ID), path) for t in TEMPLATES)


class LcuError(Exception):
    """The client answered in a way we can't use, or its certificate didn't check out."""


class LcuUnavailable(LcuError):
    """The client isn't running or stopped answering. Wait and try again."""


class LcuClient:
    def __init__(
        self,
        find: Callable[[], LcuCredentials | None],
        timeout_s: float = 5.0,
        transport: httpx.BaseTransport | None = None,  # tests pass a fake
    ) -> None:
        self._find = find
        self._timeout_s = timeout_s
        self._transport = transport
        self._ssl = ssl_context()
        self._http: httpx.Client | None = None

    def get(self, path: str) -> Any:
        """GET a path like '/lol-champ-select/v1/session'. Parsed JSON, or None on 404.

        Raises LcuUnavailable if the client isn't reachable, LcuError for anything else.
        """
        if not allowed(path):
            raise ValueError(f"{path} isn't in ENDPOINTS (scout/lcu/client.py, docs/LCU.md)")
        was_connected = self._http is not None
        try:
            return self._get_once(path)
        except LcuUnavailable:
            self._disconnect()
            if not was_connected:
                raise
        # The port and token change whenever the client restarts: find it again, retry once.
        try:
            return self._get_once(path)
        except LcuUnavailable:
            self._disconnect()
            raise

    def close(self) -> None:
        self._disconnect()

    def _get_once(self, path: str) -> Any:
        http = self._connect()
        try:
            response = http.get(path)
        except httpx.TransportError as exc:
            if _is_certificate_error(exc):
                raise LcuError(
                    "The League client's certificate didn't verify against "
                    f"scout/lcu/riotgames.pem: {exc}"
                ) from exc
            raise LcuUnavailable(f"League client not answering: {exc}") from exc
        if response.status_code == 401:
            raise LcuUnavailable("League client rejected the token (it probably restarted)")
        if response.status_code == 404:  # e.g. champ select session outside champ select
            return None
        if response.is_error:
            raise LcuError(f"GET {path}: HTTP {response.status_code}")
        if not response.content:
            return None
        try:
            return response.json()
        except ValueError as exc:
            raise LcuError(f"GET {path}: response isn't JSON") from exc

    def _connect(self) -> httpx.Client:
        if self._http is None:
            credentials = self._find()
            if credentials is None:
                raise LcuUnavailable("League client not running")
            self._http = httpx.Client(
                base_url=credentials.base_url,
                auth=credentials.auth,
                verify=self._ssl,
                timeout=self._timeout_s,
                trust_env=False,  # never send local client traffic through a proxy
                transport=self._transport,
                headers={"Accept": "application/json"},
            )
        return self._http

    def _disconnect(self) -> None:
        if self._http is not None:
            self._http.close()
            self._http = None


def _is_certificate_error(exc: BaseException) -> bool:
    """True if a failed connection was a TLS certificate failure (retrying won't help)."""
    cause: BaseException | None = exc
    for _ in range(10):  # walk the exception chain; httpx wraps the ssl error
        if cause is None:
            return False
        if isinstance(cause, ssl.SSLCertVerificationError):
            return True
        if "CERTIFICATE_VERIFY_FAILED" in str(cause):
            return True
        cause = cause.__cause__ or cause.__context__
    return False
