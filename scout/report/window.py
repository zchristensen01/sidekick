"""A small report window (M6b): drag it to a second monitor and it reopens there.

It shows the latest report and changes only when `scout watch` re-renders (a trade, the
loading-screen role check). Pre-game only: no timers, no live prompts (docs/POLICY.md).
Built on tkinter, which ships with Python. Thread-safe: the watcher runs in another thread
and hands over text through a queue.
"""

import json
import queue
import re
from collections.abc import Callable
from pathlib import Path
from typing import Any

DEFAULT_GEOMETRY = "760x900+80+60"
FONT_SIZES = (9, 10, 11, 12, 13, 14, 16)
POLL_MS = 150
_HEADING = re.compile(r"[A-Z][A-Z0-9 '/:,.()-]+")
_GEOMETRY = re.compile(r"(\d+)x(\d+)([+-]-?\d+)([+-]-?\d+)")


def line_style(line: str, index: int) -> str:
    """How to show one line of a rendered report: title, heading, warning, or body."""
    if index == 0:
        return "title"
    if _HEADING.fullmatch(line.strip()) and len(line.strip()) > 2:
        return "heading"
    return "body"


def unwrap(report: str) -> list[str]:
    """Undo the terminal's line wrapping so the window wraps items to its own width (a narrow
    window otherwise breaks every pre-wrapped line a second time)."""
    lines: list[str] = []
    for line in report.rstrip("\n").splitlines():
        if line.startswith("  ") and line.strip() and lines and lines[-1].startswith("- "):
            lines[-1] += " " + line.strip()
        else:
            lines.append(line)
    return lines


def usable_geometry(saved: str | None, screen_width: int, screen_height: int) -> str:
    """The saved window position if it's still on a screen, else the default.

    `screen_*` is the whole desktop (all monitors), so a window parked on a monitor that's
    since been unplugged comes back to the main one.
    """
    match = _GEOMETRY.fullmatch(saved or "")
    if not match:
        return DEFAULT_GEOMETRY
    width, height, x, y = (int(v.lstrip("+")) for v in match.groups())  # "+-650" -> -650
    on_screen = -width < x < screen_width - 50 and 0 <= y < screen_height - 50
    return saved if on_screen and width >= 300 and height >= 200 else DEFAULT_GEOMETRY


class ReportWindow:
    def __init__(self, settings_file: Path) -> None:
        self._settings_file = settings_file
        self._queue: queue.Queue[tuple[str, Any]] = queue.Queue()
        self._settings = self._load_settings()
        self.shown: list[str] = []  # reports displayed, newest last (for checks)

    # ------------------------------------------------------------ thread-safe API

    def show_report(self, title: str, text: str) -> None:
        self._queue.put(("report", (title, text)))

    def set_status(self, text: str) -> None:
        if "\n" not in text and not text.startswith("=") and len(text) <= 160:
            self._queue.put(("status", text))

    def close(self) -> None:
        self._queue.put(("close", None))

    # ------------------------------------------------------------ main thread

    def run(self, on_tick: Callable[[], None] | None = None) -> None:
        """Open the window and block until it's closed (or Ctrl+C in the terminal)."""
        import tkinter as tk
        from tkinter import font as tkfont

        root = tk.Tk()
        root.title("Sidekick")
        saved = self._settings.get("geometry")
        root.geometry(usable_geometry(saved, root.winfo_vrootwidth(), root.winfo_vrootheight()))
        root.minsize(320, 240)

        size = tk.IntVar(value=int(self._settings.get("font_size", 11)))
        on_top = tk.BooleanVar(value=bool(self._settings.get("on_top", False)))
        body = tkfont.Font(family="Consolas", size=size.get())
        bold = tkfont.Font(family="Consolas", size=size.get(), weight="bold")
        title_font = tkfont.Font(family="Segoe UI", size=size.get() + 2, weight="bold")

        bar = tk.Frame(root)
        bar.pack(side="top", fill="x")
        heading = tk.Label(bar, text="Waiting for a report...", anchor="w",
                           font=("Segoe UI", 10, "bold"))  # fmt: skip
        heading.pack(side="left", padx=8, pady=4)

        def resize(step: int) -> None:
            sizes = list(FONT_SIZES)
            current = size.get() if size.get() in sizes else 11
            new = sizes[max(0, min(len(sizes) - 1, sizes.index(current) + step))]
            size.set(new)
            body.configure(size=new)
            bold.configure(size=new)
            title_font.configure(size=new + 2)

        def toggle_top() -> None:
            root.attributes("-topmost", on_top.get())

        tk.Button(bar, text="A+", width=3, command=lambda: resize(1)).pack(side="right", padx=2)
        tk.Button(bar, text="A-", width=3, command=lambda: resize(-1)).pack(side="right", padx=2)
        tk.Checkbutton(bar, text="Always on top", variable=on_top,
                       command=toggle_top).pack(side="right", padx=6)  # fmt: skip
        toggle_top()

        frame = tk.Frame(root)
        frame.pack(side="top", fill="both", expand=True)
        scroll = tk.Scrollbar(frame)
        scroll.pack(side="right", fill="y")
        text = tk.Text(frame, wrap="word", font=body, padx=10, pady=8, relief="flat",
                       yscrollcommand=scroll.set, state="disabled", cursor="arrow")  # fmt: skip
        text.pack(side="left", fill="both", expand=True)
        scroll.configure(command=text.yview)
        text.tag_configure("title", font=title_font, spacing3=6)
        text.tag_configure("heading", font=bold, spacing1=8, foreground="#1f4e8c")
        text.tag_configure("body", font=body, lmargin2=18)

        status = tk.Label(root, text="Starting...", anchor="w", relief="sunken", padx=6)
        status.pack(side="bottom", fill="x")

        def show(title: str, report: str) -> None:
            heading.configure(text=title)
            text.configure(state="normal")
            text.delete("1.0", "end")
            for index, line in enumerate(unwrap(report)):
                text.insert("end", line + "\n", line_style(line, index))
            text.configure(state="disabled")
            text.yview_moveto(0)
            root.deiconify()
            # Bring it in front of other windows without taking keyboard focus from the game
            # client: on top for a moment, then back to the user's setting.
            root.attributes("-topmost", True)
            root.after(300, lambda: root.attributes("-topmost", on_top.get()))
            self.shown.append(report)

        def save_settings() -> None:
            self._settings.update(geometry=root.geometry(), font_size=size.get(),
                                  on_top=on_top.get())  # fmt: skip
            self._save_settings()

        def close() -> None:
            save_settings()
            root.destroy()

        def poll() -> None:
            if on_tick is not None:
                on_tick()
            try:
                while True:
                    kind, payload = self._queue.get_nowait()
                    if kind == "report":
                        show(*payload)
                    elif kind == "status":
                        status.configure(text=payload)
                    elif kind == "close":
                        close()
                        return
            except queue.Empty:
                pass
            root.after(POLL_MS, poll)

        def on_error(kind, value, tb) -> None:  # Ctrl+C lands here while Tk is running
            if issubclass(kind, KeyboardInterrupt):
                close()
            else:
                import traceback

                traceback.print_exception(kind, value, tb)

        root.report_callback_exception = on_error
        root.protocol("WM_DELETE_WINDOW", close)
        root.after(POLL_MS, poll)
        root.mainloop()

    # ------------------------------------------------------------ settings

    def _load_settings(self) -> dict[str, Any]:
        try:
            loaded = json.loads(self._settings_file.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        return loaded if isinstance(loaded, dict) else {}

    def _save_settings(self) -> None:
        try:
            self._settings_file.parent.mkdir(parents=True, exist_ok=True)
            self._settings_file.write_text(json.dumps(self._settings), encoding="utf-8")
        except OSError:
            pass  # remembering the position is a convenience, never worth an error
