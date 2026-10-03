"""Build the static tables for one Data Dragon version from the parsed sources.

Pure functions, no network or disk: `scout/data/refresh.py` fetches and writes. Merge rules,
cross-checks and review reasons: docs/DATA.md (The refresh pipeline, Static file schemas).
"""

import hashlib
from dataclasses import dataclass, field
from datetime import datetime

from scout.data import review
from scout.data.cdragon import CdChampion
from scout.data.ddragon import DdChampion
from scout.data.opgg import opgg_name
from scout.data.patch import display_patch, short_patch
from scout.data.schemas import CHAMPION_META, STATIC_FILES
from scout.data.store import Row
from scout.data.wiki import WikiChampion

RATING_COLUMNS = ("damage", "durability", "cc", "mobility", "utility")
# Fields an override may set (champion_overrides.csv); identity columns can't be overridden.
OVERRIDABLE = tuple(
    c for c in CHAMPION_META if c not in ("champ_id", "field_sources", "ddragon_version")
)


@dataclass
class StaticBuild:
    version: str
    tables: dict[str, list[Row]]  # file name -> rows, columns per scout/data/schemas.py
    warnings: list[str] = field(default_factory=list)
    disagreements: list[dict[str, str]] = field(default_factory=list)  # champ_id, field, details
    missing: dict[str, list[str]] = field(default_factory=dict)  # source -> champ ids


def build(
    version: str,
    champions: dict[str, DdChampion],
    summoner_spells: list[tuple[int, str, str]],
    items: list[tuple[int, str, int, int, bool]],
    cdragon: dict[str, CdChampion],
    wiki: dict[str, WikiChampion],
    overrides: list[Row],
    mechanics: dict[str, tuple[str, ...]] | None = None,
) -> StaticBuild:
    result = StaticBuild(version=version, tables={})
    ordered = sorted(champions.values(), key=lambda c: c.champ_id)
    result.tables["champions.csv"] = [
        {"champ_id": c.champ_id, "key": str(c.key), "name": c.name, "ddragon_version": version}
        for c in ordered
    ]
    result.tables["abilities.csv"] = [
        _ability_row(c.champ_id, ability, version) for c in ordered for ability in c.abilities
    ]
    result.tables["champion_meta.csv"] = [
        _meta_row(c, cdragon.get(c.champ_id), wiki.get(c.champ_id), version, result,
                  (mechanics or {}).get(c.champ_id, ()))  # fmt: skip
        for c in ordered
    ]
    result.tables["summoner_spells.csv"] = [
        {"key": str(key), "spell_id": spell_id, "name": name}
        for key, spell_id, name in summoner_spells
    ]
    result.tables["items.csv"] = [
        {"item_id": str(i), "name": name, "gold_total": str(gold), "depth": str(depth),
         "boots": "y" if boots else "n", "ddragon_version": version}
        for i, name, gold, depth, boots in items
    ]  # fmt: skip
    result.tables["tips.csv"] = [
        {"champ_id": c.champ_id, "kind": kind, "n": str(n), "text": text,
         "ddragon_version": version}
        for c in ordered
        for kind, tips in (("ally", c.ally_tips), ("enemy", c.enemy_tips))
        for n, text in enumerate(tips, 1)
    ]  # fmt: skip
    result.missing = {
        "cdragon": sorted(c for c in champions if c not in cdragon),
        "wiki": sorted(c for c in champions if c not in wiki),
        "wiki_mechanics": sorted(c for c in champions if not (mechanics or {}).get(c)),
    }
    _apply_overrides(result, overrides)
    return result


def _ability_row(champ_id: str, ability, version: str) -> Row:
    cooldowns = "|".join(_number(c) for c in ability.cooldowns)
    digest = hashlib.sha1(f"{ability.description}\n{cooldowns}".encode()).hexdigest()
    return {
        "champ_id": champ_id, "slot": ability.slot, "name": ability.name,
        "max_rank": str(ability.max_rank or ""), "cooldowns": cooldowns,
        "description": ability.description, "description_hash": digest,
        "ddragon_version": version,
    }  # fmt: skip


def _meta_row(
    champ: DdChampion,
    cd: CdChampion | None,
    wk: WikiChampion | None,
    version: str,
    result: StaticBuild,
    mechanics: tuple[str, ...] = (),
) -> Row:
    sources: dict[str, str] = {}

    def pick(column: str, *candidates: tuple[str, object]) -> str:
        for source, value in candidates:
            if value not in (None, "", ()):
                sources[column] = source
                return str(value)
        return ""

    row: Row = {"champ_id": champ.champ_id}
    row["range_type"] = pick(
        "range_type", ("cdragon", cd and cd.range_type), ("wiki", wk and wk.range_type)
    )
    row["attack_range"] = pick("attack_range", ("wiki", wk and _maybe(wk.attack_range)))
    row["move_speed"] = pick("move_speed", ("wiki", wk and _maybe(wk.move_speed)))
    row["damage_type"] = pick(
        "damage_type", ("cdragon", cd and cd.damage_type), ("wiki", wk and wk.adaptive_type)
    )
    row["classes"] = pick("classes", ("wiki", wk and "|".join(wk.classes)))
    row["legacy_tags"] = pick("legacy_tags", ("ddragon", "|".join(t.lower() for t in champ.tags)))
    row["positions"] = pick("positions", ("wiki", wk and "|".join(r.value for r in wk.positions)))
    row["client_positions"] = pick(
        "client_positions", ("wiki", wk and "|".join(r.value for r in wk.client_positions))
    )
    rating_source = "cdragon" if cd and cd.ratings else "wiki"
    ratings = (cd.ratings if cd and cd.ratings else wk.ratings if wk else {}) or {}
    for name in RATING_COLUMNS:
        row[f"rating_{name}"] = pick(f"rating_{name}", (rating_source, ratings.get(name)))
    row["difficulty"] = pick("difficulty", (rating_source, ratings.get("difficulty")))
    row["mechanics"] = pick("mechanics", ("wiki", "|".join(mechanics)))
    row["last_changed_patch"] = pick("last_changed_patch", ("wiki", wk and wk.last_changed_patch))
    row["opgg_name"] = opgg_name(champ.name)  # the champion argument OP.GG's tools take
    row["field_sources"] = _sources_text(sources)
    row["ddragon_version"] = version

    # Cross-checks (docs/DATA.md step 3): log, don't fail.
    if cd and wk:
        if cd.range_type and wk.range_type and cd.range_type != wk.range_type:
            _disagree(
                result,
                champ.champ_id,
                "range_type",
                f"cdragon={cd.range_type}, wiki={wk.range_type}",
            )
        # No damage type check: the wiki's adaptive type isn't a damage type (Leona and Thresh
        # are "physical" there). It's only a fallback when CommunityDragon lacks a champion.
        if wk.key is not None and wk.key != champ.key:
            _disagree(result, champ.champ_id, "key", f"ddragon={champ.key}, wiki={wk.key}")
    if cd and cd.key != champ.key:
        _disagree(result, champ.champ_id, "key", f"ddragon={champ.key}, cdragon={cd.key}")
    if wk and wk.unknown_positions:
        result.warnings.append(
            f"{champ.champ_id}: unknown wiki positions {', '.join(wk.unknown_positions)}"
        )
    return row


def _disagree(result: StaticBuild, champ_id: str, column: str, details: str) -> None:
    result.disagreements.append({"champ_id": champ_id, "field": column, "details": details})


def _sources_text(sources: dict[str, str]) -> str:
    """'range_type:cdragon|classes:wiki|ratings:cdragon' (ratings collapsed when they agree)."""
    rating_keys = [f"rating_{n}" for n in RATING_COLUMNS] + ["difficulty"]
    rating_sources = {sources.pop(k) for k in rating_keys if k in sources}
    parts = [f"{column}:{source}" for column, source in sources.items()]
    if len(rating_sources) == 1:
        parts.append(f"ratings:{rating_sources.pop()}")
    return "|".join(parts)


def _apply_overrides(result: StaticBuild, overrides: list[Row]) -> None:
    """champion_overrides.csv wins over every source; each use is marked in field_sources."""
    meta = {row["champ_id"]: row for row in result.tables["champion_meta.csv"]}
    for override in overrides:
        champ_id, column = override.get("champ_id", ""), override.get("field", "")
        row = meta.get(champ_id)
        if row is None:
            result.warnings.append(f"override for unknown champion {champ_id!r} ignored")
        elif column not in OVERRIDABLE:
            result.warnings.append(f"override field {column!r} for {champ_id} isn't overridable")
        else:
            row[column] = override.get("value", "")
            sources = [
                s for s in row["field_sources"].split("|") if s and not s.startswith(f"{column}:")
            ]
            row["field_sources"] = "|".join([*sources, f"{column}:override"])


def validate(result: StaticBuild) -> list[str]:
    """Problems that make the build unusable. Empty list = OK to publish as PATCH."""
    errors = []
    for name, columns in STATIC_FILES.items():
        rows = result.tables.get(name)
        if rows is None:
            errors.append(f"{name} wasn't built")
            continue
        for row in rows:
            if tuple(row) != columns:
                errors.append(f"{name}: columns {tuple(row)} don't match the schema")
                break
    champions = result.tables.get("champions.csv") or []
    if not champions:
        errors.append("no champions")
    keys = [row["key"] for row in champions]
    duplicates = sorted({k for k in keys if keys.count(k) > 1})
    if duplicates:
        errors.append(f"duplicate champion keys: {', '.join(duplicates)}")
    for row in champions:
        if not (row["champ_id"] and row["key"] and row["name"]):
            errors.append(f"champion row with an empty id, key or name: {row}")
    with_abilities = {row["champ_id"] for row in result.tables.get("abilities.csv") or []}
    no_abilities = sorted(r["champ_id"] for r in champions if r["champ_id"] not in with_abilities)
    if no_abilities:
        errors.append(f"champions without abilities: {', '.join(no_abilities)}")
    if not result.tables.get("summoner_spells.csv"):
        errors.append("no summoner spells")
    return errors


def review_rows(
    result: StaticBuild,
    previous: dict[str, list[Row]],
    traits_champs: set[str],
    now: datetime,
) -> list[Row]:
    """Review queue entries for this build (docs/DATA.md step 4). `previous` may be {}."""
    patch = result.version
    rows: list[Row] = []
    current = {r["champ_id"] for r in result.tables["champions.csv"]}
    before = {r["champ_id"] for r in previous.get("champions.csv", [])}
    if before:
        for champ_id in sorted(current - before):
            rows.append(review.entry(champ_id, "new_champion", "", patch, now))

    old_hashes = {
        (r["champ_id"], r["slot"]): r["description_hash"] for r in previous.get("abilities.csv", [])
    }
    changed: dict[str, list[str]] = {}
    for r in result.tables["abilities.csv"]:
        old = old_hashes.get((r["champ_id"], r["slot"]))
        if old is not None and old != r["description_hash"]:
            changed.setdefault(r["champ_id"], []).append(r["slot"])

    this_patch = short_patch(result.version)
    for meta in result.tables["champion_meta.csv"]:
        champ_id = meta["champ_id"]
        has_traits = champ_id in traits_champs
        if has_traits and champ_id in changed:
            rows.append(
                review.entry(
                    champ_id,
                    "abilities_changed",
                    "slots " + "|".join(changed[champ_id]),
                    patch,
                    now,
                )
            )
        if has_traits and meta["last_changed_patch"] == this_patch:
            rows.append(
                review.entry(
                    champ_id,
                    "patch_changed",
                    f"wiki: changed in patch {display_patch(this_patch)}",
                    patch,
                    now,
                )
            )
        if not has_traits:
            rows.append(review.entry(champ_id, "traits_missing", "", patch, now))
        if not meta["classes"]:
            rows.append(review.entry(champ_id, "class_missing", "not in the wiki", patch, now))
    for d in result.disagreements:
        details = f"{d['field']}: {d['details']}"
        rows.append(review.entry(d["champ_id"], "source_disagreement", details, patch, now))
    return rows


def _maybe(value: float | None) -> str | None:
    return _number(value) if value is not None else None


def _number(value: float) -> str:
    return str(int(value)) if float(value).is_integer() else f"{value:g}"
