"""Past games for the app's History (M23): each final report's dashboard screen, kept on this PC.

The watcher saves the final report's screen next to the report as `<report>.view.json` (in the
reports folder, which is gitignored: nothing here reaches GitHub) and rewrites it when the
written version or the loading-screen records arrive. History lists them newest first, with the
account that played and, once the post-game check ran, how many calls came true
(data/history/postgame.csv, by report name). Reports from before M23 have only their text, so
History shows the text.
"""

import json
import re
from collections import defaultdict
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from scout.data.fetch import write_atomic
from scout.data.store import read_csv

VIEW_SUFFIX = ".view.json"
LIMIT = 300  # the newest this many games are listed
_NAME = re.compile(r"^\d{4}-\d{2}-\d{2}_\d{6}_[A-Za-z]+_[A-Za-z0-9'.&-]*$")  # the watcher's names


def view_path(report_path: Path) -> Path:
    return report_path.with_name(report_path.stem + VIEW_SUFFIX)


def save(report_path: Path, view: Mapping[str, Any], meta: Mapping[str, Any]) -> Path:
    """The final screen and what History lists it by (when, which account)."""
    path = view_path(report_path)
    write_atomic(path, json.dumps({"meta": dict(meta), "view": dict(view)}, ensure_ascii=False))
    return path


def listing(reports: Path, postgame_csv: Path, limit: int = LIMIT) -> list[dict[str, Any]]:
    """Every past game, newest first: the saved screens, and older reports as text."""
    results = _postgame(postgame_csv)
    names = sorted({p.name[: -len(VIEW_SUFFIX)] for p in reports.glob("*" + VIEW_SUFFIX)}
                   | {p.stem for p in reports.glob("*.md")}, reverse=True)  # fmt: skip
    out = []
    for name in names[:limit]:
        if not _NAME.match(name):
            continue
        entry = _entry(reports, name)
        if entry is not None:
            entry["postgame"] = _summary(results.get(name, []))
            out.append(entry)
    return out


def game(reports: Path, postgame_csv: Path, name: str) -> dict[str, Any] | None:
    """One past game: its screen (or its report text) and the post-game results."""
    if not _NAME.match(name):
        return None  # only the watcher's own file names, never a path from elsewhere
    entry = _entry(reports, name, full=True)
    if entry is None:
        return None
    rows = _postgame(postgame_csv).get(name, [])
    entry["postgame"] = _summary(rows)
    entry["results"] = [{"kind": r["kind"], "lane": r["lane"], "predicted": r["predicted"],
                         "actual": r["actual"], "hit": r["hit"], "measure": r["measure"]}
                        for r in rows]  # fmt: skip
    return entry


def _entry(reports: Path, name: str, full: bool = False) -> dict[str, Any] | None:
    saved = reports / (name + VIEW_SUFFIX)
    stamp, role, champ = _parts(name)
    if saved.exists():
        try:
            raw = json.loads(saved.read_text(encoding="utf-8"))
        except ValueError:
            return None
        view, meta = raw.get("view") or {}, raw.get("meta") or {}
        header = view.get("header") or {}
        entry = {
            "id": name, "at": meta.get("saved_at") or stamp, "account": meta.get("account", ""),
            "kind": "screen", "role": header.get("role", role),
            "champion": header.get("champion", champ),
            "champion_id": header.get("champion_id", ""),
            "opponents": [{"id": o.get("id", ""), "name": o.get("name", "")}
                          for o in view.get("opponents") or []],
            "written": bool(view.get("written")), "patch": header.get("patch", ""),
        }  # fmt: skip
        if full:
            entry["view"] = view
        return entry
    text_file = reports / (name + ".md")
    if not text_file.exists():
        return None
    entry = {"id": name, "at": stamp, "account": "", "kind": "text", "role": role,
             "champion": champ, "champion_id": "", "opponents": [], "written": False,
             "patch": ""}  # fmt: skip
    if full:
        entry["text"] = text_file.read_text(encoding="utf-8")
    return entry


def _parts(name: str) -> tuple[str, str, str]:
    """'2026-01-01_120000_support_Leona' -> ('2026-01-01T12:00:00', 'support', 'Leona')."""
    day, clock, role, champ = (name.split("_", 3) + ["", "", "", ""])[:4]
    stamp = f"{day}T{clock[:2]}:{clock[2:4]}:{clock[4:6]}" if len(clock) == 6 else day
    return stamp, role, champ


def _postgame(path: Path) -> dict[str, list[dict[str, str]]]:
    by_report: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in read_csv(path):
        by_report[row.get("report", "")].append(row)
    return by_report


def _summary(rows: list[dict[str, str]]) -> dict[str, int] | None:
    """{'graded': n, 'hits': n} once the post-game check ran; None before."""
    if not rows:
        return None
    graded = [r for r in rows if r.get("hit") in ("y", "n")]
    return {"graded": len(graded), "hits": sum(r["hit"] == "y" for r in graded)}
