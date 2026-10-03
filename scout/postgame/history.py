"""The post-game record (M10): every graded claim, and how often each kind and rule was right.

data/history/postgame.csv gets one row per claim (append-only; gitignored, not rebuildable).
data/history/rule_accuracy.csv is rebuilt from it after each game: hit rates per claim kind,
per lane label, and per rule (a lane rule counts the claims about its lane in that game).
"""

import csv
import json
from collections import defaultdict
from collections.abc import Sequence
from pathlib import Path

from scout.data.store import read_csv, write_csv
from scout.postgame.claims import Saved
from scout.postgame.grade import Result

POSTGAME = ("graded_at", "report", "patch", "queue", "role", "champion", "claim", "kind", "lane",
            "predicted", "actual", "hit", "measure", "rules", "inputs")  # fmt: skip
ACCURACY = ("what", "name", "claims", "graded", "hits", "hit_rate")


def append(folder: Path, saved: Saved, results: Sequence[Result], when: str) -> Path:
    path = folder / "postgame.csv"
    rows = [{
        "graded_at": when, "report": saved.path.stem, "patch": saved.patch, "queue": saved.queue,
        "role": saved.my_role, "champion": saved.my_champion, "claim": r.claim.id,
        "kind": r.claim.kind, "lane": r.claim.lane or "", "predicted": r.claim.predicted,
        "actual": r.actual, "hit": "" if r.hit is None else ("y" if r.hit else "n"),
        "measure": r.measure, "rules": "|".join(r.claim.rules),
        "inputs": json.dumps(r.claim.inputs, sort_keys=True),
    } for r in results]  # fmt: skip
    folder.mkdir(parents=True, exist_ok=True)
    new = not path.exists()
    with path.open("a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=POSTGAME, lineterminator="\n")
        if new:
            writer.writeheader()
        writer.writerows(rows)
    return path


def rebuild_accuracy(folder: Path) -> list[dict[str, str]]:
    """rule_accuracy.csv from postgame.csv: per kind, per kind + lane label, per rule."""
    counts: dict[tuple[str, str], list[int]] = defaultdict(lambda: [0, 0, 0])

    def add(key: tuple[str, str], hit: str) -> None:
        c = counts[key]
        c[0] += 1
        if hit:
            c[1] += 1
            c[2] += hit == "y"

    for row in read_csv(folder / "postgame.csv"):
        hit = row.get("hit", "")
        add(("kind", row["kind"]), hit)
        label = json.loads(row.get("inputs") or "{}").get("label")
        if label:
            add(("kind+label", f"{row['kind']}:{label}"), hit)
        for rule in filter(None, (row.get("rules") or "").split("|")):
            add(("rule", f"{rule} ({row['kind']})"), hit)
    rows = [{"what": what, "name": name, "claims": str(n), "graded": str(graded),
             "hits": str(hits), "hit_rate": f"{hits / graded:.2f}" if graded else ""}
            for (what, name), (n, graded, hits) in sorted(counts.items())]  # fmt: skip
    write_csv(folder / "rule_accuracy.csv", ACCURACY, rows)
    return rows
