"""Load and validate data from disk: static CSVs, manual CSVs, the stats database.

Builds ChampFacts (scout/model/champ.py) by merging generated static data, the owner's traits and
overrides, and stats. Validates trait rows per docs/TRAITS.md (scales, tags, spikes, text
fields). Never writes to data/manual/ except appending drafted rows. Trait loading and
ChampFacts come in M3; M2 needs the CSV helpers and the static-data readers.
"""

import csv
import dataclasses
import io
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from scout.data import sourced
from scout.data.fetch import write_atomic
from scout.data.schemas import (
    CHAMPION_TRAITS,
    JUNGLE_STYLES,
    MATCHUP_NOTES,
    STATIC_FILES,
    TRAIT_SCALE_RANGE,
    TRAIT_SCALES,
    TRAIT_SOURCES,
    TRAIT_TAGS,
)
from scout.model.champ import ChampFacts, Traits
from scout.model.roles import Role
from scout.paths import Paths

if TYPE_CHECKING:
    from scout.data.briefs import Brief

Row = dict[str, str]


def read_csv(path: Path) -> list[Row]:
    """Rows of a CSV file as dicts. A missing file is an empty list."""
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as f:
        return [dict(row) for row in csv.DictReader(f)]


def write_csv(path: Path, columns: Iterable[str], rows: Iterable[Mapping[str, object]]) -> None:
    """Write rows with exactly these columns (LF line endings, written atomically)."""
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=list(columns), lineterminator="\n")
    writer.writeheader()
    for row in rows:
        writer.writerow({k: "" if v is None else v for k, v in row.items()})
    write_atomic(path, buffer.getvalue())


def current_version(paths: Paths) -> str | None:
    """The Data Dragon version in data/generated/PATCH, or None before the first refresh."""
    if not paths.patch_file.exists():
        return None
    return paths.patch_file.read_text(encoding="utf-8").strip() or None


def static_complete(paths: Paths, version: str) -> bool:
    """Every static file is there with the columns this code expects (an app update that
    changes a file's columns makes the next refresh rebuild it)."""
    folder = paths.static_dir(version)
    if not (folder / "manifest.json").exists():
        return False
    for name, columns in STATIC_FILES.items():
        try:
            with (folder / name).open(newline="", encoding="utf-8") as f:
                header = next(csv.reader(f), [])
        except OSError:
            return False
        if header != list(columns):
            return False
    return True


def load_static(paths: Paths, version: str) -> dict[str, list[Row]]:
    """Every static CSV for a version, by file name ({} if that version wasn't built)."""
    folder = paths.static_dir(version)
    return {name: read_csv(folder / name) for name in STATIC_FILES if (folder / name).exists()}


def traits_champ_ids(paths: Paths) -> set[str]:
    """Champions with at least one row in data/manual/champion_traits.csv."""
    return {row["champ_id"] for row in read_csv(paths.manual_dir / "champion_traits.csv")}


# ---------------------------------------------------------------- traits (docs/TRAITS.md)

TEXT_LIMITS = {"key_note": 240, "ult_note": 320, "spike_note": 200}  # characters
_NUMBER = re.compile(r"\d+(?:\.\d+)?")
# "level 6", "levels 1-3", "level 2 or 3": level mentions are allowed numbers.
_LEVEL_PHRASE = re.compile(r"\blevels? \d+(?:\s*(?:-|to|and|or)\s*\d+)*", re.I)


@dataclass(frozen=True)
class TraitContext:
    """What the validator checks rows against. Empty sets skip that check."""

    champions: frozenset[str] = frozenset()  # known Data Dragon ids
    ability_numbers: Mapping[str, frozenset[str]] = field(default_factory=dict)
    ability_names: Mapping[str, frozenset[str]] = field(default_factory=dict)
    item_names: frozenset[str] = frozenset()


def trait_context(paths: Paths, version: str | None) -> TraitContext:
    """Validator context from the static data for `version` (empty if not built)."""
    tables = load_static(paths, version) if version else {}
    numbers: dict[str, set[str]] = {}
    names: dict[str, set[str]] = {}
    for row in tables.get("abilities.csv", []):
        text = f"{row['description']} {row['cooldowns'].replace('|', ' ')}"
        numbers.setdefault(row["champ_id"], set()).update(_NUMBER.findall(text))
        names.setdefault(row["champ_id"], set()).update(
            part.strip() for part in row["name"].split("/") if part.strip()
        )
    return TraitContext(
        champions=frozenset(r["champ_id"] for r in tables.get("champions.csv", [])),
        ability_numbers={k: frozenset(v) for k, v in numbers.items()},
        ability_names={k: frozenset(v) for k, v in names.items()},
        item_names=frozenset(r["name"] for r in tables.get("items.csv", [])),
    )


def validate_traits(rows: list[Row], context: TraitContext) -> list[str]:
    """Problems in champion_traits.csv rows, as 'Champ (role): problem'. Empty = valid."""
    problems: list[str] = []
    seen: set[tuple[str, str]] = set()
    for row in rows:
        where = f"{row.get('champ_id') or '?'} ({row.get('role') or 'any role'})"
        for problem in _row_problems(row, context):
            problems.append(f"{where}: {problem}")
        key = (row.get("champ_id", ""), row.get("role", ""))
        if key in seen:
            problems.append(f"{where}: duplicate row (champ_id, role must be unique)")
        seen.add(key)
    return problems


def _row_problems(row: Row, context: TraitContext) -> list[str]:
    problems: list[str] = []
    if tuple(row) != CHAMPION_TRAITS:
        return [f"columns don't match the schema: {tuple(row)}"]
    champ = row["champ_id"]
    if not champ:
        return ["empty champ_id"]
    if context.champions and champ not in context.champions:
        problems.append("unknown champion (not in champions.csv)")
    if row["role"] and row["role"] not in {r.value for r in Role}:
        problems.append(f"role {row['role']!r} isn't one of {', '.join(r.value for r in Role)}")

    complete = row["reviewed"] == "y" or row["source"] == "llm"  # these need every field
    for scale in TRAIT_SCALES:
        value = row[scale]
        if value == "":
            if complete:
                problems.append(f"{scale} is empty")
        elif not value.isdigit() or int(value) not in TRAIT_SCALE_RANGE:
            problems.append(f"{scale} must be 0-3 (got {value!r})")

    spikes = [s for s in row["spikes"].split("|") if s] if row["spikes"] else []
    if any(not s.isdigit() or not 1 <= int(s) <= 18 for s in spikes):
        problems.append(f"spikes must be levels 1-18 like 2|6 (got {row['spikes']!r})")
    elif spikes != sorted(set(spikes), key=int):
        problems.append(f"spikes must be ascending without repeats (got {row['spikes']!r})")
    unknown_tags = [t for t in row["tags"].split("|") if t and t not in TRAIT_TAGS]
    if unknown_tags:
        problems.append(f"unknown tags {', '.join(unknown_tags)} (vocabulary: docs/TRAITS.md)")
    if row["style"] not in JUNGLE_STYLES:
        problems.append(f"style must be ganker, farmer or blank (got {row['style']!r})")
    elif row["style"] and row["role"] not in ("", Role.JUNGLE.value):
        problems.append("style is for junglers only")

    if row["reviewed"] not in ("y", "n"):
        problems.append(f"reviewed must be y or n (got {row['reviewed']!r})")
    if row["source"] not in TRAIT_SOURCES:
        problems.append(f"source must be one of {', '.join(sorted(TRAIT_SOURCES))}")
    if row["reviewed"] == "y" and not row["reviewed_patch"]:
        problems.append("reviewed=y needs reviewed_patch")

    allowed_numbers = set(spikes) | set(context.ability_numbers.get(champ, ()))
    own_names = context.ability_names.get(champ, frozenset())
    for column, limit in TEXT_LIMITS.items():
        text = row[column]
        if not text:
            if complete:
                problems.append(f"{column} is empty")
            continue
        if len(text) > limit:
            problems.append(f"{column} is longer than {limit} characters")
        stray = sorted(set(_NUMBER.findall(_LEVEL_PHRASE.sub("", text))) - allowed_numbers)
        if context.ability_numbers and stray:
            problems.append(f"{column} has numbers not in the ability text: {', '.join(stray)}")
        # The champion's own ability names can contain item names (Mel's "Golden Eclipse",
        # Renekton's "Cull the Meek"), so they're taken out before looking for items.
        prose = text
        for name in sorted(own_names, key=len, reverse=True):
            prose = re.sub(rf"(?<!\w){re.escape(name)}(?!\w)", " ", prose)
        items = sorted(
            name for name in context.item_names
            if re.search(rf"(?<!\w){re.escape(name)}(?!\w)", prose)
        )  # fmt: skip
        if items:
            problems.append(f"{column} names items ({', '.join(items)}); say it in general terms")
    return problems


def parse_traits(row: Row) -> Traits:
    """A validated champion_traits.csv row as Traits (blank scales become None)."""

    def scale(name: str) -> int | None:
        return int(row[name]) if row[name] != "" else None

    return Traits(
        early=scale("early"), engage=scale("engage"), cc=scale("cc"), escape=scale("escape"),
        scaling=scale("scaling"), roam=scale("roam"), waveclear=scale("waveclear"),
        frontline=scale("frontline"),
        spikes=tuple(int(s) for s in row["spikes"].split("|") if s),
        tags=frozenset(t for t in row["tags"].split("|") if t),
        style=row["style"], key_note=row["key_note"], ult_note=row["ult_note"],
        spike_note=row["spike_note"], reviewed=row["reviewed"] == "y",
        reviewed_patch=row["reviewed_patch"], source=row["source"],
    )  # fmt: skip


def traits_for(
    traits: Mapping[tuple[str, str], Traits], champ_id: str, role: Role
) -> Traits | None:
    """The row for this champion in this role, else its any-role row (docs/TRAITS.md)."""
    return traits.get((champ_id, role.value)) or traits.get((champ_id, ""))


def append_note(paths: Paths, row: Row) -> None:
    """Append one of this user's matchup notes (matchup_notes.csv in their folder; append only)."""
    path = paths.notes_file
    if not path.exists():
        write_csv(path, MATCHUP_NOTES, [])
    text = path.read_text(encoding="utf-8")
    buffer = io.StringIO()
    csv.DictWriter(buffer, fieldnames=list(MATCHUP_NOTES), lineterminator="\n").writerow(row)
    with path.open("a", encoding="utf-8", newline="") as f:
        f.write(("" if not text or text.endswith("\n") else "\n") + buffer.getvalue())


def append_traits(paths: Paths, rows: list[Row]) -> None:
    """Append drafted rows to data/manual/champion_traits.csv (never rewrites existing rows).

    Raises ValueError if a row's (champ_id, role) is already in the file.
    """
    path = paths.manual_dir / "champion_traits.csv"
    existing = {(r["champ_id"], r["role"]) for r in read_csv(path)}
    clashes = [f"{r['champ_id']} ({r['role'] or 'any role'})" for r in rows
               if (r["champ_id"], r["role"]) in existing]  # fmt: skip
    if clashes:
        raise ValueError(f"already in champion_traits.csv: {', '.join(clashes)}")
    if not path.exists():
        write_csv(path, CHAMPION_TRAITS, [])
    text = path.read_text(encoding="utf-8")
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=list(CHAMPION_TRAITS), lineterminator="\n")
    writer.writerows(rows)
    with path.open("a", encoding="utf-8", newline="") as f:
        if text and not text.endswith("\n"):
            f.write("\n")
        f.write(buffer.getvalue())


def save_traits(paths: Paths, rows: list[Row]) -> None:
    """Rewrite champion_traits.csv. Only `scout review` calls this, after the owner confirms."""
    write_csv(paths.manual_dir / "champion_traits.csv", CHAMPION_TRAITS, rows)


@dataclass(frozen=True)
class TrackRecord:
    """How often one call (say "bot lane_winner=us") came true in the backtest (M20)."""

    graded: int
    hits: int
    usual: float  # how often the most common result happened in those same games


@dataclass(frozen=True)
class Knowledge:
    """Everything the analysis needs about champions, loaded once per report."""

    version: str
    champions: Mapping[str, ChampFacts]  # by Data Dragon id; traits = the any-role row
    traits: Mapping[tuple[str, str], Traits]  # (champ_id, role) -> row, "" = any role
    abilities: Mapping[str, tuple[Row, ...]] = field(default_factory=dict)  # abilities.csv rows
    item_names: frozenset[str] = frozenset()
    briefs: Mapping[tuple[str, str, str], "Brief"] = field(default_factory=dict)  # (role, me, opp)
    tips: Mapping[tuple[str, str], tuple[str, ...]] = field(default_factory=dict)  # Riot's,
    # by (champ_id, "ally" | "enemy"), in Riot's order
    game_facts: tuple[Row, ...] = ()  # data/manual/game_facts.csv: cited timers, role quests
    class_definitions: Mapping[str, Row] = field(default_factory=dict)  # class -> Riot's words
    # M20: each call's record in past games, from data/history/backtest.csv (`scout backtest`)
    track: Mapping[str, TrackRecord] = field(default_factory=dict)

    def facts_about(self, topic: str, role: str = "") -> list[Row]:
        """Game facts on a topic (objective, camps, role_quest), for everyone or one role."""
        return [f for f in self.game_facts
                if f.get("topic") == topic and f.get("role", "") in ("", role)]  # fmt: skip

    def facts(self, champ_id: str) -> ChampFacts:
        """Facts for a champion; an unknown one gets an empty placeholder with a warning."""
        found = self.champions.get(champ_id)
        if found is not None:
            return found
        return ChampFacts(champ_id=champ_id, name=champ_id, key=0,
                          warnings=(f"{champ_id} isn't in the static data",))  # fmt: skip


def build_knowledge(
    version: str,
    tables: Mapping[str, list[Row]],
    traits_rows: list[Row],
    context: TraitContext | None = None,
) -> Knowledge:
    """Merge static tables and champion_traits.csv. Raises ValueError on invalid traits."""
    problems = validate_traits(traits_rows, context or TraitContext())
    if problems:
        raise ValueError("champion_traits.csv has problems:\n" + "\n".join(problems))
    drafted = {(r["champ_id"], r["role"]): parse_traits(r) for r in traits_rows}
    meta = {r["champ_id"]: r for r in tables.get("champion_meta.csv", [])}
    abilities: dict[str, list[Row]] = {}
    for row in tables.get("abilities.csv", []):
        abilities.setdefault(row["champ_id"], []).append(row)
    mechanics = {c: frozenset(x for x in (m.get("mechanics") or "").split("|") if x)
                 for c, m in meta.items()}  # fmt: skip
    ratings = {c: _ratings(m) for c, m in meta.items()}
    # Sourced values over drafted ones, per field (scout/data/sourced.py); every champion with
    # a source gets a row, drafted or not.
    traits: dict[tuple[str, str], Traits] = {}
    for row in tables.get("champions.csv", []):
        champ_id = row["champ_id"]
        texts = [a["description"] for a in abilities.get(champ_id, [])]
        roles = {role for (c, role) in drafted if c == champ_id} | {""}
        for role in roles:
            found = sourced.apply(drafted.get((champ_id, role)),
                                  mechanics.get(champ_id, frozenset()),
                                  ratings.get(champ_id, {}), texts)  # fmt: skip
            if found is not None:
                traits[(champ_id, role)] = found
    champions: dict[str, ChampFacts] = {}
    for row in tables.get("champions.csv", []):
        champ_id = row["champ_id"]
        m = meta.get(champ_id, {})
        warnings = [] if (champ_id, "") in drafted else [f"{row['name']} has no traits row"]
        champions[champ_id] = ChampFacts(
            champ_id=champ_id,
            name=row["name"],
            key=int(row["key"]),
            range_type=m.get("range_type") or None,
            attack_range=_float(m.get("attack_range")),
            move_speed=_float(m.get("move_speed")),
            damage_type=m.get("damage_type") or None,
            classes=frozenset(c for c in (m.get("classes") or "").split("|") if c),
            traits=traits.get((champ_id, "")),
            mechanics=mechanics.get(champ_id, frozenset()),
            ratings=tuple(sorted(ratings.get(champ_id, {}).items())),
            warnings=tuple(warnings),
        )
    return Knowledge(
        version=version,
        champions=champions,
        traits=traits,
        abilities={k: tuple(v) for k, v in abilities.items()},
        item_names=frozenset(r["name"] for r in tables.get("items.csv", [])),
        tips=_tips(tables.get("tips.csv", [])),
    )


def _ratings(meta: Row) -> dict[str, int]:
    """Riot's playstyle ratings from champion_meta.csv: {"cc": 3, "mobility": 1, ...}."""
    found = {}
    for name in ("damage", "durability", "cc", "mobility", "utility"):
        value = meta.get(f"rating_{name}") or ""
        if value.isdigit():
            found[name] = int(value)
    return found


def _float(value: str | None) -> float | None:
    try:
        return float(value) if value else None
    except ValueError:
        return None


def _tips(rows: Iterable[Row]) -> dict[tuple[str, str], tuple[str, ...]]:
    found: dict[tuple[str, str], list[tuple[int, str]]] = {}
    for r in rows:
        found.setdefault((r["champ_id"], r["kind"]), []).append((int(r["n"] or 0), r["text"]))
    return {k: tuple(text for _, text in sorted(v)) for k, v in found.items()}


def load_knowledge(paths: Paths, version: str) -> Knowledge:
    """Champion knowledge for reports. Traits get the structural checks only (scales, tags,
    spikes, columns): a patch that rewords ability text must not stop reports. The content
    checks (numbers, item names) run when rows are written, in draft-traits and review."""
    from scout.data.briefs import parse_briefs  # briefs.py imports this module
    from scout.postgame.backtest import load_track  # it imports this module too

    tables = load_static(paths, version)
    knowledge = build_knowledge(version, tables, read_csv(paths.manual_dir / "champion_traits.csv"))
    briefs = parse_briefs(read_csv(paths.manual_dir / "matchup_briefs.csv"))
    facts = tuple(r for r in read_csv(paths.manual_dir / "game_facts.csv") if r.get("text"))
    classes = {r["class"].strip().lower().replace(" ", "_"): r
               for r in read_csv(paths.manual_dir / "class_definitions.csv") if r.get("quote")}
    return dataclasses.replace(knowledge, briefs=briefs, game_facts=facts,
                               class_definitions=classes,
                               track=load_track(paths.history_dir / "backtest.csv"))  # fmt: skip
