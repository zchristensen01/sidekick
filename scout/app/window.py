"""The Sidekick app window (M13, M14): the dashboard page in a native window (pywebview, Edge).

The watcher runs in a background thread and hands screens to a Bridge; the page polls the
Bridge a few times a second (no callbacks into the page, so no threading trouble). The page's
buttons (Settings, Update, Refresh) call `action(name, payload)`, which the app answers
(scout/app/main.py). Closing the window stops everything. The window remembers its size
and position.
"""

import base64
import json
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any

PAGE = Path(__file__).with_name("dashboard.html")
ICON = Path(__file__).with_name("sidekick.ico")
LOGO = Path(__file__).with_name("sidekick.png")
Actions = Callable[[str, dict[str, Any]], dict[str, Any]]
DEFAULT = {"width": 1280, "height": 820, "x": None, "y": None}


class Bridge:
    """The latest screen and status line, shared between the watcher thread and the page."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._version = 0
        self._view: dict[str, Any] | None = None
        self._message = ""
        self.closer: Callable[[], None] | None = None  # set when the window opens

    def close(self) -> None:
        """Close the window (and so the app) from any thread."""
        if self.closer is not None:
            self.closer()

    def show(self, view: dict[str, Any]) -> None:
        with self._lock:
            self._version += 1
            self._view = view

    def status(self, message: str) -> None:
        with self._lock:
            self._message = message

    def poll(self, version: int) -> dict[str, Any]:
        with self._lock:
            changed = version != self._version
            return {"version": self._version, "view": self._view if changed else None,
                    "message": self._message}  # fmt: skip

    @property
    def view(self) -> dict[str, Any] | None:
        with self._lock:
            return self._view


class Api:
    """What the page can call (pywebview exposes public methods as `pywebview.api.*`)."""

    def __init__(self, bridge: Bridge, actions: Actions | None = None,
                 meta: Callable[[], dict[str, Any]] | None = None) -> None:  # fmt: skip
        self._bridge, self._actions, self._meta = bridge, actions, meta

    def poll(self, version: int) -> dict[str, Any]:
        reply = self._bridge.poll(int(version))
        reply["meta"] = self._meta() if self._meta else {}
        return reply

    def action(self, name: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        if self._actions is None:
            return {"error": "Not available here."}
        return self._actions(str(name), payload if isinstance(payload, dict) else {})


class Settings:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.data = dict(DEFAULT)
        try:
            saved = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(saved, dict):
                self.data.update({k: saved[k] for k in DEFAULT if k in saved})
        except (OSError, ValueError):
            pass  # first run, or a broken file: defaults

    def save(self) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps(self.data, indent=1), encoding="utf-8")
        except OSError:
            pass


def on_screen(x: int | None, y: int | None, width: int, screens: list[Any]) -> bool:
    """A saved position is used only if it's still on a connected monitor."""
    if x is None or y is None:
        return False
    return any(s.x - width + 80 <= x <= s.x + s.width - 80 and s.y <= y <= s.y + s.height - 80
               for s in screens)  # fmt: skip


def page() -> str:
    """The dashboard with the logo inlined (the page is loaded as text, not from a file)."""
    html = PAGE.read_text(encoding="utf-8")
    logo = "data:image/png;base64," + base64.b64encode(LOGO.read_bytes()).decode()
    return html.replace("__LOGO__", logo)


def run(start: Callable[[Bridge, threading.Event], None], settings_file: Path,
        title: str = "Sidekick", actions: Actions | None = None,
        meta: Callable[[], dict[str, Any]] | None = None) -> None:  # fmt: skip
    """Open the window and run `start(bridge, stop)` in a background thread until it closes."""
    import webview  # Windows-only dependency, imported when the app actually opens

    settings = Settings(settings_file)
    bridge = Bridge()
    stop = threading.Event()
    d = settings.data
    x, y = d.get("x"), d.get("y")
    if not on_screen(x, y, int(d["width"]), list(webview.screens)):
        x = y = None
    window = webview.create_window(
        title, html=page(), js_api=Api(bridge, actions, meta),
        width=int(d["width"]), height=int(d["height"]), x=x, y=y, min_size=(900, 600),
        background_color="#0a111c",
    )  # fmt: skip

    def remember() -> None:
        try:
            settings.data.update(width=window.width, height=window.height, x=window.x, y=window.y)
            settings.save()
        except Exception:  # the window may already be gone; position isn't worth a crash
            pass

    window.events.closing += remember
    bridge.closer = window.destroy

    def background() -> None:
        threading.Thread(target=start, args=(bridge, stop), daemon=True).start()

    try:
        webview.start(background, gui="edgechromium", icon=str(ICON))
    finally:
        stop.set()
