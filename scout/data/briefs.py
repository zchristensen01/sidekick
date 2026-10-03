"""Matchup briefs (data/manual/matchup_briefs.csv): load, validate, find stale ones.

One row per (role, champion, opponent), from my champion's side (docs/KNOWLEDGE.md, layer 3).
`levels_1_3` starts with a verdict word, so a draft that contradicts OP.GG's lane-advantage
label can be caught: "Favored:", "Even:" or "Unfavored:". Numbers must come from either
champion's ability text (or be levels); item names aren't allowed (expected items come from
the stats). The owner owns the file: code only appends drafted rows (CLAUDE.md hard rule 4).
"""

import csv
import io
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from pathlib import Path

from scout.data.schemas import MATCHUP_BRIEFS
from scout.data.store import _LEVEL_PHRASE, _NUMBER, Row, read_csv, write_csv
from scout.model.roles import Role

LEADS = {"Favored:": "us", "Even:": "even", "Unfavored:": "them"}
TEXT_COLUMNS = ("levels_1_3", "levels_3_6", "after_6", "first_item", "trade_pattern",
                "jungle_ask")  # fmt: skip
TEXT_LIMIT = 240  # characters per column
BRIEF_SOURCES = frozenset({"owner", "llm", "claude-code"})
Key = tuple[str, str, str]  # (role, champ_id, opp_champ_id)


@dataclass(frozen=True)
class Brief:
    role: Role
    champ: str
    opp: str
    lead: str  # us | even | them, from levels_1_3
    levels_1_3: str
    levels_3_6: str
    after_6: str
    first_item: str
    trade_pattern: str
    jungle_ask: str
    reviewed: bool

    @property
    def early(self) -> str:
        """levels_1_3 without its verdict word."""
        return _strip_lead(self.levels_1_3)


@dataclass(frozen=True)
class BriefContext:
    """What briefs are checked against. Empty collections skip that check."""

    champions: frozenset[str] = frozenset()
    ability_numbers: Mapping[str, frozenset[str]] = field(default_factory=dict)
    ability_names: Mapping[str, frozenset[str]] = field(default_factory=dict)
    item_names: frozenset[str] = frozenset()
    lane_advantage: Mapping[Key, str] = field(default_factory=dict)  # OP.GG, when shown


def lead_of(text: str) -> str | None:
    return next((side for word, side in LEADS.items() if text.startswith(word)), None)


def _strip_lead(text: str) -> str:
    for word in LEADS:
        if text.startswith(word):
            return text[len(word):].strip()
    return text


def validate_brief(row: Row, context: BriefContext) -> list[str]:
    """Problems with one row, empty if it's fine."""
    if tuple(row) != MATCHUP_BRIEFS:
        return [f"columns don't match the schema: {tuple(row)}"]
    problems = []
    role, champ, opp = row["role"], row["champ_id"], row["opp_champ_id"]
    if role not in {r.value for r in Role}:
        problems.append(f"role {role!r} isn't one of {', '.join(r.value for r in Role)}")
    for name in (champ, opp):
        if not name or (context.champions and name not in context.champions):
            problems.append(f"unknown champion {name!r}")
    lead = lead_of(row["levels_1_3"])
    if lead is None:
        problems.append("levels_1_3 must start with Favored:, Even: or Unfavored:")
    data = context.lane_advantage.get((role, champ, opp))
    if lead and data and {lead, data} == {"us", "them"}:
        side = "you" if data == "us" else opp
        problems.append(f"levels_1_3 contradicts OP.GG, which gives {side} the early lane")
    kit_numbers, kit_names = context.ability_numbers, context.ability_names
    allowed = set(kit_numbers.get(champ, ())) | set(kit_numbers.get(opp, ()))
    names = set(kit_names.get(champ, ())) | set(kit_names.get(opp, ()))
    for column in TEXT_COLUMNS:
        text = row[column]
        if not text:
            problems.append(f"{column} is empty")
            continue
        if len(text) > TEXT_LIMIT:
            problems.append(f"{column} is longer than {TEXT_LIMIT} characters")
        stray = sorted(set(_NUMBER.findall(_LEVEL_PHRASE.sub("", text))) - allowed)
        if context.ability_numbers and stray:
            problems.append(f"{column} has numbers not in either kit: {', '.join(stray)}")
        prose = text
        for name in sorted(names, key=len, reverse=True):
            prose = re.sub(rf"(?<!\w){re.escape(name)}(?!\w)", " ", prose)
        items = sorted(n for n in context.item_names
                       if re.search(rf"(?<!\w){re.escape(n)}(?!\w)", prose))  # fmt: skip
        if items:
            problems.append(f"{column} names items ({', '.join(items)}); say it in general terms")
    if row["reviewed"] not in ("y", "n"):
        problems.append(f"reviewed must be y or n (got {row['reviewed']!r})")
    if row["source"] not in BRIEF_SOURCES:
        problems.append(f"source must be one of {', '.join(sorted(BRIEF_SOURCES))}")
    if row["reviewed"] == "y" and not row["reviewed_patch"]:
        problems.append("reviewed=y needs reviewed_patch")
    return problems


def validate_briefs(rows: Iterable[Row], context: BriefContext) -> list[str]:
    problems, seen = [], set()
    for row in rows:
        key = (row.get("role", ""), row.get("champ_id", ""), row.get("opp_champ_id", ""))
        where = f"{key[1]} vs {key[2]} ({key[0]})"
        if key in seen:
            problems.append(f"{where}: duplicate row")
        seen.add(key)
        problems += [f"{where}: {p}" for p in validate_brief(row, context)]
    return problems


def parse_briefs(rows: Iterable[Row]) -> dict[Key, Brief]:
    """Rows that pass the structural checks, by (role, champ, opp). Others are skipped: a bad
    row must not stop reports (`scout doctor` lists the problems)."""
    briefs = {}
    for row in rows:
        if validate_brief(row, BriefContext()):
            continue
        key = (row["role"], row["champ_id"], row["opp_champ_id"])
        briefs[key] = Brief(
            role=Role(row["role"]), champ=row["champ_id"], opp=row["opp_champ_id"],
            lead=lead_of(row["levels_1_3"]) or "even",
            **{c: row[c] for c in TEXT_COLUMNS}, reviewed=row["reviewed"] == "y",
        )  # fmt: skip
    return briefs


def stale(rows: Iterable[Row], changed: Mapping[str, str],
          lane_advantage: Mapping[Key, str]) -> list[tuple[str, str]]:  # fmt: skip
    """(champ_id, details) for `brief_stale` review rows: a champion in the brief changed
    (`changed`: champ -> reason), or OP.GG's lane advantage now points the other way."""
    found = []
    for row in rows:
        key = (row["role"], row["champ_id"], row["opp_champ_id"])
        what = f"{row['champ_id']} vs {row['opp_champ_id']} ({row['role']})"
        for champ in (row["champ_id"], row["opp_champ_id"]):
            if champ in changed:
                found.append((row["champ_id"], f"{what}: {champ} {changed[champ]}"))
        lead, data = lead_of(row["levels_1_3"]), lane_advantage.get(key)
        if lead and data and {lead, data} == {"us", "them"}:
            found.append((row["champ_id"], f"{what}: OP.GG's lane advantage is now {data}"))
    return found


def append_briefs(path: Path, rows: list[Row]) -> None:
    """Append drafted rows to matchup_briefs.csv (never rewrites existing rows).

    Raises ValueError if a row's (role, champ, opp) is already in the file.
    """
    existing = {(r["role"], r["champ_id"], r["opp_champ_id"]) for r in read_csv(path)}
    clashes = [f"{r['champ_id']} vs {r['opp_champ_id']} ({r['role']})" for r in rows
               if (r["role"], r["champ_id"], r["opp_champ_id"]) in existing]  # fmt: skip
    if clashes:
        raise ValueError(f"already in matchup_briefs.csv: {', '.join(clashes)}")
    if not path.exists():
        write_csv(path, MATCHUP_BRIEFS, [])
    text = path.read_text(encoding="utf-8")
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=list(MATCHUP_BRIEFS), lineterminator="\n")
    writer.writerows(rows)
    with path.open("a", encoding="utf-8", newline="") as f:
        if text and not text.endswith("\n"):
            f.write("\n")
        f.write(buffer.getvalue())
