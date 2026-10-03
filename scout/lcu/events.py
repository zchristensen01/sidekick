"""Wake `scout watch` as soon as the client reports a change, over its WebSocket (WAMP 1.0).

The state itself is always read with GETs (one code path); events only cut the wait between
polls. If the socket can't connect, `scout watch` just polls every `client.poll_seconds`.
Subscribing is read-only. Protocol and gotchas: docs/LCU.md section 5.
"""

import base64
import contextlib
import json
import threading
from collections.abc import Callable
from typing import Any

from scout.lcu.connection import LcuCredentials, ssl_context

WAMP_SUBSCRIBE, WAMP_EVENT = 5, 8
EVENTS = (
    "OnJsonApiEvent_lol-gameflow_v1_gameflow-phase",
    "OnJsonApiEvent_lol-champ-select_v1_session",
    "OnJsonApiEvent_lol-gameflow_v1_session",
)
RETRY_S = 3.0


def is_event(message: Any) -> bool:
    """True for a WAMP event frame for one of our subscriptions. Junk frames are just False."""
    if isinstance(message, bytes):
        message = message.decode("utf-8", errors="replace")
    if not isinstance(message, str) or not message.strip():
        return False
    try:
        frame = json.loads(message)
    except ValueError:
        return False
    return (isinstance(frame, list) and len(frame) >= 2 and frame[0] == WAMP_EVENT
            and frame[1] in EVENTS)  # fmt: skip


class EventWaker:
    """A background thread that sets a flag whenever a subscribed event arrives."""

    def __init__(
        self,
        find: Callable[[], LcuCredentials | None],
        connect: Callable[..., Any] | None = None,  # tests pass a fake
    ) -> None:
        self._find = find
        self._connect = connect
        self._signal = threading.Event()
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, name="lcu-events", daemon=True)
        self.connected = False

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def wait(self, timeout: float) -> bool:
        """Sleep until an event arrives or `timeout` passes. True if an event woke us."""
        woke = self._signal.wait(timeout)
        self._signal.clear()
        return woke

    def _run(self) -> None:
        connect = self._connect
        if connect is None:
            from websockets.sync.client import connect
        while not self._stop.is_set():
            credentials = self._find()
            if credentials is None:
                self._stop.wait(RETRY_S)
                continue
            # A closed client, refused socket or bad frame just means polling until it's back.
            with contextlib.suppress(Exception):
                self._listen(connect, credentials)
            self.connected = False
            self._stop.wait(RETRY_S)

    def _listen(self, connect: Callable[..., Any], credentials: LcuCredentials) -> None:
        token = base64.b64encode(f"riot:{credentials.token}".encode()).decode()
        with connect(
            f"wss://127.0.0.1:{credentials.port}/",
            ssl=ssl_context(),
            additional_headers={"Authorization": f"Basic {token}"},
            proxy=None,  # never route local client traffic through a proxy
            open_timeout=5,
        ) as socket:
            for name in EVENTS:
                socket.send(json.dumps([WAMP_SUBSCRIBE, name]))
            self.connected = True
            while not self._stop.is_set():
                try:
                    message = socket.recv(timeout=1.0)
                except TimeoutError:
                    continue
                if is_event(message):
                    self._signal.set()
