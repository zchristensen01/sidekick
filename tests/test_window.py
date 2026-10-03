"""The report window's logic (M6b). No window is opened in tests."""

import threading

from scout.report.window import (
    DEFAULT_GEOMETRY,
    ReportWindow,
    line_style,
    unwrap,
    usable_geometry,
)


def test_line_styles():
    lines = ["Sidekick: bot Jhin (patch 26.19, ranked solo)", "", "YOUR LANE",
             "- Their ADC outranges yours (650 vs 525 attack range).", "DON'T LET THEM GET FED",
             "WARNINGS", "- Traits are drafts."]  # fmt: skip
    styles = [line_style(line, i) for i, line in enumerate(lines)]
    assert styles == ["title", "body", "heading", "body", "heading", "heading", "body"]


def test_window_rewraps_items_itself():
    report = "\n".join(["Sidekick: support Nautilus", "  You:  A / B", "", "PUNISH",
                        "- Lux has no dash, so once", "  Flash is down she's a target.",
                        "- Short one.", ""])  # fmt: skip
    assert unwrap(report) == ["Sidekick: support Nautilus", "  You:  A / B", "", "PUNISH",
                              "- Lux has no dash, so once Flash is down she's a target.",
                              "- Short one."]  # fmt: skip


def test_window_position_is_kept_only_if_on_screen():
    assert usable_geometry("700x800+2600+40", 3840, 1080) == "700x800+2600+40"  # second monitor
    assert usable_geometry("700x800+2600+40", 1920, 1080) == DEFAULT_GEOMETRY  # it was unplugged
    left = "700x800+-650+40"  # a monitor to the left of the main one
    assert usable_geometry(left, 1920, 1080) == left
    assert usable_geometry("garbage", 1920, 1080) == DEFAULT_GEOMETRY
    assert usable_geometry(None, 1920, 1080) == DEFAULT_GEOMETRY
    assert usable_geometry("100x100+10+10", 1920, 1080) == DEFAULT_GEOMETRY  # too small


def test_status_only_takes_short_single_lines(tmp_path):
    window = ReportWindow(tmp_path / "window.json")
    window.set_status("Champion select started.")
    window.set_status("Sidekick: bot Jhin\nYOUR LANE")
    window.set_status("=" * 100)
    queued = []
    while not window._queue.empty():
        queued.append(window._queue.get_nowait())
    assert queued == [("status", "Champion select started.")]


def test_bad_settings_file_is_ignored(tmp_path):
    (tmp_path / "window.json").write_text("{not json", encoding="utf-8")
    assert ReportWindow(tmp_path / "window.json")._settings == {}


def test_watch_loop_stops_when_asked():
    from scout.lcu.watcher import run

    class Watcher:
        recorder = None
        ticks = 0

        def tick(self):
            self.ticks += 1

    watcher, stop = Watcher(), threading.Event()

    def wait(seconds):
        if watcher.ticks >= 3:
            stop.set()

    run(watcher, 0.01, wait=wait, echo=lambda m: None, stop=stop)
    assert watcher.ticks == 3
