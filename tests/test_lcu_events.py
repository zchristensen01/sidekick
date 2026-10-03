"""The WebSocket waker (docs/LCU.md section 5), against a fake socket. No network."""

import json
import time

from scout.lcu.connection import LcuCredentials
from scout.lcu.events import EVENTS, EventWaker, is_event


def test_is_event():
    frame = json.dumps([8, "OnJsonApiEvent_lol-champ-select_v1_session", {"eventType": "Update"}])
    assert is_event(frame) and is_event(frame.encode())
    assert not is_event(json.dumps([8, "OnJsonApiEvent_lol-chat_v1_me", {}]))
    assert not is_event("")
    assert not is_event("not json")
    assert not is_event(json.dumps({"a": 1}))


class FakeSocket:
    def __init__(self, frames):
        self.frames = list(frames)
        self.sent: list[str] = []

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def send(self, text):
        self.sent.append(text)

    def recv(self, timeout=None):
        if self.frames:
            return self.frames.pop(0)
        time.sleep(0.01)
        raise TimeoutError


def test_waker_subscribes_and_wakes_on_events():
    socket = FakeSocket(["", json.dumps([8, EVENTS[0], {"data": "ChampSelect"}])])
    calls = []

    def connect(uri, **kwargs):
        calls.append((uri, kwargs))
        return socket

    waker = EventWaker(lambda: LcuCredentials(50200, "secret", "process"), connect=connect)
    waker.start()
    try:
        assert waker.wait(2.0) is True
        uri, kwargs = calls[0]
        assert uri == "wss://127.0.0.1:50200/"
        assert kwargs["additional_headers"]["Authorization"].startswith("Basic ")
        assert kwargs["proxy"] is None
        assert [json.loads(s) for s in socket.sent] == [[5, name] for name in EVENTS]
        assert waker.connected
    finally:
        waker.stop()


def test_waker_without_a_client_just_times_out():
    waker = EventWaker(lambda: None, connect=lambda *a, **k: None)
    waker.start()
    try:
        assert waker.wait(0.05) is False and not waker.connected
    finally:
        waker.stop()
