"""Agents' replies from research/results/ (M19): checked, shown, applied with the owner's OK.

A reply is recognized by its CSV table's columns, not its file name:
- champ_id, patch, what_changed, quote: kit changes in a patch's notes, to the review queue
  (reason `patch_notes`);
- fact_id, topic, role, text, source, source_url, patch, checked_on: game facts, to
  data/manual/game_facts.csv;
- class, quote, source, source_url: Riot's class definitions, to
  data/manual/class_definitions.csv.

Every row is checked (a known champion id, a source and an https link where the table has them,
a patch), problems are listed instead of applied, and nothing is written until `apply`. Applied
replies move to research/results/done/.

The patch notes reply may carry game facts too (only what that patch changed). When the game
facts reply (a full re-check of every fact) has the same fact, the game facts reply's row wins.
"""

import csv
import io
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from scout.data import patch_updates, review
from scout.data.schemas import CLASS_DEFINITIONS, GAME_FACTS
from scout.data.store import Row, read_csv, write_csv
from scout.paths import Paths

KIT = ("champ_id", "patch", "what_changed", "quote")
# research/status.csv: which prompt was done for which patch; for patch_notes, the patch page's
# mid-patch updates it covered ("; "-separated, scout/data/patch_updates.py)
STATUS = ("prompt", "patch", "done_on", "covered")
PROMPT_OF = {"kit_changes": "patch_notes", "game_facts": "game_facts",
             "class_definitions": "class_definitions"}  # fmt: skip
PER_PATCH = ("patch_notes", "game_facts")  # due again every new patch; class_definitions once
KINDS = {KIT: "kit_changes", GAME_FACTS: "game_facts", CLASS_DEFINITIONS[:4]: "class_definitions"}
_BLOCK = re.compile(r"```csv\s*\n(.*?)```", re.S)


@dataclass
class Reply:
    path: Path
    tables: dict[str, list[Row]] = field(default_factory=dict)  # kind -> rows
    problems: list[str] = field(default_factory=list)


@dataclass
class Plan:
    replies: list[Reply]
    review_rows: list[Row] = field(default_factory=list)
    facts_changed: list[tuple[Row, Row]] = field(default_factory=list)  # (old, new)
    facts_added: list[Row] = field(default_factory=list)
    classes: list[Row] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)  # what was set aside, and why

    @property
    def empty(self) -> bool:
        return not (self.review_rows or self.facts_changed or self.facts_added or self.classes)

    def lines(self) -> list[str]:
        out = []
        for reply in self.replies:
            kinds = ", ".join(f"{k} ({len(v)} rows)" for k, v in reply.tables.items()) or "nothing"
            out.append(f"{reply.path.name}: {kinds}")
            out += [f"  problem: {p}" for p in reply.problems]
        out += [f"Review queue: {r['champ_id']} ({r['details'][:70]})" for r in self.review_rows]
        out += [f"Game fact {new['fact_id']}: \"{old['text']}\" -> \"{new['text']}\" "
                f"({new['source']})" for old, new in self.facts_changed]  # fmt: skip
        out += [f"New game fact {r['fact_id']}: \"{r['text']}\" ({r['source']})"
                for r in self.facts_added]  # fmt: skip
        out += [f"Class definition: {r['class']} ({r['source']})" for r in self.classes]
        out += [f"Note: {n}" for n in self.notes]
        return out or ["Nothing to change."]


def read_reply(path: Path, champions: Iterable[str]) -> Reply:
    known = set(champions)
    reply = Reply(path)
    text = path.read_text(encoding="utf-8")
    for block in _BLOCK.findall(text):
        rows = list(csv.DictReader(io.StringIO(block.strip() + "\n")))
        header = tuple(h.strip() for h in (csv.reader(io.StringIO(block.strip())).__next__()))
        kind = KINDS.get(header)
        if kind is None:
            reply.problems.append(f"a table with unknown columns: {', '.join(header)}")
            continue
        good = []
        for i, row in enumerate(rows, 2):
            row = {k.strip(): (v or "").strip() for k, v in row.items() if k}
            problem = _check(kind, row, known)
            if problem:
                reply.problems.append(f"row {i}: {problem}")
            else:
                good.append(row)
        reply.tables.setdefault(kind, []).extend(good)
    if not reply.tables and not reply.problems:
        reply.problems.append("no CSV table found (it should be in a ```csv block)")
    return reply


def _check(kind: str, row: Mapping[str, str], known: set[str]) -> str:
    if kind == "kit_changes":
        if row.get("champ_id") not in known:
            return f"unknown champion id {row.get('champ_id')!r}"
        if not row.get("quote"):
            return "no quote from the patch notes"
    if kind in ("game_facts", "class_definitions"):
        if not row.get("source") or not row.get("source_url", "").startswith("https://"):
            return "no source or no https link"
        if kind == "game_facts" and (not row.get("fact_id") or not row.get("text")
                                     or not row.get("patch")):  # fmt: skip
            return "a game fact needs fact_id, text and patch"
        if kind == "class_definitions" and not (row.get("class") and row.get("quote")):
            return "a class definition needs the class and Riot's quote"
    if kind != "class_definitions" and not row.get("patch"):
        return "no patch"
    return ""


def plan(paths: Paths, champions: Iterable[str], now: datetime,
         files: Sequence[Path] | None = None) -> Plan:  # fmt: skip
    folder = paths.research_dir / "results"
    found = files if files is not None else sorted(
        p for p in folder.glob("*.md") if p.name.lower() != "readme.md"
    )  # fmt: skip
    replies = [read_reply(p, champions) for p in found]
    result = Plan(replies)
    facts = {r["fact_id"]: r for r in read_csv(paths.manual_dir / "game_facts.csv")}
    classes = {r["class"].lower(): r for r in read_csv(paths.manual_dir / "class_definitions.csv")}
    # game facts by id: a full game facts check beats a patch notes reply's partial row
    chosen: dict[str, tuple[bool, Row, str]] = {}  # fact_id -> (from the full check, row, file)
    for reply in replies:
        full = "kit_changes" not in reply.tables
        for row in reply.tables.get("game_facts", []):
            before = chosen.get(row["fact_id"])
            if before is not None and before[0] and not full:
                result.notes.append(f"{row['fact_id']}: kept the game facts check's row "
                                    f"({before[2]}), not {reply.path.name}'s")  # fmt: skip
                continue
            if before is not None and full and not before[0]:
                result.notes.append(f"{row['fact_id']}: kept the game facts check's row "
                                    f"({reply.path.name}), not {before[2]}'s")  # fmt: skip
            chosen[row["fact_id"]] = (full, row, reply.path.name)
    for _, row, _ in chosen.values():
        old = facts.get(row["fact_id"])
        new = {c: row.get(c, "") for c in GAME_FACTS}
        if old is None:
            result.facts_added.append(new)
        elif (old["text"], old["source_url"]) != (new["text"], new["source_url"]):
            result.facts_changed.append((old, new))
    for reply in replies:
        for row in reply.tables.get("kit_changes", []):
            details = f"patch {row['patch']}: {row['what_changed']}: {row['quote']}"[:300]
            result.review_rows.append(review.entry(row["champ_id"], "patch_notes", details,
                                                   row["patch"], now))  # fmt: skip
        for row in reply.tables.get("class_definitions", []):
            old = classes.get(row["class"].lower())
            new = {"class": row["class"], "quote": row["quote"], "source": row["source"],
                   "source_url": row["source_url"],
                   "checked_on": now.date().isoformat()}  # fmt: skip
            if old is None or old["quote"] != new["quote"]:
                result.classes.append(new)
    return result


def status_file(paths: Paths) -> Path:
    return paths.research_dir / "status.csv"


def record_done(paths: Paths, prompts: Iterable[str], patch: str, when: str) -> None:
    """Mark prompts as done for a patch (short patch, e.g. 16.19), in research/status.csv. The
    patch notes prompt also records the mid-patch updates known now (it was asked about them)."""
    rows = {r["prompt"]: r for r in read_csv(status_file(paths))}
    for prompt in prompts:
        covered = known_updates(paths, patch) if prompt == "patch_notes" else []
        rows[prompt] = {"prompt": prompt, "patch": patch, "done_on": when,
                        "covered": "; ".join(covered)}  # fmt: skip
    write_csv(status_file(paths), STATUS, sorted(rows.values(), key=lambda r: r["prompt"]))


def known_updates(paths: Paths, patch: str) -> list[str]:
    """The patch page's mid-patch updates from the last refresh, for this patch only."""
    found = patch_updates.load(paths)
    return list(found.updates) if found is not None and found.patch == patch else []


def done_rows(paths: Paths) -> dict[str, Row]:
    return {r["prompt"]: r for r in read_csv(status_file(paths))}


def new_updates(paths: Paths, patch: str) -> list[str]:
    """Mid-patch updates (hotfixes) that appeared after this patch's notes were researched."""
    row = done_rows(paths).get("patch_notes")
    if row is None or row.get("patch") != patch:
        return []  # the whole patch is due anyway
    covered = {t.strip() for t in (row.get("covered") or "").split(";") if t.strip()}
    return [t for t in known_updates(paths, patch) if t not in covered]


def due(paths: Paths, patch: str) -> list[str]:
    """Prompts to run now: the per-patch ones not done for this patch (or patch notes again
    after a new mid-patch update), and any never done."""
    done = {p: r["patch"] for p, r in done_rows(paths).items()}
    out = [p for p in PER_PATCH if done.get(p) != patch]
    if "patch_notes" not in out and new_updates(paths, patch):
        out.insert(0, "patch_notes")
    if "class_definitions" not in done:
        out.append("class_definitions")
    return out


def apply(paths: Paths, p: Plan, patch: str = "") -> list[str]:
    """Write what the plan says (the owner confirmed it); move the replies to results/done/; mark
    the prompts done for `patch` (the current short patch)."""
    done = []
    if p.review_rows:
        added = review.add(paths.review_queue, p.review_rows)
        done.append(f"review queue: +{len(added)}")
    if p.facts_changed or p.facts_added:
        path = paths.manual_dir / "game_facts.csv"
        rows = read_csv(path)
        changed = {new["fact_id"]: new for _, new in p.facts_changed}
        rows = [changed.get(r["fact_id"], r) for r in rows] + p.facts_added
        write_csv(path, GAME_FACTS, rows)
        done.append(f"game facts: {len(changed)} changed, {len(p.facts_added)} added")
    if p.classes:
        path = paths.manual_dir / "class_definitions.csv"
        rows = {r["class"].lower(): r for r in read_csv(path)}
        rows |= {r["class"].lower(): r for r in p.classes}
        write_csv(path, CLASS_DEFINITIONS, sorted(rows.values(), key=lambda r: r["class"]))
        done.append(f"class definitions: {len(p.classes)}")
    target = paths.research_dir / "results" / "done"
    kinds = set()
    for reply in p.replies:
        if reply.tables:
            kinds |= set(reply.tables)
            target.mkdir(parents=True, exist_ok=True)
            reply.path.replace(target / reply.path.name)
    if patch and kinds:
        record_done(paths, sorted(PROMPT_OF[k] for k in kinds), patch,
                    datetime.now().date().isoformat())  # fmt: skip
    return done
