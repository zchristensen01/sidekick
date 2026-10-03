"""`scout review`: walk champion traits with the owner, one champion at a time.

Order (docs/TRAITS.md, Reviewing): champions from recent games, then the champ pool, then the
rest. For each: why it's queued, its static facts and Riot's ability text, the current row;
then accept / edit / skip / quit. Accepting marks the row reviewed=y, reviewed_patch=<current>
and resolves its review queue entries; an edited row also becomes source=owner (its values then
beat every source). Changes are saved only after a yes.
"""

import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from scout.data import review
from scout.data.draft import champion_brief
from scout.data.schemas import CHAMPION_TRAITS, TRAIT_SCALES
from scout.data.store import Row, TraitContext, save_traits, validate_traits
from scout.paths import Paths

EDITABLE = (*TRAIT_SCALES, "spikes", "tags", "style", "key_note", "ult_note", "spike_note",
            "notes")  # fmt: skip


@dataclass
class ReviewItem:
    champ_id: str
    group: str  # "recent game", "your pool", "other"
    reasons: list[str]


def recent_champions(recordings: Path, champ_by_key: dict[int, str]) -> list[str]:
    """Champions in recorded champ selects, newest recording first (each listed once)."""
    seen: list[str] = []
    files = sorted(recordings.glob("*.json"), key=lambda p: p.name, reverse=True)
    for path in files:
        try:
            session = json.loads(path.read_text(encoding="utf-8"))["snapshots"][-1]["session"]
        except (OSError, ValueError, KeyError, IndexError):
            continue
        for player in session.get("myTeam", []) + session.get("theirTeam", []):
            champ = champ_by_key.get(player.get("championId") or 0)
            if champ and champ not in seen:
                seen.append(champ)
    return seen


def review_order(
    traits_rows: list[Row],
    queue_rows: list[Row],
    recent: list[str],
    pool: list[str],
    only: str | None = None,
) -> list[ReviewItem]:
    """Champions that need a look: unreviewed rows and rows with open queue entries."""
    any_role = [row for row in traits_rows if row["role"] == ""]  # role rows are edited by hand
    reasons: dict[str, list[str]] = {}
    for row in any_role:
        if row["reviewed"] != "y":
            reasons.setdefault(row["champ_id"], []).append(f"unreviewed ({row['source']})")
    have_rows = {row["champ_id"] for row in any_role}
    for entry in queue_rows:
        if entry["resolved"] != "y" and entry["champ_id"] in have_rows:
            text = entry["reason"] + (f": {entry['details']}" if entry["details"] else "")
            reasons.setdefault(entry["champ_id"], []).append(text)
    if only:
        reasons = {only: reasons.get(only, ["asked for"])} if only in have_rows else {}

    def rank(champ: str) -> tuple[int, int, str]:
        if champ in recent:
            return (0, recent.index(champ), champ)
        if champ in pool:
            return (1, pool.index(champ), champ)
        return (2, 0, champ)

    groups = {0: "recent game", 1: "your pool", 2: "other"}
    return [
        ReviewItem(champ, groups[rank(champ)[0]], reasons[champ])
        for champ in sorted(reasons, key=rank)
    ]


def format_row(row: Row) -> str:
    scales = "  ".join(f"{s} {row[s] or '-'}" for s in TRAIT_SCALES)
    return "\n".join([
        f"  {scales}",
        f"  spikes {row['spikes'] or '-'}  tags {row['tags'] or '-'}  style {row['style'] or '-'}",
        f"  key_note:   {row['key_note'] or '-'}",
        f"  ult_note:   {row['ult_note'] or '-'}",
        f"  spike_note: {row['spike_note'] or '-'}",
        f"  notes:      {row['notes'] or '-'}",
        f"  source {row['source']}, reviewed {row['reviewed']}",
    ])  # fmt: skip


@dataclass
class Session:
    paths: Paths
    version: str
    tables: dict[str, list[Row]]
    context: TraitContext
    ask: Callable[[str], str]
    echo: Callable[[str], None]
    now: Callable[[], datetime]

    def run(self, rows: list[Row], items: list[ReviewItem]) -> int:
        """Walk the items. Returns how many rows were saved."""
        saved = 0
        for number, item in enumerate(items, 1):
            row = next(r for r in rows if r["champ_id"] == item.champ_id and r["role"] == "")
            self.echo("")
            self.echo(f"=== {item.champ_id}: {number} of {len(items)} ({item.group}) ===")
            self.echo("Why: " + "; ".join(item.reasons))
            self.echo(champion_brief(self.tables, item.champ_id))
            self.echo("Current row:")
            self.echo(format_row(row))
            while True:
                choice = self.ask("[a]ccept  [e]dit  [s]kip  [q]uit").strip().lower()[:1]
                if choice == "q":
                    return saved
                if choice == "s":
                    break
                if choice in ("a", "e"):
                    updated = self._accept(row) if choice == "a" else self._edit(row)
                    if updated is not None:
                        rows[rows.index(row)] = updated
                        save_traits(self.paths, rows)
                        review.resolve(self.paths.review_queue, item.champ_id, self.now())
                        self.echo(f"Saved {item.champ_id} as reviewed.")
                        saved += 1
                        break
        return saved

    def _accept(self, row: Row) -> Row | None:
        accepted = self._reviewed(row, edited=False)
        problems = validate_traits([accepted], self.context)
        if problems:
            self.echo("Can't accept as is:\n  " + "\n  ".join(problems))
            self.echo("Choose [e]dit to fix it.")
            return None
        return accepted

    def _edit(self, row: Row) -> Row | None:
        draft = dict(row)
        self.echo("Enter keeps the current value; type '-' to clear a field.")
        for field in EDITABLE:
            answer = self.ask(f"{field} [{draft[field]}]").strip()
            if answer == "-":
                draft[field] = ""
            elif answer:
                draft[field] = answer
        edited = self._reviewed(draft, edited=any(draft[f] != row[f] for f in EDITABLE))
        problems = validate_traits([edited], self.context)
        if problems:
            self.echo("Not saved, these need fixing:\n  " + "\n  ".join(problems))
            return None
        self.echo(format_row(edited))
        if self.ask("Save this row as reviewed? [y/n]").strip().lower() != "y":
            self.echo("Not saved.")
            return None
        return edited

    def _reviewed(self, row: Row, edited: bool) -> Row:
        """Marked reviewed. Only a row the owner changed becomes source=owner (its values then beat
        every source); one accepted as is keeps its source, so Riot's ratings and the wiki's
        mechanics still fill cc, escape, frontline and the sourced tags (scout/data/sourced.py)."""
        out = {column: row[column] for column in CHAMPION_TRAITS}
        out.update(reviewed="y", reviewed_patch=self.version)
        if edited:
            out["source"] = "owner"
        return out
