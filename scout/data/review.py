"""The review queue (data/generated/review_queue.csv): add, list, and resolve entries.

Reasons are listed in scout/data/schemas.py (REVIEW_REASONS). Used by `scout refresh` and
`scout review` (M3).
"""

from collections import Counter
from datetime import datetime
from pathlib import Path

from scout.data.schemas import REVIEW_QUEUE, REVIEW_REASONS
from scout.data.store import Row, read_csv, write_csv


def entry(champ_id: str, reason: str, details: str, patch: str, now: datetime) -> Row:
    if reason not in REVIEW_REASONS:
        raise ValueError(f"unknown review reason {reason!r} (see REVIEW_REASONS)")
    return {
        "champ_id": champ_id, "reason": reason, "details": details, "patch_detected": patch,
        "created_at": now.isoformat(timespec="seconds"), "resolved": "n", "resolved_at": "",
    }  # fmt: skip


def add(path: Path, new_rows: list[Row]) -> list[Row]:
    """Append rows that aren't already open (same champion, reason and details). Returns them."""
    rows = read_csv(path)
    open_keys = {(r["champ_id"], r["reason"], r["details"]) for r in rows if r["resolved"] != "y"}
    added = []
    for row in new_rows:
        key = (row["champ_id"], row["reason"], row["details"])
        if key not in open_keys:
            open_keys.add(key)
            added.append(row)
    if added or not path.exists():
        write_csv(path, REVIEW_QUEUE, rows + added)
    return added


def open_entries(path: Path) -> list[Row]:
    return [r for r in read_csv(path) if r["resolved"] != "y"]


def resolve(path: Path, champ_id: str, now: datetime) -> int:
    """Mark every open entry for a champion resolved. Returns how many were open."""
    rows = read_csv(path)
    count = 0
    for row in rows:
        if row["champ_id"] == champ_id and row["resolved"] != "y":
            row["resolved"], row["resolved_at"] = "y", now.isoformat(timespec="seconds")
            count += 1
    if count:
        write_csv(path, REVIEW_QUEUE, rows)
    return count


def summarize(rows: list[Row]) -> str:
    """'traits_missing 170, new_champion 1' (most common first)."""
    counts = Counter(r["reason"] for r in rows)
    return ", ".join(f"{reason} {n}" for reason, n in counts.most_common()) or "nothing new"
