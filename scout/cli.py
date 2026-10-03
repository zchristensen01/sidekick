"""The `scout` command line. Commands not built yet say which milestone builds them."""

import csv
import dataclasses
import platform
import sys
import threading
from datetime import date, datetime
from pathlib import Path
from typing import Annotated, Any

import typer
import yaml

from scout.accounts import Accounts, merged
from scout.analysis.insights import analyze
from scout.analysis.role_inference import merged_rates, rates_from_wiki_positions
from scout.analysis.stats import Lookup
from scout.app.session import SetupError, build_session, make_writer
from scout.app.session import bands as _bands
from scout.app.session import stats_service as _stats_service
from scout.config import (
    Config,
    ConfigError,
    load_config,
    load_secrets,
    with_env_value,
)
from scout.data.briefs import BriefContext, validate_briefs
from scout.data.briefs import stale as stale_briefs
from scout.data.draft import DraftError, anthropic_ask, example_rows, missing_champions
from scout.data.draft import draft as draft_row
from scout.data.fetch import FetchError, HttpFetcher
from scout.data.opgg import OpggError, name_key
from scout.data.patch import short_patch
from scout.data.refresh import log_entry, refresh_static
from scout.data.refresh import prune as prune_versions
from scout.data.review import add as review_add
from scout.data.review import entry as review_entry
from scout.data.review import open_entries as review_queue_open
from scout.data.review import summarize as review_summary
from scout.data.riot import RiotApi, RiotError
from scout.data.schemas import MANUAL_FILES
from scout.data.stats_db import StatsDb
from scout.data.stats_service import StatsService
from scout.data.store import (
    append_note,
    append_traits,
    current_version,
    load_knowledge,
    load_static,
    read_csv,
    trait_context,
)
from scout.lcu.champselect import ChampionIndex
from scout.lcu.client import CHAMPION_MASTERY, GAMEFLOW_PHASE, LcuClient, LcuError
from scout.lcu.connection import discover
from scout.lcu.events import EventWaker
from scout.lcu.recorder import Recorder
from scout.lcu.recorder import run as record_until_stopped
from scout.lcu.watcher import Watcher
from scout.lcu.watcher import run as watch_until_stopped
from scout.model.gamefile import load_game
from scout.model.roles import Role
from scout.paths import Paths
from scout.picks import Picker, mastery_by_role, parse_mastery
from scout.pool import DEFAULT_STARS, PoolError, champion_lists, load_pool, save_pool
from scout.report.builder import build_input
from scout.report.render import render_text, render_written
from scout.report.select import select as select_report
from scout.report.view import picks_view, report_view, status_view
from scout.report.window import ReportWindow
from scout.report.writer import usage_today
from scout.reviewing import Session as ReviewSession
from scout.reviewing import recent_champions, review_order
from scout.rules.engine import evaluate, load_rules

app = typer.Typer(
    help="Sidekick: a pre-game League of Legends scouting report for the role you're playing.",
    no_args_is_help=True,
    add_completion=False,
)


@app.command()
def doctor() -> None:
    """Check Python, config, keys, data files, and the League client. Never prints secrets."""
    paths = Paths.from_env()
    problems = 0

    def line(status: str, text: str) -> None:
        nonlocal problems
        if status == "!!":
            problems += 1
        typer.echo(f"[{status}] {text}")

    # Python and platform
    version = ".".join(str(v) for v in sys.version_info[:3])
    line("ok" if sys.version_info >= (3, 11) else "!!", f"Python {version} (need 3.11+)")
    system = platform.system()
    if system == "Windows":
        line("ok", "Windows: live commands (watch, record) supported")
    elif "microsoft" in platform.release().lower():
        line("--", "WSL: offline commands only; run watch/record with Windows Python (docs/LCU.md)")
    else:
        line("--", f"{system}: offline commands only; live commands need Windows")

    # Config
    config = None
    try:
        config = load_config(paths.config_file, paths.env_file)
        line("ok", "config.yaml valid")
    except ConfigError as exc:
        line("!!", str(exc))
    try:
        rated = load_pool(paths.pool_file, config.player.champ_pool if config else {})
        count = sum(len(c) for c in rated.values())
        where = ("pool.yaml" if paths.pool_file.exists()
                 else "config.yaml (until the Champions page saves)")  # fmt: skip
        line("ok" if count else "--", f"your champions: {count}, from {where}")
    except PoolError as exc:
        line("!!", str(exc))
    from scout.app.shortcut import launcher

    if platform.system() == "Windows":
        found = launcher()
        line("ok" if found else "--", "sidekick.exe " + ("installed" if found else
             "missing: run tools/dev_setup.ps1"))  # fmt: skip

    # Secrets: presence only
    secrets = config.secrets if config else load_secrets(paths.env_file)
    line(
        "ok" if secrets.anthropic_api_key else "--",
        "ANTHROPIC_API_KEY "
        + ("set" if secrets.anthropic_api_key else "not set (needed for draft-traits and M7)"),
    )
    if not secrets.riot_api_key:
        line("--", "RIOT_API_KEY not set (loading-screen duo check, post-game check)")
    else:
        platform_id = config.player.platform if config else "na1"
        riot = RiotApi(secrets.riot_api_key, platform_id, "")
        try:
            riot.check()
            line("ok", "RIOT_API_KEY set and working")
        except RiotError as exc:
            line("!!", f"RIOT_API_KEY: {exc}")
        finally:
            riot.close()

    # hand-owned data files
    for name, columns in MANUAL_FILES.items():
        path = paths.manual_dir / name
        if not path.exists():
            line("!!", f"data/manual/{name} is missing")
            continue
        with path.open(newline="", encoding="utf-8") as f:
            header = tuple(next(csv.reader(f), []))
        if header == columns:
            line("ok", f"data/manual/{name}")
        else:
            line("!!", f"data/manual/{name} header doesn't match scout/data/schemas.py")

    # Generated data
    version = current_version(paths)
    if version:
        line("ok", f"static data for {version}")
    else:
        line("--", "no static data yet: run `scout refresh`")

    # Stats (OP.GG): how old, which patch
    if paths.stats_db.exists():
        db = StatsDb(paths.stats_db)
        try:
            fetched, patch = db.lane_fetched_at(), db.opgg_patch()
        finally:
            db.close()
        if fetched is None:
            line("--", "no lane stats yet: run `scout refresh --stats`")
        else:
            hours = (datetime.now().astimezone() - fetched).total_seconds() / 3600
            line("ok", f"stats from OP.GG (patch {patch or '?'}), lane stats {hours:.0f} h old")
    else:
        line("--", "no stats yet: run `scout refresh --stats` (or just `scout watch`)")

    # Champion traits coverage (docs/TRAITS.md)
    traits = read_csv(paths.manual_dir / "champion_traits.csv")
    champions = load_static(paths, version).get("champions.csv", []) if version else []
    if champions:
        have = {r["champ_id"] for r in traits}
        missing = [c["champ_id"] for c in champions if c["champ_id"] not in have]
        reviewed = sum(1 for r in traits if r["reviewed"] == "y")
        text = f"traits for {len(champions) - len(missing)}/{len(champions)} champions, "
        text += f"{reviewed} reviewed by you (`scout review`)"
        if missing:
            text += f"; missing: {', '.join(missing[:5])}" + (" ..." if len(missing) > 5 else "")
        line("ok" if not missing else "--", text)

    # Matchup briefs (docs/KNOWLEDGE.md, layer 3)
    brief_rows = read_csv(paths.manual_dir / "matchup_briefs.csv")
    if brief_rows:
        tc = trait_context(paths, version) if version else None
        lane_advantage: dict[tuple[str, str, str], str] = {}
        if config is not None and version:  # a brief must not contradict OP.GG's lane label
            service = _stats_service(paths, config, version, load_static(paths, version),
                                     online=False)  # fmt: skip
            try:
                lane_advantage = service.lane_advantage(
                    [(r["role"], r["champ_id"], r["opp_champ_id"]) for r in brief_rows])
            finally:
                service.close()
        context = BriefContext(tc.champions, tc.ability_numbers, tc.ability_names,
                               tc.item_names, lane_advantage) if tc else BriefContext()  # fmt: skip
        brief_problems = validate_briefs(brief_rows, context)
        reviewed = sum(1 for r in brief_rows if r["reviewed"] == "y")
        text = f"{len(brief_rows)} matchup briefs, {reviewed} reviewed by you"
        if brief_problems:
            line("!!", f"{text}; problems: {'; '.join(brief_problems[:3])}")
        else:
            line("ok", text)

    # LLM writer: provider, today's use against the cap
    if config is not None:
        debug_dir = paths.reports_dir(config.report.save_dir) / "debug"
        calls, cost = usage_today(debug_dir / "llm_usage.csv", date.today().isoformat())
        if config.llm.provider == "none":
            line("--", "LLM writer off (llm.provider: none)")
        else:
            line("ok", f"LLM writer: {config.llm.provider} {config.llm.model}; today {calls} of "
                       f"{config.llm.max_calls_per_day} calls, about ${cost:.2f}")  # fmt: skip

    # Rules file
    try:
        rules = yaml.safe_load(paths.rules_file.read_text(encoding="utf-8"))["rules"]
        ids = [r["id"] for r in rules]
        dupes = sorted({i for i in ids if ids.count(i) > 1})
        if dupes:
            line("!!", f"duplicate rule ids: {', '.join(dupes)}")
        else:
            line("ok", f"{len(ids)} rules in scout/rules/league_rules.yaml")
    except Exception as exc:  # doctor reports problems, it never crashes
        line("!!", f"rules file unreadable: {exc}")

    # League client
    if config is None:
        line("--", "League client check skipped (fix config.yaml first)")
    else:
        line(*_client_check(config.client.lockfile_path))

    typer.echo("All good." if problems == 0 else f"{problems} problem(s) found.")
    raise typer.Exit(code=0 if problems == 0 else 1)


def _client_check(lockfile_path: Path) -> tuple[str, str]:
    """Doctor's status and message for the League client. Read-only: one GET."""
    credentials = discover(lockfile_path)
    if credentials is None:
        return "--", "League client not running (open it to check the connection)"
    client = LcuClient(lambda: credentials)
    try:
        phase = client.get(GAMEFLOW_PHASE)
    except LcuError as exc:
        return "!!", f"League client found (via {credentials.source}) but not reachable: {exc}"
    finally:
        client.close()
    return "ok", f"League client reachable (found via {credentials.source}; phase: {phase})"


def _config_or_exit(paths: Paths) -> Config:
    try:
        return load_config(paths.config_file, paths.env_file)
    except ConfigError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from None


@app.command()
def refresh(
    static: Annotated[bool, typer.Option("--static", help="Only static data.")] = False,
    stats: Annotated[bool, typer.Option("--stats", help="Only stats.")] = False,
    pool: Annotated[
        bool, typer.Option("--pool", help="Also matchup tables for your champ pool.")
    ] = False,
    force: Annotated[
        bool, typer.Option("--force", help="Rebuild even if nothing is stale.")
    ] = False,
    prune: Annotated[bool, typer.Option("--prune", help="Delete old versions' files.")] = False,
) -> None:
    """Update static data and stats, and the review queue (docs/DATA.md)."""
    paths = Paths.from_env()
    started = datetime.now().astimezone()
    failed = False
    if not stats:
        failed = not _refresh_static(paths, force, prune)
        _fetch_portraits(paths)
    if static:
        if failed:
            raise typer.Exit(code=1)
        return
    config = _config_or_exit(paths)
    version, tables = _static_or_exit(paths)
    service = _stats_service(paths, config, version, tables, online=True)
    lines: list[str] = []
    try:
        if stats or force or service.lane_stats_stale():
            try:
                summary = service.refresh_lane_meta()
                typer.echo(f"Stats: {summary}.")
                lines.append(summary)
            except OpggError as exc:
                typer.echo(f"Stats failed, previous data kept: {exc}", err=True)
                lines.append(f"Error: {exc}")
                failed = True
        else:
            hours = config.stats.max_age_hours
            typer.echo(f"Stats: up to date (lane stats are younger than {hours:g} hours; "
                       "--stats forces a refresh).")  # fmt: skip
        stale = _queue_stale_briefs(paths, service, version)
        if stale:
            typer.echo(f"Matchup briefs: {len(stale)} queued for review (brief_stale).")
            lines.append(f"Review queue: +{len(stale)} brief_stale")
        if pool and not failed:
            done = service.refresh_pool(champion_lists(_every_pool(paths, config)))
            if not done:
                typer.echo("Champ pool: empty (the Champions button in the app).")
            for message in done:
                typer.echo(f"Champ pool: {message}")
            lines += done
    finally:
        service.close()
    if lines:
        log_entry(paths, f"{started:%Y-%m-%d %H:%M} stats", lines)
    try:  # M20: each call's track record, from the games collected so far (offline)
        checked = _backtest(paths, config, version, tables)
        if checked is not None:
            typer.echo(f"Backtest: {checked.games:,} stored games checked "
                       "(`scout backtest` shows the results).")  # fmt: skip
    except (ValueError, OSError) as exc:
        typer.echo(f"Backtest skipped: {exc}", err=True)
    if config.report.research_reminders:  # the PC that does the research (the owner's)
        _research_upkeep(paths, version)
    if failed:
        raise typer.Exit(code=1)


def _research_upkeep(paths: Paths, version: str) -> None:
    """Look for mid-patch updates on the wiki's patch page, then rewrite the research prompts
    for what's due now (docs/PATCH_UPDATE.md)."""
    from scout.data import patch_updates
    from scout.research import regenerate

    fetcher = HttpFetcher()
    try:
        found = patch_updates.check(paths, fetcher, version)
        if found.updates:
            typer.echo(f"Patch page updates: {'; '.join(found.updates)}")
    except FetchError as exc:
        typer.echo(f"Couldn't read the wiki's patch page (hotfix check skipped): {exc}", err=True)
    finally:
        fetcher.close()
    written = regenerate(paths)
    if written:
        typer.echo(f"Research prompts rewritten: {', '.join(p.name for p in written)}")


def _fetch_portraits(paths: Paths) -> None:
    """Champion pictures for the app, downloaded once (data/cache/img/champion)."""
    from scout.app.portraits import Portraits, http_get

    version = current_version(paths)
    if not version:
        return
    champions = [r["champ_id"] for r in load_static(paths, version).get("champions.csv", [])]
    folder = paths.cache_dir / "img" / "champion"
    got, failed = Portraits(folder, version, champions, http_get()).fetch_missing()
    if got or failed:
        typer.echo(f"Champion pictures: {got} downloaded" + (f", {failed} failed" if failed else "")
                   + ".")  # fmt: skip


def _pool_or_exit(paths: Paths, config: Config) -> dict[Role, dict[str, int]]:
    try:
        return load_pool(paths.pool_file, config.player.champ_pool)
    except PoolError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from None


def _every_pool(paths: Paths, config: Config) -> dict[Role, dict[str, int]]:
    """pool.yaml and every account's list as one (M22): the nightly matchups cover them all."""
    pool = _pool_or_exit(paths, config)
    try:
        return merged([pool, *Accounts(paths.pools_dir).every_pool()])
    except PoolError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from None


def _queue_stale_briefs(paths: Paths, service: StatsService, version: str) -> list[dict[str, str]]:
    """brief_stale rows: a champion in a brief changed this patch, or OP.GG's lane advantage
    now contradicts it (docs/KNOWLEDGE.md, Keeping them current)."""
    rows = read_csv(paths.manual_dir / "matchup_briefs.csv")
    if not rows:
        return []
    kit_changes = ("abilities_changed", "patch_changed", "patch_notes")
    queue = review_queue_open(paths.review_queue)
    changed = {e["champ_id"]: e["reason"].replace("_", " ")
               for e in queue if e["reason"] in kit_changes}  # fmt: skip
    keys = [(r["role"], r["champ_id"], r["opp_champ_id"]) for r in rows]
    found = stale_briefs(rows, changed, service.lane_advantage(keys))
    now = datetime.now().astimezone()
    return review_add(paths.review_queue, [
        review_entry(c, "brief_stale", d, short_patch(version), now) for c, d in found
    ])  # fmt: skip


def _refresh_static(paths: Paths, force: bool, prune: bool) -> bool:
    """The static part of `scout refresh`. False if it failed."""
    fetcher = HttpFetcher()
    try:
        result = refresh_static(paths, fetcher, force=force)
    except FetchError as exc:
        typer.echo(f"Download failed, previous data kept: {exc}", err=True)
        return False
    finally:
        fetcher.close()
    typer.echo(result.message)
    if result.counts:
        typer.echo(
            "  "
            + ", ".join(f"{n} {name.removesuffix('.csv')}" for name, n in result.counts.items())
        )
    if result.built:
        typer.echo(
            f"  Review queue: +{len(result.review_added)} ({review_summary(result.review_added)})"
        )
    for warning in result.warnings[:10]:
        typer.echo(f"  Warning: {warning}")
    if len(result.warnings) > 10:
        typer.echo(f"  ...and {len(result.warnings) - 10} more in data/generated/REFRESH_LOG.md")
    for error in result.errors:
        typer.echo(f"  Error: {error}", err=True)
    if prune:
        for folder in prune_versions(paths):
            typer.echo(f"  Pruned {folder}")
    return not result.errors


@app.command()
def watch(
    no_record: Annotated[
        bool, typer.Option("--no-record", help="Don't save champ selects to your recordings.")
    ] = False,
    no_window: Annotated[
        bool, typer.Option("--no-window", help="Terminal only, no report window.")
    ] = False,
    no_llm: Annotated[
        bool, typer.Option("--no-llm", help="Rules report only; never call the LLM writer.")
    ] = False,
    no_stats: Annotated[
        bool, typer.Option("--no-stats", help="Don't fetch OP.GG stats (cached ones still show).")
    ] = False,
) -> None:
    """Wait for champion select and show the report when all picks lock (Windows only).

    Opens the Sidekick app (the same as the desktop shortcut) and prints to this terminal."""
    paths = Paths.from_env()
    if platform.system() != "Windows":
        typer.echo("Warning: the League client is usually only reachable from Windows Python.")
    options = {"record": not no_record, "llm": not no_llm, "stats_online": not no_stats}
    if not no_window and _has_webview():
        from scout.app.main import run_app

        typer.echo("Opening Sidekick. Close its window (or press Ctrl+C here) to stop.")
        if not run_app(paths, echo=typer.echo, **options):
            typer.echo("Sidekick is already open (check the taskbar).", err=True)
            raise typer.Exit(code=1)
        return
    config = _config_or_exit(paths)
    try:
        session = build_session(paths, config, echo=typer.echo, **options)
    except SetupError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from None
    typer.echo(f"Watching for champion select (patch data {session.version}). Ctrl+C to stop.")
    typer.echo(f"Reports are saved to {session.reports}" + ("" if no_record else
               "; champ selects are recorded (scrubbed) in your recordings folder."))  # fmt: skip
    try:
        if no_window:
            watch_until_stopped(
                session.watcher, config.client.poll_seconds, wait=session.waker.wait,
                echo=typer.echo, error_log=session.errors,
            )  # fmt: skip
        else:  # no pywebview (not Windows): the old text window
            _watch_with_window(session.watcher, config.client.poll_seconds, session.waker,
                               session.errors, paths)  # fmt: skip
    except LcuError as exc:
        typer.echo(f"Stopped: {exc}", err=True)
        raise typer.Exit(code=1) from None
    finally:
        session.close()


def _has_webview() -> bool:
    import importlib.util

    return importlib.util.find_spec("webview") is not None


def _watch_with_window(
    watcher: Watcher, poll_seconds: float, waker: EventWaker, errors: Path, paths: Paths
) -> None:
    """The watch loop in a background thread; the report window in this (main) thread."""
    window = ReportWindow(paths.cache_dir / "window.json")
    stop = threading.Event()
    failure: list[LcuError] = []

    def echo(message: str) -> None:
        typer.echo(message)
        window.set_status(message)

    watcher.echo, watcher.on_report = echo, window.show_report
    if watcher.recorder is not None:
        watcher.recorder.echo = echo

    def loop() -> None:
        try:
            watch_until_stopped(
                watcher, poll_seconds, wait=waker.wait, echo=echo, error_log=errors, stop=stop
            )
        except LcuError as exc:
            failure.append(exc)
            window.set_status(f"Stopped: {exc}")

    worker = threading.Thread(target=loop, name="scout-watch", daemon=True)
    worker.start()
    typer.echo("The report window is open; close it (or press Ctrl+C here) to stop.")
    try:
        window.run()
    finally:
        stop.set()
        worker.join(timeout=5)
    if failure:
        raise failure[0]


@app.command()
def report(
    file: Annotated[
        Path, typer.Option("--file", help="Game fixture YAML (tests/fixtures/games/).")
    ],
    role: Annotated[Role | None, typer.Option("--role", help="Role to report for.")] = None,
    debug: Annotated[bool, typer.Option("--debug", help="Show the source of every line.")] = False,
    write: Annotated[
        bool, typer.Option("--write", help="Also have the LLM write it (uses your API key).")
    ] = False,
    fetch: Annotated[
        bool, typer.Option("--fetch", help="Fetch missing OP.GG stats first (network, free).")
    ] = False,
) -> None:
    """Offline report for a game fixture (cached stats; rules only unless --write)."""
    paths = Paths.from_env()
    config = _config_or_exit(paths)
    version, tables = _static_or_exit(paths)
    try:
        knowledge = load_knowledge(paths, version)
        game = load_game(file, set(knowledge.champions))
        rules = load_rules(paths.rules_file)
    except (ValueError, OSError) as exc:  # GameFileError, RulesError, invalid traits
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from None
    if role is not None and role is not game.my_role:
        game = dataclasses.replace(game, my_role=role)
    stats = _stats_service(paths, config, version, tables, online=fetch)
    try:
        if fetch:
            stats.prefetch(game)
        game_stats = stats.for_game(game, 60.0 if fetch else 0.0)
    finally:
        stats.close()
    insights = analyze(game, knowledge, game_stats, _bands(config))
    notes = read_csv(paths.notes_file)
    chosen = select_report(insights, evaluate(rules, insights), notes,
                           config.roles.low_confidence_below)  # fmt: skip
    typer.echo(render_text(chosen, debug=debug), nl=False)
    if write:
        writer = make_writer(config, paths, knowledge, typer.echo)
        if writer is None:
            raise typer.Exit(code=1)
        payload = build_input(chosen, insights, knowledge, config.llm.max_words[game.my_role])
        result = writer.write(payload)
        typer.echo("")
        if result.written is None:
            typer.echo(f"No written version: {result.note}.")
            raise typer.Exit(code=1)
        typer.echo(f"WRITTEN ({result.calls} call(s); log: reports/debug/llm_usage.csv)")
        typer.echo(render_written(chosen, result.written, debug=debug), nl=False)


@app.command()
def pool(
    show: Annotated[bool, typer.Option("--show", help="Only show it; change nothing.")] = False,
) -> None:
    """Your champions per role (pool.yaml), with suggestions from your champion mastery.
    The app's Champions page keeps one list per account with 1-5 comfort ratings."""
    paths = Paths.from_env()
    config = _config_or_exit(paths)
    version, tables = _static_or_exit(paths)
    champions = {r["champ_id"]: r["name"] for r in tables["champions.csv"]}
    index = ChampionIndex.from_static(version, tables)
    mastery = _read_mastery(config, index)
    db = StatsDb(paths.stats_db, config.stats.rank_filter)
    try:
        wiki = rates_from_wiki_positions(tables["champion_meta.csv"])
        rates = merged_rates(_role_rates(db), wiki)
    finally:
        db.close()
    suggested = mastery_by_role(mastery, rates)
    if not mastery:
        typer.echo("(No champion mastery from the League client: open it for suggestions.)")
    rated = _pool_or_exit(paths, config)
    current = champion_lists(rated)
    chosen: dict[Role, tuple[str, ...]] = {}
    for role in Role:
        have = list(current.get(role, ()))
        ideas = [c for c in suggested.get(role, []) if c not in have]
        typer.echo(f"{role.value:8s} {_names(have, champions) or '(empty)'}"
                   + (f"   most played: {_names(ideas, champions)}" if ideas else ""))  # fmt: skip
        if show:
            continue
        answer = typer.prompt("  Enter keeps it; + adds the most played; or type champions",
                              default="", show_default=False).strip()  # fmt: skip
        if answer == "+":
            have += ideas
        elif answer:
            picked, unknown = _champion_ids(answer, champions)
            if unknown:
                typer.echo(f"  Not champions: {', '.join(unknown)}; kept the old list.")
            else:
                have = picked
        chosen[role] = tuple(have)
    if show or chosen == {r: tuple(current.get(r, ())) for r in Role}:
        return
    typer.echo("New pool: " + "; ".join(f"{r.value} {_names(list(c), champions) or '-'}"
                                        for r, c in chosen.items()))  # fmt: skip
    if not typer.confirm("Save to pool.yaml?", default=False):
        typer.echo("Nothing saved.")
        return
    new = {r: {c: rated.get(r, {}).get(c, DEFAULT_STARS) for c in chosen.get(r, ())}
           for r in Role}  # fmt: skip
    save_pool(paths.pool_file, new)
    typer.echo("Saved (new champions are rated 3 of 5; the app's Champions page changes that). "
               "`scout watch` uses it from its next start.")  # fmt: skip


def _read_mastery(config: Config, index: ChampionIndex) -> list[tuple[str, int]]:
    """My champion mastery from the client (one read-only GET), or [] if it isn't open."""
    credentials = discover(config.client.lockfile_path)
    if credentials is None:
        return []
    client = LcuClient(lambda: credentials)
    try:
        return parse_mastery(client.get(CHAMPION_MASTERY), index.by_key)
    except LcuError:
        return []
    finally:
        client.close()


def _role_rates(db: StatsDb) -> dict[str, dict[Role, float]]:
    for patch in reversed(db.patches()):
        rates = db.role_rates(patch)
        if rates:
            return rates
    return {}


def _names(champs: list[str], names: dict[str, str]) -> str:
    return ", ".join(names.get(c, c) for c in champs)


def _champion_ids(text: str, names: dict[str, str]) -> tuple[list[str], list[str]]:
    """'Lee Sin, amumu, Elise' -> Data Dragon ids, and what didn't match."""
    by_key = {name_key(n): c for c, n in names.items()} | {name_key(c): c for c in names}
    found, unknown = [], []
    for part in (p.strip() for p in text.split(",")):
        if part and name_key(part) in by_key:
            found.append(by_key[name_key(part)])
        elif part:
            unknown.append(part)
    return found, unknown


@app.command()
def demo(
    role: Annotated[Role, typer.Option("--role", help="Role to show.")] = Role.SUPPORT,
    file: Annotated[
        Path | None, typer.Option("--file", help="Game fixture YAML (default: a real game).")
    ] = None,
) -> None:
    """Open the app window and play a saved game through its screens (no League client)."""
    from scout.app.window import run as run_window

    paths = Paths.from_env()
    config = _config_or_exit(paths)
    version, tables = _static_or_exit(paths)
    knowledge = load_knowledge(paths, version)
    rules = load_rules(paths.rules_file)
    path = file or paths.root / "tests" / "fixtures" / "games" / "bot_shove.yaml"
    game = dataclasses.replace(load_game(path, set(knowledge.champions)), my_role=role)
    stats = _stats_service(paths, config, version, tables, online=False)
    picker = Picker(knowledge=knowledge, pool=_pool_or_exit(paths, config),
                    meta_rows=tables["champion_meta.csv"], role_rates=stats.role_rates(),
                    lookup=lambda: Lookup(stats.db, version, stats.settings, stats.changed),
                    bands=_bands(config))  # fmt: skip
    names = {c: knowledge.facts(c).name for c in knowledge.champions}

    def report_screen() -> dict[str, Any]:  # the demo has no LLM: the rules version
        insights = analyze(game, knowledge, stats.for_game(game), _bands(config))
        chosen = select_report(insights, evaluate(rules, insights),
                               read_csv(paths.notes_file),
                               config.roles.low_confidence_below)  # fmt: skip
        return report_view(chosen, insights, None, "final")

    def start(bridge: Any, stop: threading.Event) -> None:
        steps = [
            (3, status_view("waiting_game", "Demo: a saved game, shown the way a real one goes.")),
        ]
        before_lock = {r: p for r, p in game.ally.items() if r is not role}
        drafting = dataclasses.replace(game, ally=before_lock)
        steps.append((6, picks_view(picker.suggest(drafting), drafting, names)))
        steps.append((4, status_view("picks_locked", "Your report comes at the loading screen, "
                                     "as soon as it shows everyone's summoner spells.")))
        steps.append((4, status_view("writing", "Roles and summoner spells are in. Gathering "
                                     "the players and likely duos, then the AI writes your "
                                     "report.")))
        steps.append((0, report_screen()))
        for seconds, view in steps:
            bridge.show(view)
            bridge.status("Demo mode: the real thing follows your League client.")
            if seconds and stop.wait(seconds):
                return

    try:
        run_window(start, paths.cache_dir / "app.json", title="Sidekick (demo)")
    finally:
        stats.close()


@app.command()
def key() -> None:
    """Paste a new Riot API key into .env (development keys expire every 24 hours)."""
    paths = Paths.from_env()
    config = _config_or_exit(paths)
    typer.echo("Get it at https://developer.riotgames.com (your dashboard, 'Regenerate API Key').")
    new = typer.prompt("Paste the key (it won't show)", hide_input=True).strip()
    if not new.startswith("RGAPI-"):
        typer.echo("That doesn't look like a Riot key (they start with RGAPI-). Nothing saved.")
        raise typer.Exit(code=1)
    riot = RiotApi(new, config.player.platform, config.player.regional_route)
    try:
        riot.check()
    except RiotError as exc:
        typer.echo(f"Riot didn't accept it ({exc}). Nothing saved.")
        raise typer.Exit(code=1) from None
    finally:
        riot.close()
    text = paths.env_file.read_text(encoding="utf-8") if paths.env_file.exists() else ""
    paths.env_file.write_text(with_env_value(text, "RIOT_API_KEY", new), encoding="utf-8",
                              newline="\n")  # fmt: skip
    typer.echo("Saved to .env and it works. Restart `scout watch` to use it.")


@app.command()
def collect(
    games: Annotated[int, typer.Option("--games", help="New games to measure.")] = 100,
    status: Annotated[
        bool, typer.Option("--status", help="Only show coverage and the OP.GG cross-check.")
    ] = False,
) -> None:
    """Measure Emerald+ ranked games from Riot's match data (needs the Riot key)."""
    from scout.analysis.measured import changes, coverage, cross_check
    from scout.data.collector import Collector
    from scout.data.measure import finished_items
    from scout.data.patch import previous_patch, short_patch

    paths = Paths.from_env()
    config = _config_or_exit(paths)
    version, tables = _static_or_exit(paths)
    db = StatsDb(paths.stats_db, config.stats.rank_filter)
    patch = short_patch(version)
    try:
        if not status:
            if not config.secrets.riot_api_key:
                typer.echo("No Riot API key: paste one in the app's Settings.", err=True)
                raise typer.Exit(code=1)
            riot = RiotApi(config.secrets.riot_api_key, config.player.platform,
                           config.player.regional_route, max_wait_s=130)  # fmt: skip
            # (the app isn't running alongside `scout collect`, so it gets the whole limit)
            by_key = {int(r["key"]): r["champ_id"] for r in tables["champions.csv"]}
            previous = previous_patch(patch)
            collector = Collector(riot, db, by_key, finished_items(tables["items.csv"]),
                                  (patch, previous))  # fmt: skip
            typer.echo(f"Measuring up to {games} games from patches {patch} and {previous} "
                       "(about 45 games every 2 minutes; Ctrl+C stops safely)...")  # fmt: skip
            try:
                typer.echo(collector.run(games).line())
            finally:
                riot.close()
        table = db.measured(patch)
        shares = _role_rates(db)
        have, wanted, missing = coverage(table, shares)
        typer.echo(f"Patch {patch}: {db.collected_games(patch)} games counted; {have} of "
                   f"{wanted} champion-roles really played have 50+ games.")  # fmt: skip
        if missing and have:
            typer.echo(f"  Still thin: {', '.join(missing[:12])}"
                       + (f" and {len(missing) - 12} more" if len(missing) > 12 else ""))
        before = previous_patch(patch)
        moved = changes(table, db.measured(before), before)
        if moved:
            typer.echo(f"  Changed since patch {before} (beyond normal variation): {len(moved)}")
            for change in moved[:8]:
                typer.echo(f"    {change.champ} {change.role.value}: {change.text()}")
        checked = cross_check(table, db.lane_counts(patch))
        if checked:
            gap = sum(abs(o - t) for _, _, o, t, _ in checked) / len(checked)
            typer.echo(f"  Cross-check against OP.GG's win rates ({len(checked)} champion-roles): "
                       f"average gap {gap * 100:.1f} points.")  # fmt: skip
            for champ, role, ours, theirs, n in checked[:3]:
                typer.echo(f"    {champ} {role.value}: ours {ours:.1%} over {n} games, "
                           f"OP.GG {theirs:.1%}")  # fmt: skip
    finally:
        db.close()


@app.command("import-research")
def import_research(
    yes: Annotated[bool, typer.Option("--yes", help="Apply without asking.")] = False,
) -> None:
    """Read the agents' replies in research/results/, show what would change, apply on OK."""
    from scout import research_import

    paths = Paths.from_env()
    version, tables = _static_or_exit(paths)
    champions = [r["champ_id"] for r in tables["champions.csv"]]
    plan = research_import.plan(paths, champions, datetime.now().astimezone())
    for line in plan.lines():
        typer.echo(line)
    if plan.empty:
        return
    if not yes and not typer.confirm("Apply these changes?", default=False):
        typer.echo("Nothing changed.")
        return
    from scout.data.patch import short_patch

    for line in research_import.apply(paths, plan, short_patch(version)):
        typer.echo(f"Done: {line}")
    from scout.research import regenerate

    written = regenerate(paths)  # the prompts follow what's due now
    if written:
        typer.echo(f"Research prompts rewritten: {', '.join(p.name for p in written)}")


@app.command()
def research() -> None:
    """Rewrite the prompts in research/ for the current patch and what's due (the app does it
    by itself on the PC with research reminders on)."""
    from scout.research import regenerate

    paths = Paths.from_env()
    version, _ = _static_or_exit(paths)
    written = regenerate(paths)
    typer.echo(f"Rewrote {len(written)} files in research/ (patch data {version})."
               if written else "The research prompts are already up to date.")  # fmt: skip


@app.command()
def shortcut() -> None:
    """Put Sidekick on the Desktop and in the Start menu (Windows)."""
    from scout.app import shortcut as shortcuts

    paths = Paths.from_env()
    try:
        made = shortcuts.create(paths.user)
    except shortcuts.ShortcutError as exc:
        typer.echo(f"No shortcut: {exc}", err=True)
        raise typer.Exit(code=1) from None
    for link in made:
        typer.echo(f"Made {link}")


@app.command()
def review(
    champ: Annotated[
        str | None, typer.Argument(help="Review just this champion (Data Dragon id).")
    ] = None,
) -> None:
    """Walk the review queue: check, edit, or accept champion traits (briefs are fixed by
    hand in data/manual/matchup_briefs.csv)."""
    paths = Paths.from_env()
    config = _config_or_exit(paths)
    version, tables = _static_or_exit(paths)
    rows = read_csv(paths.manual_dir / "champion_traits.csv")
    champ_by_key = {int(r["key"]): r["champ_id"] for r in tables["champions.csv"]}
    recent = recent_champions(paths.recordings_dir, champ_by_key)
    pool = [c for champs in champion_lists(_pool_or_exit(paths, config)).values()
            for c in champs]  # fmt: skip
    items = review_order(rows, review_queue_open(paths.review_queue), recent, pool, champ)
    if not items:
        typer.echo("Nothing to review." if champ is None else f"No traits row for {champ}.")
        return
    typer.echo(f"{len(items)} champion(s) to review. Changes are saved only when you confirm.")
    session = ReviewSession(
        paths=paths,
        version=version,
        tables=tables,
        context=trait_context(paths, version),
        ask=lambda text: typer.prompt(text, default="", show_default=False),
        echo=typer.echo,
        now=lambda: datetime.now().astimezone(),
    )
    saved = session.run(rows, items)
    typer.echo(f"Done: {saved} reviewed this session.")


@app.command("draft-traits")
def draft_traits(
    champ: Annotated[str | None, typer.Argument(help="Data Dragon id, e.g. LeeSin.")] = None,
    all_missing: Annotated[
        bool, typer.Option("--all-missing", help="Every champion without a row.")
    ] = False,
) -> None:
    """Have the LLM draft a traits row (reviewed=n) for you to check."""
    paths = Paths.from_env()
    config = _config_or_exit(paths)
    if (champ is None) == (not all_missing):
        typer.echo(
            "Give one champion (e.g. `scout draft-traits LeeSin`) or --all-missing.", err=True
        )
        raise typer.Exit(code=2)
    key = config.secrets.anthropic_api_key
    if not key:
        typer.echo(
            "ANTHROPIC_API_KEY isn't set in .env. Add it, or ask Claude Code to draft the row "
            "in a session instead (docs/TRAITS.md).",
            err=True,
        )
        raise typer.Exit(code=1)
    version, tables = _static_or_exit(paths)
    rows = read_csv(paths.manual_dir / "champion_traits.csv")
    targets = missing_champions(tables, rows) if all_missing else [champ]
    have = {r["champ_id"] for r in rows if r["role"] == ""}
    targets = [t for t in targets if t not in have]
    if not targets:
        done = f"{champ} already has a traits row; use `scout review {champ}`."
        typer.echo("Every champion already has a traits row." if all_missing else done)
        return
    ask = anthropic_ask(config.llm.model, key)
    context = trait_context(paths, version)
    examples = example_rows(rows)
    failed = 0
    for target in targets:
        try:
            result = draft_row(target, tables, context, paths.traits_doc,
                               examples, ask, version)  # fmt: skip
        except DraftError as exc:
            typer.echo(f"{target}: {exc}", err=True)
            failed += 1
            continue
        append_traits(paths, [result.row])
        typer.echo(f"{target}: drafted (reviewed=n), {result.input_tokens} in / "
                   f"{result.output_tokens} out tokens, attempt {result.attempts}")  # fmt: skip
    if failed:
        raise typer.Exit(code=1)


def _static_or_exit(paths: Paths) -> tuple[str, dict[str, list[dict[str, str]]]]:
    version = current_version(paths)
    tables = load_static(paths, version) if version else {}
    if not version or not tables:
        typer.echo("No static data yet: run `scout refresh` first.", err=True)
        raise typer.Exit(code=1)
    return version, tables


@app.command()
def record(
    all_queues: Annotated[
        bool, typer.Option("--all-queues", help="Also record ARAM, customs and other queues.")
    ] = False,
) -> None:
    """Save scrubbed champion select sessions to your recordings folder (Windows only)."""
    paths = Paths.from_env()
    config = _config_or_exit(paths)
    if platform.system() != "Windows":
        typer.echo("Warning: the League client is usually only reachable from Windows Python.")
    out_dir = paths.recordings_dir
    client = LcuClient(lambda: discover(config.client.lockfile_path))
    recorder = Recorder(client, out_dir, all_queues=all_queues, echo=typer.echo)
    typer.echo(f"Recording champion selects to {out_dir}")
    typer.echo("Leave this running while you play. Ctrl+C to stop.")
    try:
        record_until_stopped(recorder, config.client.poll_seconds, echo=typer.echo)
    except LcuError as exc:
        typer.echo(f"Stopped: {exc}", err=True)
        raise typer.Exit(code=1) from None
    finally:
        client.close()


@app.command()
def postgame(
    file: Annotated[
        Path | None,
        typer.Option("--file", help="A report's claims (reports/<report>.json); default: the "
                     "newest unchecked one."),  # fmt: skip
    ] = None,
    note: Annotated[
        bool, typer.Option("--note/--no-note", help="Offer to add a matchup note after.")
    ] = True,
) -> None:
    """Check a report's predictions against what happened in the game (needs the Riot key)."""
    from scout.postgame import claims as claim_files
    from scout.postgame.check import check, pending, record, summary
    from scout.postgame.grade import MatchError

    paths = Paths.from_env()
    config = _config_or_exit(paths)
    version, _ = _static_or_exit(paths)
    if not config.secrets.riot_api_key:
        typer.echo("No Riot API key: paste one in the app's Settings (or `scout key`).", err=True)
        raise typer.Exit(code=1)
    reports = paths.reports_dir(config.report.save_dir)
    path = file or next(iter(pending(reports)), None)
    if path is None:
        typer.echo("Nothing to check: every saved report has been checked (or none has claims).")
        return
    saved = claim_files.load(path)
    knowledge = load_knowledge(paths, version)
    riot = RiotApi(config.secrets.riot_api_key, config.player.platform,
                   config.player.regional_route)  # fmt: skip
    try:
        results = check(saved, riot, knowledge, config.player.platform)
    except (MatchError, RiotError) as exc:
        typer.echo(f"Not checked: {exc}.", err=True)
        raise typer.Exit(code=1) from None
    finally:
        riot.close()
    record(paths.history_dir, saved, results, datetime.now().astimezone())
    typer.echo(f"{path.stem}")
    for line in summary(results):
        typer.echo(line)
    typer.echo(f"Saved to {paths.history_dir / 'postgame.csv'}; hit rates in rule_accuracy.csv.")
    opp = saved.enemy.get(saved.my_role)
    if note and opp and saved.my_champion:
        names = {c: knowledge.facts(c).name for c in (saved.my_champion, opp)}
        ask = f"A note about {names[saved.my_champion]} vs {names[opp]} for next time?"
        text = typer.prompt(f"{ask} (Enter to skip)", default="", show_default=False).strip()
        if text:
            append_note(paths, {"role": saved.my_role, "champ_id": saved.my_champion,
                                "opp_champ_id": opp, "note": text,
                                "date": date.today().isoformat()})  # fmt: skip
            typer.echo(f"Added to {paths.notes_file} (shown as \"Your notes\").")


@app.command()
def backtest(
    games: Annotated[
        int | None, typer.Option("--games", help="Only the newest N stored games.")
    ] = None,
    fetch: Annotated[
        bool, typer.Option("--fetch", help="First fetch OP.GG's matchup tables the stored "
                           "drafts need (network, free; cached for days).")  # fmt: skip
    ] = False,
) -> None:
    """Grade every read on the games the collector stored (no network): how often each kind of
    read, rule and lane label came true, against always guessing the usual outcome. `scout
    refresh` runs it too; reports then carry each call's record (docs/REPORT_AGENT.md)."""
    from scout.postgame.backtest import summary

    paths = Paths.from_env()
    config = _config_or_exit(paths)
    version, tables = _static_or_exit(paths)
    try:
        tally = _backtest(paths, config, version, tables, games, fetch)
    except (ValueError, OSError) as exc:  # invalid traits or rules
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from None
    if tally is None:
        typer.echo("No stored games yet: the app's match data collector (or `scout collect`) "
                   "stores them as it measures.")  # fmt: skip
        return
    for line in summary(tally):
        typer.echo(line)
    typer.echo(f"Every line: {paths.history_dir / 'backtest.csv'}")


BACKTEST_FETCH_S = 3600.0  # the longest `scout backtest --fetch` waits for OP.GG


def _backtest(paths: Paths, config: Config, version: str, tables: dict[str, list[dict[str, str]]],
              games: int | None = None, fetch: bool = False) -> Any:  # fmt: skip
    """Run the backtest on the stored games and save data/history/backtest.csv; None (and no
    file change) when no games are stored yet. `fetch`: first get the OP.GG matchup tables the
    drafts need, so lane reads are graded as live reports make them (with OP.GG's numbers)."""
    from scout.analysis.stats import game_stats
    from scout.postgame import backtest as bt

    knowledge = load_knowledge(paths, version)
    rules = load_rules(paths.rules_file)
    stats = _stats_service(paths, config, version, tables, online=fetch)
    cache: dict[str, Any] = {}
    try:
        records = stats.db.games(limit=games)
        if not records:
            return None
        if fetch:
            typer.echo(f"Fetching OP.GG's matchup tables for {len(records)} games (fresh ones "
                       "are skipped; the first time can take a while)...")  # fmt: skip
            for record in records:
                for side in ("100", "200"):
                    if set(record.get("sides") or {}) == {"100", "200"}:
                        stats.prefetch(bt.game_from(record, side))
            stats.wait(BACKTEST_FETCH_S)
            errors = stats.take_errors()
            if errors:
                typer.echo(f"  {len(errors)} OP.GG calls failed (last: {errors[-1][:90]}).")
        tally = bt.run(records, knowledge, rules,
                       lambda g: game_stats(stats.db, g, stats.settings, stats.changed,
                                            stats.items, cache=cache),
                       _bands(config))  # fmt: skip
    finally:
        stats.close()
    bt.save(paths.history_dir / "backtest.csv", tally)
    return tally
