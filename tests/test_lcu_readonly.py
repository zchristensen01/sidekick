"""CLAUDE.md hard rule 1: the League client is read-only. These tests keep it that way."""

import inspect
from pathlib import Path

import scout.lcu
from scout.lcu.client import LcuClient

WRITE_NAMES = {"post", "put", "patch", "delete", "request", "send", "write"}
WRITE_CALLS = (".post(", ".put(", ".patch(", ".delete(", '"POST"', '"PUT"', '"PATCH"', '"DELETE"')


def test_client_only_has_get():
    public = {name for name, _ in inspect.getmembers(LcuClient) if not name.startswith("_")}
    assert "get" in public
    assert not (public & WRITE_NAMES), f"write-capable methods on LcuClient: {public & WRITE_NAMES}"
    methods = {n for n in public if callable(getattr(LcuClient, n))}
    assert methods <= {"get", "close"}, f"unexpected client methods: {methods - {'get', 'close'}}"


def test_lcu_package_never_uses_write_verbs():
    package_dir = Path(scout.lcu.__file__).parent
    for path in package_dir.glob("*.py"):
        text = path.read_text(encoding="utf-8")
        for call in WRITE_CALLS:
            assert call not in text, f"{path.name} contains {call}"
