"""The `scout refresh` pipeline: version check, static build, diff, validate, stats, log.

Step by step in docs/DATA.md (The refresh pipeline). Never touches data/manual/ (it only reads
champion_traits.csv and champion_overrides.csv). Static data is M2; stats come in M8.
"""

import json
import shutil
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from scout.data import cdragon, ddragon, review, static, wiki
from scout.data.fetch import Fetcher, FetchError, NotFound, write_atomic
from scout.data.patch import display_patch, is_newer, short_patch
from scout.data.schemas import STATIC_FILES
from scout.data.store import (
    current_version,
    load_static,
    read_csv,
    static_complete,
    traits_champ_ids,
    write_csv,
)
from scout.paths import Paths

KEEP_VERSIONS = 3
WIKI_RECHECK = timedelta(days=3)  # the wiki can lag a new patch by a few days
CDRAGON_WORKERS = 6


@dataclass
class StaticResult:
    version: str
    built: bool
    message: str
    counts: dict[str, int] = field(default_factory=dict)
    review_added: list[dict[str, str]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


def refresh_static(
    paths: Paths,
    fetcher: Fetcher,
    *,
    force: bool = False,
    now: Callable[[], datetime] = lambda: datetime.now().astimezone(),
) -> StaticResult:
    """Build static data for the newest Data Dragon version if it isn't built yet."""
    version = ddragon.latest_version(fetcher.json(ddragon.VERSIONS_URL))
    current = current_version(paths)
    if current and is_newer(current, version):
        return StaticResult(version, False, f"Data Dragon is behind ({version} < {current})")
    recheck_wiki = _wiki_recheck_due(paths, version, now())
    if current == version and static_complete(paths, version) and not force and not recheck_wiki:
        return StaticResult(version, False, f"Static data is up to date ({version}).")

    started = now()
    sources, warnings = _download(paths, fetcher, version, refresh_wiki=recheck_wiki or force)
    overrides = read_csv(paths.manual_dir / "champion_overrides.csv")
    built = static.build(version, overrides=overrides, **sources)
    warnings += built.warnings
    if built.missing["cdragon"]:
        warnings.append(f"not in CommunityDragon yet: {', '.join(built.missing['cdragon'])}")
    if built.missing["wiki"]:
        warnings.append(f"not in the wiki yet: {', '.join(built.missing['wiki'])}")
    if built.missing["wiki_mechanics"]:
        warnings.append("no wiki mechanics (categories) yet: "
                        + ", ".join(built.missing["wiki_mechanics"]))  # fmt: skip
    errors = static.validate(built)
    counts = {name: len(rows) for name, rows in built.tables.items()}
    if errors:
        result = StaticResult(
            version,
            False,
            "Static build failed; kept the previous data.",
            counts,
            [],
            warnings,
            errors,
        )
        _log(paths, result, started)
        return result

    previous_version = (
        current if current and current != version else _previous_built(paths, version)
    )
    previous = load_static(paths, previous_version) if previous_version else {}
    folder = paths.static_dir(version)
    for name, columns in STATIC_FILES.items():
        write_csv(folder / name, columns, built.tables[name])
    manifest = _manifest(paths, version, built, warnings, started, recheck_wiki, fetcher)
    write_atomic(folder / "manifest.json", json.dumps(manifest, indent=2) + "\n")
    added = review.add(
        paths.review_queue, static.review_rows(built, previous, traits_champ_ids(paths), started)
    )
    write_atomic(paths.patch_file, version + "\n")
    what = "Re-checked the wiki for" if recheck_wiki and current == version else "Built"
    result = StaticResult(
        version,
        True,
        f"{what} static data {version} (patch {display_patch(version)}).",
        counts,
        added,
        warnings,
    )
    _log(paths, result, started, built.disagreements)
    return result


def _download(
    paths: Paths, fetcher: Fetcher, version: str, *, refresh_wiki: bool
) -> tuple[dict[str, Any], list[str]]:
    warnings: list[str] = []
    cache = paths.cache_dir
    full = fetcher.json(
        ddragon.champion_full_url(version), cache / "ddragon" / version / "championFull.json"
    )
    summoner = fetcher.json(
        ddragon.summoner_url(version), cache / "ddragon" / version / "summoner.json"
    )
    items = fetcher.json(ddragon.item_url(version), cache / "ddragon" / version / "item.json")
    champions = ddragon.parse_champions(full)

    folder = short_patch(version)
    try:
        fetcher.json(
            cdragon.metadata_url(folder), cache / "cdragon" / version / "content-metadata.json"
        )
    except NotFound:
        warnings.append(f"CommunityDragon has no {folder}/ folder yet; used latest/")
        folder = "latest"
        fetcher.json(
            cdragon.metadata_url(folder),
            cache / "cdragon" / version / "content-metadata.json",
            refresh=True,
        )

    def one(champ: ddragon.DdChampion) -> tuple[str, cdragon.CdChampion | None, str]:
        target = cache / "cdragon" / version / "champions" / f"{champ.key}.json"
        try:
            return (
                champ.champ_id,
                cdragon.parse_champion(
                    fetcher.json(cdragon.champion_url(folder, champ.key), target)
                ),
                "",
            )
        except FetchError as exc:
            return champ.champ_id, None, f"CommunityDragon {champ.champ_id}: {exc}"

    cd_champions: dict[str, cdragon.CdChampion] = {}
    with ThreadPoolExecutor(max_workers=CDRAGON_WORKERS) as pool:
        for champ_id, parsed, problem in pool.map(one, champions.values()):
            if parsed is not None:
                cd_champions[champ_id] = parsed
            if problem:
                warnings.append(problem)

    try:
        wiki_text = fetcher.text(
            wiki.URL, cache / "wiki" / version / "ChampionData.lua", refresh=refresh_wiki
        )
        wiki_champions = wiki.parse_module(wiki_text)
    except (FetchError, wiki.LuaParseError) as exc:
        warnings.append(f"wiki unavailable, classes and positions missing: {exc}")
        wiki_champions = {}

    try:
        mechanics = _wiki_mechanics(fetcher, cache / "wiki" / version, champions, refresh_wiki)
    except (FetchError, KeyError, TypeError, AttributeError) as exc:
        warnings.append(f"wiki categories unavailable, mechanics missing: {exc}")
        mechanics = {}

    sources = {
        "champions": champions,
        "summoner_spells": ddragon.parse_summoner_spells(summoner),
        "items": ddragon.parse_items(items),
        "cdragon": cd_champions,
        "wiki": wiki_champions,
        "mechanics": mechanics,
    }
    return sources, warnings


def _wiki_mechanics(
    fetcher: Fetcher, folder: Path, champions: dict[str, ddragon.DdChampion], refresh: bool
) -> dict[str, tuple[str, ...]]:
    """Each champion's mechanic categories from its wiki page (docs/DATA.md, LoL wiki)."""
    raw = fetcher.json(wiki.attributes_url(), folder / "attributes.json", refresh=refresh)
    attributes = wiki.parse_attributes(raw)
    if not attributes:
        raise FetchError("the wiki listed no attribute categories")
    by_title = {c.name: c.champ_id for c in champions.values()}
    titles = sorted(by_title)
    found: dict[str, set[str]] = {}
    for n, start in enumerate(range(0, len(titles), wiki.TITLES_PER_CALL)):
        batch, cont = titles[start : start + wiki.TITLES_PER_CALL], None
        for step in range(20):  # the API's "continue" pages, if a batch has many categories
            url = wiki.categories_url(batch, cont)
            pages, cont = wiki.parse_categories(
                fetcher.json(url, folder / f"categories_{n}_{step}.json", refresh=refresh)
            )
            for title, cats in pages.items():
                found.setdefault(title, set()).update(cats)
            if cont is None:
                break
    return {by_title[t]: wiki.mechanics(c, attributes) for t, c in found.items() if t in by_title}


def _wiki_recheck_due(paths: Paths, version: str, now: datetime) -> bool:
    """True once, 3+ days after a version was first built, to pick up late wiki edits."""
    manifest_path = paths.static_dir(version) / "manifest.json"
    if not manifest_path.exists():
        return False
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    first = datetime.fromisoformat(manifest["first_built_at"])
    return not manifest.get("wiki_rechecked") and now - first >= WIKI_RECHECK


def _manifest(
    paths: Paths,
    version: str,
    built: static.StaticBuild,
    warnings: list[str],
    started: datetime,
    recheck_wiki: bool,
    fetcher: Fetcher,
) -> dict[str, Any]:
    old_path = paths.static_dir(version) / "manifest.json"
    old = json.loads(old_path.read_text(encoding="utf-8")) if old_path.exists() else {}
    downloads = getattr(fetcher, "log", [])
    return {
        "ddragon_version": version,
        "patch": display_patch(version),
        "built_at": started.isoformat(timespec="seconds"),
        "first_built_at": old.get("first_built_at", started.isoformat(timespec="seconds")),
        "wiki_rechecked": bool(old.get("wiki_rechecked") or recheck_wiki),
        "rows": {name: len(rows) for name, rows in built.tables.items()},
        "sources": {
            "ddragon": ddragon.champion_full_url(version),
            "cdragon": cdragon.BASE,
            "wiki": f"{wiki.URL} ({wiki.LICENSE})",
        },
        "downloaded": sum(1 for d in downloads if not d.get("from_cache")),
        "from_cache": sum(1 for d in downloads if d.get("from_cache")),
        "missing": built.missing,
        "disagreements": built.disagreements,
        "warnings": warnings,
    }


def _previous_built(paths: Paths, version: str) -> str | None:
    """The newest built version older than `version` (for the diff), if any."""
    root = paths.generated_dir / "static"
    older = (
        [p.name for p in root.iterdir() if p.is_dir() and p.name != version]
        if root.exists()
        else []
    )
    older = [v for v in older if _is_version(v) and is_newer(version, v)]
    return max(older, key=lambda v: tuple(int(x) for x in v.split("."))) if older else None


def _is_version(name: str) -> bool:
    parts = name.split(".")
    return len(parts) == 3 and all(p.isdigit() for p in parts)


def prune(paths: Paths, keep: int = KEEP_VERSIONS) -> list[Path]:
    """Delete static and cache folders beyond the newest `keep` versions. Returns what went."""
    removed: list[Path] = []
    roots = [paths.generated_dir / "static"]
    if paths.cache_dir.exists():
        roots += [p for p in paths.cache_dir.iterdir() if p.is_dir()]
    for root in roots:
        if not root.exists():
            continue
        versions = sorted(
            (p for p in root.iterdir() if p.is_dir() and _is_version(p.name)),
            key=lambda p: tuple(int(x) for x in p.name.split(".")),
            reverse=True,
        )
        for old in versions[keep:]:
            shutil.rmtree(old)
            removed.append(old)
    return removed


def _log(
    paths: Paths,
    result: StaticResult,
    started: datetime,
    disagreements: list[dict[str, str]] | None = None,
) -> None:
    """Add an entry at the top of data/generated/REFRESH_LOG.md (newest first)."""
    lines = [
        f"## {started:%Y-%m-%d %H:%M} static {result.version} "
        f"(patch {display_patch(result.version)})",
        f"- {result.message}",
    ]
    if result.counts:
        lines.append(
            "- Rows: "
            + ", ".join(f"{n} {k.removesuffix('.csv')}" for k, n in result.counts.items())
        )
    if result.built:
        lines.append(
            f"- Review queue: +{len(result.review_added)} ({review.summarize(result.review_added)})"
        )
    for d in disagreements or []:
        lines.append(f"- Disagreement: {d['champ_id']} {d['field']} ({d['details']})")
    lines += [f"- Warning: {w}" for w in result.warnings]
    lines += [f"- Error: {e}" for e in result.errors]
    _prepend(paths, lines)


def log_entry(paths: Paths, title: str, items: list[str]) -> None:
    """A REFRESH_LOG.md entry for anything else `scout refresh` did (stats, the champ pool)."""
    _prepend(paths, [f"## {title}", *(f"- {item}" for item in items)])


def _prepend(paths: Paths, lines: list[str]) -> None:
    header = "# REFRESH_LOG\n\nWritten by `scout refresh`, newest first. Machine-owned.\n"
    old = paths.refresh_log.read_text(encoding="utf-8") if paths.refresh_log.exists() else header
    body = old[len(header) :] if old.startswith(header) else old
    write_atomic(paths.refresh_log, header + "\n" + "\n".join(lines) + "\n" + body)
