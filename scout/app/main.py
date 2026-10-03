"""Sidekick.exe (M14, M24): the app, with no command line.

The installed app (`Sidekick.exe`, packaging/) and a developer copy's `sidekick` launcher
(pip's no-console launcher from pyproject's gui-scripts) open the window and do what
`scout watch` does, plus what used to need a terminal:

- first run: makes config.yaml, .env and pool.yaml, downloads the champion data;
- Champions: your champions per lane with a 1-5 comfort rating, one list per account (M22);
- History: past games on this PC, each with its dashboard (M23);
- Settings: your account and region (from the client), the AI writer, the Riot and Anthropic
  keys (tested before they're saved), the match data collector, research, Refresh data;
- background: the data refresh every 6 hours, Riot's match data, the update check;
- Update: the newest release (installed) or git (a developer copy), then a restart
  (scout/app/update.py).

`scout watch` opens the same app (and also prints to the terminal). Messages go to
reports/debug/app.log. Changes that need a fresh start (new data, a new region) wait until
you're not in a game.
"""

import contextlib
import ctypes
import os
import shutil
import subprocess
import sys
import threading
import time
import traceback
from collections.abc import Callable
from dataclasses import asdict
from datetime import date, datetime
from pathlib import Path
from typing import Any

from scout import research_import
from scout.accounts import (
    RECENT_MIN,
    Account,
    Accounts,
    logged_in,
    mastery_ideas,
    platform_of,
    recent_counts,
    recent_games,
    recent_ideas,
)
from scout.analysis.measured import changes, coverage, cross_check
from scout.app import shortcut
from scout.app.portraits import Portraits, http_get
from scout.app.session import Echo, Session, SetupError, build_session, make_writer
from scout.app.update import (
    Status,
    UpdateError,
    check_release,
    download_release,
    hand_off,
    http_client,
    install_release,
    latest_release,
    marker_file,
    pull,
    read_marker,
    refreshed_file,
    release_marker,
    scout_command,
    updates_dir,
    version_key,
    write_marker,
)
from scout.app.update import check as check_git
from scout.app.update import git as run_git
from scout.config import Config, ConfigError, load_config, with_env_value, with_value
from scout.data.collector import COLLECTOR_LIMITS, Collector
from scout.data.measure import finished_items
from scout.data.opgg import REGION_OF_PLATFORM
from scout.data.patch import display_patch, previous_patch, short_patch
from scout.data.riot import RiotApi, RiotError
from scout.data.stats_db import StatsDb
from scout.data.store import current_version, load_static
from scout.lcu.client import CHAMPION_MASTERY, CURRENT_SUMMONER, RECENT_GAMES, LcuError
from scout.lcu.watcher import run as watch_until_stopped
from scout.model.roles import Role
from scout.paths import Paths, frozen
from scout.picks import parse_mastery
from scout.pool import HIGHEST, LOWEST, Pool, PoolError, load_pool, save_pool
from scout.report import past
from scout.report.view import status_view
from scout.report.writer import usage_today
from scout.research import regenerate as regenerate_prompts
from scout.version import current_build

# Riot API routing per region (Riot's developer docs: platform and regional routing values).
REGIONS: dict[str, tuple[str, str]] = {
    "NA": ("na1", "americas"), "BR": ("br1", "americas"), "LAN": ("la1", "americas"),
    "LAS": ("la2", "americas"), "EUW": ("euw1", "europe"), "EUNE": ("eun1", "europe"),
    "TR": ("tr1", "europe"), "RU": ("ru", "europe"), "ME": ("me1", "europe"),
    "KR": ("kr", "asia"), "JP": ("jp1", "asia"),
}  # fmt: skip
LOG_LIMIT = 2_000_000  # bytes; the log starts over past this
COLLECT_EVERY_S = 30.0  # how often the background collector checks whether it may run
UPDATE_FIRST_S = 20.0  # the first check for a new version, after the app starts
UPDATE_EVERY_S = 6 * 3600.0  # then every 6 hours
DUE_EVERY_S = 60.0  # how often "research due" is worked out again
REFRESH_EVERY_S = 6 * 3600.0  # the app refreshes the data by itself when it's this old
REFRESH_CHECK_S = 300.0  # how often it looks whether a refresh is due
COLLECT_BATCH = 20  # games per run (it stops early when a game starts)
MUTEX = "Local\\SidekickScoutApp"  # the installer waits on it too (packaging/sidekick.iss)
NO_RESEARCH = "Research runs on the developer copy; its results come with updates."


class Log:
    """Every message to reports/debug/app.log (and the terminal, under `scout watch`)."""

    def __init__(self, path: Path, also: Echo | None = None) -> None:
        self.path, self.also = path, also
        self._lock = threading.Lock()

    def __call__(self, message: str) -> None:
        if self.also is not None:
            self.also(message)
        with self._lock, contextlib.suppress(OSError):
            self.path.parent.mkdir(parents=True, exist_ok=True)
            if self.path.exists() and self.path.stat().st_size > LOG_LIMIT:
                self.path.replace(self.path.with_suffix(".old.log"))
            stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            with self.path.open("a", encoding="utf-8") as f:
                f.write(f"{stamp} {message}\n")


def first_run(paths: Paths) -> list[str]:
    """config.yaml and .env from the examples, and an empty pool.yaml, when missing."""
    paths.user.mkdir(parents=True, exist_ok=True)
    made = []
    if not paths.config_file.exists() and paths.config_example.exists():
        shutil.copy(paths.config_example, paths.config_file)
        made.append("config.yaml")
        if not paths.pool_file.exists():  # not the example's champions: start empty
            save_pool(paths.pool_file, {})
            made.append("pool.yaml")
    if not paths.env_file.exists() and paths.env_example.exists():
        shutil.copy(paths.env_example, paths.env_file)
        made.append(".env")
    return made


def anthropic_key_problem(key: str) -> str | None:
    """None if Anthropic accepts the key (listing models is free), else why not."""
    import anthropic

    try:
        anthropic.Anthropic(api_key=key, timeout=20, max_retries=1).models.list(limit=1)
    except anthropic.AuthenticationError:
        return "Anthropic didn't accept that key."
    except anthropic.APIConnectionError:
        return "Couldn't reach Anthropic (no internet?)."
    except anthropic.APIError as exc:
        return f"Anthropic answered with an error: {exc}"
    return None


class App:
    """The running app: the session, the window's bridge, and what Settings can do."""

    def __init__(self, paths: Paths, *, echo: Echo | None = None, record: bool = True,
                 llm: bool = True, stats_online: bool = True) -> None:  # fmt: skip
        self.paths = paths
        self.log = Log(paths.reports_dir() / "debug" / "app.log", echo)
        self.options = {"record": record, "llm": llm, "stats_online": stats_online}
        self.bridge: Any = None
        self.session: Session | None = None
        self.portraits: Portraits | None = None
        self.job = ""  # what's running (Refresh, Update), for the page
        self.notice = ""  # a message the page shows until dismissed
        self._job_lock = threading.Lock()
        self._halt = threading.Event()  # stops the current session
        self._reload = False  # rebuild the session when idle
        self._names: tuple[str, dict[str, str]] = ("", {})
        self.accounts = Accounts(paths.pools_dir)  # each account's champions (M22)
        self.account: Account | None = None  # logged in, when the client was last asked
        self.region_seen: str | None = None  # the region the client's games are on (REGIONS)
        self._region_for = ""  # the account whose region was last checked
        self.update_available: dict[str, Any] | None = None  # from the background check
        self.installed = frozen()  # the installed app (updates from releases), not the repo
        self.build = current_build(paths)
        self.can_research = not self.installed  # research runs on a developer copy (the repo)
        self._due: dict[str, Any] = {}
        self._due_at = 0.0

    # ------------------------------------------------------------ messages and screens

    def echo(self, message: str) -> None:
        self.log(message)
        one_line = message and "\n" not in message and not message.startswith("=")
        if self.bridge is not None and one_line and len(message) < 160:
            self.bridge.status(message)

    def show(self, view: dict[str, Any]) -> None:
        if self.bridge is not None:
            self.bridge.show(view)

    def problem(self, title: str, message: str) -> None:
        self.log(f"{title}: {message}")
        self.show(status_view("problem", message, title=title))

    def meta(self) -> dict[str, Any]:
        """For the page's top bar (asked a few times a second: everything here is cached)."""
        return {"job": self.job, "notice": self.notice, "update": self.update_available,
                "research": self.research_due()}  # fmt: skip

    def research_due(self) -> dict[str, Any]:
        """Prompts in research/ to run for the current patch (M21), worked out once a minute.
        `remind`: whether the top bar shows it (Settings; only whoever runs the research)."""
        if not self.can_research:
            return {}
        now = time.monotonic()
        if now - self._due_at > DUE_EVERY_S:
            self._due_at = now
            version = current_version(self.paths)
            try:
                remind = self._config().report.research_reminders
            except ConfigError:
                remind = False
            if version:
                patch = short_patch(version)
                self._due = {"patch": display_patch(version), "remind": remind,
                             "prompts": research_import.due(self.paths, patch),
                             "updates": research_import.new_updates(self.paths, patch)}  # fmt: skip
        return self._due

    def _update_loop(self, stop: threading.Event) -> None:
        """Checks GitHub for a new version by itself (M21): at start, then every 6 hours, never
        during champ select or a game."""
        wait = UPDATE_FIRST_S
        while not stop.wait(wait):
            session = self.session
            if session is not None and not session.watcher.idle():
                wait = REFRESH_CHECK_S  # not in champ select or a game: look again a bit later
                continue
            wait = UPDATE_EVERY_S
            status = self._check_status()
            if status.available:
                self.update_available = self._offer(status)
                self.log(f"Update available: {status.version or status.behind}.")
            else:
                self.update_available = None

    def reload_when_idle(self) -> None:
        self._reload = True

    # ------------------------------------------------------------ the background thread

    def start(self, bridge: Any, stop: threading.Event) -> None:
        self.bridge = bridge
        threading.Thread(target=self._supervise, args=(stop,), daemon=True).start()
        threading.Thread(target=self._collect_loop, args=(stop,), name="sidekick-collect",
                         daemon=True).start()  # fmt: skip
        threading.Thread(target=self._update_loop, args=(stop,), name="sidekick-update",
                         daemon=True).start()  # fmt: skip
        threading.Thread(target=self._refresh_loop, args=(stop,), name="sidekick-refresh",
                         daemon=True).start()  # fmt: skip
        try:
            self._run(stop)
        except Exception:
            self.log(traceback.format_exc())
            self.problem("Sidekick hit a problem it can't recover from",
                         f"Details are in {self.log.path}. Closing and reopening usually helps.")

    def _collect_loop(self, stop: threading.Event) -> None:
        """M19: measure Riot's match data in the background, only while you're not in a game
        (it stops at champ select), with its own share of the key's rate limit."""
        while not stop.wait(COLLECT_EVERY_S):
            session = self.session
            if (session is None or session.riot is None or session.watcher.riot is None
                    or not session.watcher.idle() or self.job):  # fmt: skip
                continue
            try:
                config = self._config()
            except ConfigError:
                continue
            if not config.stats.collect or not config.secrets.riot_api_key:
                continue
            tables = load_static(self.paths, session.version)
            riot = RiotApi(config.secrets.riot_api_key, config.player.platform,
                           config.player.regional_route, max_wait_s=130,
                           limits=COLLECTOR_LIMITS)  # fmt: skip
            patch = short_patch(session.version)
            collector = Collector(riot, session.stats.db,
                                  {int(r["key"]): r["champ_id"] for r in tables["champions.csv"]},
                                  finished_items(tables["items.csv"]),
                                  (patch, previous_patch(patch)))  # fmt: skip

            def busy(s: Session = session) -> bool:
                return stop.is_set() or self.session is not s or not s.watcher.idle()

            try:
                summary = collector.run(COLLECT_BATCH, stop=busy)
            finally:
                riot.close()
            if summary.added:
                self.log(f"Match data: {summary.line()}")
            if summary.error and "rate limit" not in summary.error:
                self.log(f"Match data stopped: {summary.error}")

    def _refresh_loop(self, stop: threading.Event) -> None:
        """Refreshes the data by itself (a new patch's champion data, OP.GG's stats, the
        backtest): once it's 6 hours old, only while you're not in champ select or a game."""
        while not stop.wait(REFRESH_CHECK_S):
            session = self.session
            idle = session is not None and session.watcher.idle()
            if self.refresh_due(idle, time.time()):
                self._start_job("Refreshing data", lambda: self._refresh_work(auto=True))

    def refresh_due(self, idle: bool, now: float) -> bool:
        """True when nothing's running, you're not in a game, and the last refresh is old."""
        stamp = refreshed_file(self.paths)
        last = stamp.stat().st_mtime if stamp.exists() else 0.0
        return idle and not self.job and now - last >= REFRESH_EVERY_S

    def _supervise(self, stop: threading.Event) -> None:
        """Ends the session when the window closes, or for a reload once nothing's running."""
        while not stop.wait(1.0):
            session = self.session
            if self._reload and (session is None or session.watcher.idle()):
                self._halt.set()
        self._halt.set()

    def _run(self, stop: threading.Event) -> None:
        made = first_run(self.paths)
        if made:
            self.echo("First start: made " + ", ".join(made) + " (Settings changes them).")
        marker = read_marker(marker_file(self.paths))
        if marker is not None:
            self._finish_update(marker)
        while not stop.is_set():
            self._reload = False
            self._halt.clear()
            session = self._open()
            if session is None:
                self._halt.wait()
                continue
            self.session = session
            try:
                self._watch(session)
            finally:
                self.session = None
                session.close()

    def _open(self) -> Session | None:
        try:
            config = load_config(self.paths.config_file, self.paths.env_file)
        except ConfigError as exc:
            self.problem("Settings need a look", str(exc))
            return None
        if current_version(self.paths) is None:
            self.show(status_view("setup", "Downloading champion data (first start, about a "
                                  "minute)...", title="Getting ready"))  # fmt: skip
            with self._job_lock:
                self.job = "Downloading champion data"
                try:
                    ok = self._refresh_process()
                finally:
                    self.job = ""
            if not ok or current_version(self.paths) is None:
                self.problem("Couldn't download the champion data",
                             "Check the internet connection, then press Refresh data in "
                             "Settings.")  # fmt: skip
                return None
        try:
            session = build_session(self.paths, config, echo=self.echo, **self.options)
        except SetupError as exc:
            self.problem("Sidekick can't start yet", str(exc))
            return None
        self.portraits = Portraits(self.paths.cache_dir / "img" / "champion", session.version,
                                   session.watcher.knowledge.champions, http_get())  # fmt: skip
        return session

    def _watch(self, session: Session) -> None:
        watcher = session.watcher

        def state(kind: str, message: str) -> None:
            if kind in ("waiting_client", "waiting_game", "ended"):
                self.show(status_view(kind, message))
            if self.bridge is not None:
                self.bridge.status(message)

        watcher.echo, watcher.on_view, watcher.on_state = self.echo, self.show, state
        watcher.account_pool = self._account_pool
        watcher.account_name = lambda: self.account.riot_id if self.account else ""
        if watcher.recorder is not None:
            watcher.recorder.echo = self.echo
        self.show(status_view("waiting_client", "Looking for the League client..."))
        config = load_config(self.paths.config_file, self.paths.env_file)
        try:
            watch_until_stopped(watcher, config.client.poll_seconds, wait=session.waker.wait,
                                echo=self.echo, error_log=session.errors,
                                stop=self._halt)  # fmt: skip
        except LcuError as exc:
            self.problem("Lost the League client", str(exc))
            self._halt.wait()

    # ------------------------------------------------------------ long jobs

    def _start_job(self, label: str, work: Callable[[], None]) -> dict[str, Any]:
        if not self._job_lock.acquire(blocking=False):
            return {"error": f"Busy: {self.job or 'another job'} is running."}
        self.job = label

        def run() -> None:
            try:
                work()
            except Exception as exc:  # shown to the user, details in the log
                self.log(traceback.format_exc())
                self.notice = f"{label} didn't finish: {exc}"
            finally:
                self.job = ""
                self._job_lock.release()

        threading.Thread(target=run, name=f"sidekick-{label}", daemon=True).start()
        return {"started": True}

    def _refresh_process(self) -> bool:
        """`scout refresh --pool` in a hidden child process, its lines shown as progress. The
        child works out the same folders (scout/paths.py) from the same environment."""
        env = dict(os.environ, PYTHONIOENCODING="utf-8")
        self.paths.user.mkdir(parents=True, exist_ok=True)
        process = subprocess.Popen(
            scout_command("refresh", "--pool"), cwd=self.paths.user,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8",
            errors="replace", env=env, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )  # fmt: skip
        assert process.stdout is not None
        for line in process.stdout:
            if line.strip():
                self.echo(line.rstrip())
        ok = process.wait() == 0
        stamp = refreshed_file(self.paths)  # tried, even if it failed: next try in 6 hours
        stamp.parent.mkdir(parents=True, exist_ok=True)
        stamp.touch()
        return ok

    def _finish_update(self, marker: Any) -> None:
        if self.installed:
            for old in updates_dir(self.paths).glob("SidekickSetup-*"):
                old.unlink(missing_ok=True)  # the installer did its job (or is fetched again)
            if version_key(self.build.version) < version_key(marker.after):
                self.notice = (f"The update to {marker.after} didn't finish; this is still "
                               f"{self.build.version}. Try Update again in Settings.")  # fmt: skip
                marker_file(self.paths).unlink(missing_ok=True)
                return
        if marker.install_ok is False:
            log = self.paths.reports_dir() / "debug" / "update.log"
            log.parent.mkdir(parents=True, exist_ok=True)
            log.write_text(marker.install_log, encoding="utf-8")
        self.show(status_view("setup", "Updated. Refreshing the data for the new version...",
                              title="Finishing the update"))  # fmt: skip
        with self._job_lock:
            self.job = "Refreshing data"
            try:
                self._refresh_process()
            finally:
                self.job = ""
        n = len(marker.commits)
        what = "; ".join(marker.commits[:3]) + (f" (and {n - 3} more)" if n > 3 else "")
        self.notice = f"Updated: {what}" if what else "Updated."
        if marker.install_ok is False:
            self.notice += " Reinstalling failed, see reports/debug/update.log."
        marker_file(self.paths).unlink(missing_ok=True)

    # ------------------------------------------------------------ what the page can ask for

    def action(self, name: str, payload: dict[str, Any]) -> dict[str, Any]:
        handlers: dict[str, Callable[[dict[str, Any]], dict[str, Any]]] = {
            "settings": self._settings, "champions": self._champions,
            "save_pool": self._save_pool, "suggestions": self._suggestions,
            "pool_ideas": self._pool_ideas, "decline": self._decline,
            "save_account": self._save_account,
            "set_llm": self._set_llm, "save_key": self._save_key, "refresh": self._refresh,
            "set_players": self._set_players, "set_collect": self._set_collect,
            "set_research_reminders": self._set_research_reminders,
            "history": self._history, "history_game": self._history_game,
            "research_plan": self._research_plan, "research_apply": self._research_apply,
            "check_update": self._check_update, "update": self._update,
            "shortcut": self._shortcut, "open": self._open_folder, "icons": self._icons,
            "dismiss": self._dismiss,
        }  # fmt: skip
        handler = handlers.get(name)
        if handler is None:
            return {"error": f"Unknown action {name}."}
        try:
            return handler(payload)
        except (ConfigError, PoolError, UpdateError, RiotError, LcuError, OSError,
                ValueError) as exc:  # fmt: skip
            self.log(f"{name} failed: {exc}")
            return {"error": str(exc)}

    def _config(self) -> Config:
        return load_config(self.paths.config_file, self.paths.env_file)

    def champion_names(self) -> dict[str, str]:
        version = current_version(self.paths) or ""
        if self._names[0] != version:
            rows = load_static(self.paths, version).get("champions.csv", []) if version else []
            self._names = (version, {r["champ_id"]: r["name"] for r in rows})
        return self._names[1]

    def _settings(self, _: dict[str, Any]) -> dict[str, Any]:
        account = self._logged_in()  # first: it may set the region from the client
        live = account is not None
        account = account or self.accounts.last()
        try:
            config: Config | None = self._config()
        except ConfigError:
            config = None
        session = self.session
        region = "custom"
        if config is not None:
            route = (config.player.platform, config.player.regional_route)
            region = next((k for k, v in REGIONS.items() if v == route), "custom")
        today = date.today().isoformat()
        debug = self.paths.reports_dir(config.report.save_dir if config else "reports") / "debug"
        calls, cost = usage_today(debug / "llm_usage.csv", today)
        riot_state = "none"
        if config is not None and config.secrets.riot_api_key:
            riot_state = "unknown"
            if session is not None:
                riot_state = "working" if session.watcher.riot is not None else "rejected"
        return {
            "app": {"commit": self._version_text(), "patch": current_version(self.paths) or "",
                    "data_at": self._data_time(), "shortcut": shortcut.exists(),
                    "installed": self.installed, "can_research": self.can_research,
                    "folder": str(self.paths.user),
                    "in_game": session is not None and not session.watcher.idle()},
            "account": {"logged_in": account.riot_id if account else "", "live": live,
                        "region": region, "regions": list(REGIONS),
                        "detected": region == self.region_seen},
            "llm": {"on": bool(config and config.llm.provider != "none"),
                    "provider": config.llm.provider if config else "",
                    "model": config.llm.model if config else "",
                    "has_key": bool(config and config.secrets.anthropic_api_key),
                    "calls_today": calls, "cost_today": round(cost, 3),
                    "cap": config.llm.max_calls_per_day if config else 0},
            "riot": {"has_key": riot_state != "none", "state": riot_state},
            "players": {"on": bool(config and config.report.player_records)},
            "collect": self._collect_status(config),
            "research": self.research_due(),
        }  # fmt: skip

    def _version_text(self) -> str:
        """'2026.10.4.12 (built 2026-10-04)' installed; 'developer copy, abc1234, ...' else."""
        if self.installed:
            built = f" (built {self.build.built})" if self.build.built else ""
            return self.build.version + built
        try:
            commit = run_git(self.paths.root, "log", "-1", "--format=%h, %cd", "--date=short",
                             timeout=10)  # fmt: skip
        except UpdateError:
            commit = ""
        return "developer copy" + (f", {commit}" if commit else "")

    def _data_time(self) -> str:
        try:
            stamp = self.paths.patch_file.stat().st_mtime
        except OSError:
            return ""
        return datetime.fromtimestamp(stamp).strftime("%Y-%m-%d %H:%M")

    # ------------------------------------------------------------ your champions (M22)

    def _starting_pool(self) -> Pool:
        """pool.yaml (or config.yaml's old lists): the offline commands' list, and the one an
        account Sidekick hasn't seen yet starts from."""
        try:
            fallback = self._config().player.champ_pool
        except ConfigError:
            fallback = {}
        return load_pool(self.paths.pool_file, fallback)

    def _logged_in(self) -> Account | None:
        """Who is logged in to the client now (remembered, with a list of their own); None
        when the client is closed."""
        session, account = self.session, None
        if session is not None:
            try:
                account = logged_in(session.client.get(CURRENT_SUMMONER))
            except LcuError:
                account = None
        if account is not None:
            self.accounts.remember(account, self._starting_pool)  # read only for a new one
            if session is not None and self._region_for != account.puuid:
                self._region_for = account.puuid
                self._detect_region(session)
        self.account = account
        return account

    def _detect_region(self, session: Session) -> None:
        """The region, from the client: the server your own recent games were played on (their
        `platformId`). Saved when it differs, so there's nothing to pick; left alone when the
        client can't tell (no games yet) or names a server Sidekick doesn't know."""
        try:
            platform = platform_of(recent_games(session.client.get(RECENT_GAMES)) or [])
        except LcuError:
            self._region_for = ""  # try again next time
            return
        region = next((name for name, (p, _) in REGIONS.items() if p == platform), None)
        self.region_seen = region
        if region is None:
            if platform:
                self.log(f"Region: the client's games are on {platform}, which Sidekick doesn't "
                         "know; pick the region in Settings.")  # fmt: skip
            return
        try:
            player = self._config().player
        except ConfigError:
            return
        if (player.platform, player.regional_route) != REGIONS[region]:
            self._set_region(region)
            self.notice = f"Region set to {region} from the League client."
            self.log(self.notice)

    def _account_pool(self) -> Pool | None:
        """For the watcher, at each champ select: the logged-in account's champions."""
        try:
            account = self._logged_in()
            return self.accounts.load(account) if account is not None else None
        except (PoolError, OSError) as exc:
            self.log(f"Couldn't load this account's champions: {exc}")
            return None

    def _champions(self, _: dict[str, Any]) -> dict[str, Any]:
        """The Champions page: whose list (logged in now, else the account seen last), the
        list, and every champion for the search."""
        account, live = self._logged_in(), True
        if account is None:
            account, live = self.accounts.last(), False
        pool = self.accounts.load(account) if account is not None else self._starting_pool()
        names = self.champion_names()
        who = None
        if account is not None:
            who = {"key": account.puuid, "riot_id": account.riot_id, "live": live}
        return {
            "account": who,
            "pool": {role.value: [{"id": c, "name": names.get(c, c), "stars": s}
                                  for c, s in pool.get(role, {}).items()] for role in Role},
            "champions": sorted(({"id": c, "name": n} for c, n in names.items()),
                                key=lambda c: c["name"]),
        }  # fmt: skip

    def _save_pool(self, payload: dict[str, Any]) -> dict[str, Any]:
        """The page's list, to its account's file (pool.yaml before any account is known)."""
        names = self.champion_names()
        raw = payload.get("pool")
        if not isinstance(raw, dict):
            return {"error": "Nothing to save."}
        pool: Pool = {role: {} for role in Role}
        for role in Role:
            for entry in raw.get(role.value) or []:
                champ, stars = entry.get("id"), entry.get("stars")
                if champ not in names:
                    return {"error": f"{champ} isn't a champion Sidekick knows."}
                if not isinstance(stars, int) or not LOWEST <= stars <= HIGHEST:
                    return {"error": f"{names[champ]}: pick a rating from 1 to 5."}
                pool[role][champ] = stars
        key = str(payload.get("account") or "")
        account = self.accounts.get(key) if key else None
        if key and account is None:
            return {"error": "That account's list isn't there any more: reopen this page."}
        if account is None:
            save_pool(self.paths.pool_file, pool)
        else:
            self.accounts.save(account, pool)
        session, now = self.session, self.account
        in_use = (account.puuid if account else None) == (now.puuid if now else None)
        if session is not None and session.watcher.picker is not None and in_use:
            session.watcher.picker.pool = (self.accounts.load(account) if account is not None
                                           else load_pool(self.paths.pool_file))  # fmt: skip
        self.log(f"Saved the champions of {account.riot_id if account else 'pool.yaml'}.")
        return {"ok": True}

    def _suggestions(self, _: dict[str, Any]) -> dict[str, Any]:
        """Champions from your recent games that aren't in that lane's list (read-only)."""
        session, account = self.session, self._logged_in()
        if session is None or account is None:
            return {"error": "Open the League client to get suggestions from your recent games."}
        try:
            games = recent_games(session.client.get(RECENT_GAMES))
        except LcuError:
            return {"error": "The League client didn't answer. Try again in a moment."}
        if games is None:
            self.log("Recent games: the client's match history isn't shaped as expected.")
            return {"error": "Couldn't read your recent games from the client."}
        watcher = session.watcher
        counts, counted = recent_counts(games, account.puuid, watcher.index.by_key, watcher.rates)
        if games and not counted:
            self.log(f"Recent games: none of {len(games)} counted; a game's fields: "
                     f"{', '.join(sorted(games[0]))}")  # fmt: skip
        ideas = recent_ideas(counts, self.accounts.load(account), self.accounts.declined(account))
        names = self.champion_names()
        return {"account": account.puuid, "games": counted, "minimum": RECENT_MIN,
                "ideas": [{"role": role.value, "id": c, "name": names.get(c, c), "games": n}
                          for role, c, n in ideas]}  # fmt: skip

    def _pool_ideas(self, _: dict[str, Any]) -> dict[str, Any]:
        """Your most-played champions (the client's mastery) that aren't in your list yet,
        each with the lane it's played in most."""
        session, account = self.session, self._logged_in()
        if session is None or account is None:
            return {"error": "Open the League client first: your most-played comes from it."}
        watcher = session.watcher
        try:
            mastery = parse_mastery(session.client.get(CHAMPION_MASTERY), watcher.index.by_key)
        except LcuError:
            return {"error": "Open the League client first: your most-played comes from it."}
        ideas = mastery_ideas(mastery, watcher.rates, self.accounts.load(account),
                              self.accounts.declined(account))  # fmt: skip
        names = self.champion_names()
        return {"account": account.puuid,
                "ideas": [{"role": role.value, "id": c, "name": names.get(c, c), "points": p}
                          for role, c, p in ideas]}  # fmt: skip

    def _decline(self, payload: dict[str, Any]) -> dict[str, Any]:
        """A suggestion turned down: not suggested again for that account and lane."""
        account = self.accounts.get(str(payload.get("account") or ""))
        champ = str(payload.get("id") or "")
        if account is None or champ not in self.champion_names():
            return {"error": "Couldn't save that answer."}
        self.accounts.decline(account, Role(str(payload.get("role"))), champ)
        return {"ok": True}

    def _save_account(self, payload: dict[str, Any]) -> dict[str, Any]:
        """The region by hand, for when the client can't tell. Your name isn't asked for: the
        client says who is logged in (M22)."""
        region = str(payload.get("region", ""))
        if region not in REGIONS:
            return {"error": "Pick your region from the list."}
        self._set_region(region)
        return {"ok": True}

    def _set_region(self, region: str) -> None:
        platform, route = REGIONS[region]
        text = self.paths.config_file.read_text(encoding="utf-8")
        text = with_value(text, "player", "platform", platform)
        text = with_value(text, "player", "regional_route", route)
        self._write_config(text)
        self.reload_when_idle()  # the Riot API calls go to the new server from the next session

    def _write_config(self, text: str) -> None:
        old = self.paths.config_file.read_text(encoding="utf-8")
        self.paths.config_file.write_text(text, encoding="utf-8", newline="\n")
        try:
            self._config()
        except ConfigError:
            self.paths.config_file.write_text(old, encoding="utf-8", newline="\n")
            raise

    def _set_llm(self, payload: dict[str, Any]) -> dict[str, Any]:
        on = bool(payload.get("on"))
        text = self.paths.config_file.read_text(encoding="utf-8")
        self._write_config(with_value(text, "llm", "provider", "anthropic" if on else "none"))
        config = self._config()
        session = self.session
        if session is not None and self.options["llm"]:
            knowledge = session.watcher.knowledge
            session.watcher.writer = make_writer(config, self.paths, knowledge, self.echo)
        if on and not config.secrets.anthropic_api_key:
            return {"ok": True, "warning": "On, but there's no Anthropic key yet: paste one."}
        return {"ok": True}

    def _collect_status(self, config: Config | None) -> dict[str, Any]:
        """Games measured this patch, coverage, and the cross-check with OP.GG."""
        on = bool(config and config.stats.collect)
        session = self.session
        if session is None:  # not connected yet: the count straight from the database
            version = current_version(self.paths)
            games = 0
            if version and self.paths.stats_db.exists():
                db = StatsDb(self.paths.stats_db)
                try:
                    games = db.collected_games(short_patch(version))
                finally:
                    db.close()
            return {"on": on, "games": games, "covered": 0, "wanted": 0, "gap": None,
                    "patch": short_patch(version) if version else ""}  # fmt: skip
        db, patch = session.stats.db, short_patch(session.version)
        table = db.measured(patch)
        covered, wanted, _ = coverage(table, session.stats.role_rates())
        checked = cross_check(table, db.lane_counts(patch))
        gap = (round(sum(abs(o - t) for _, _, o, t, _ in checked) / len(checked) * 100, 1)
               if checked else None)  # fmt: skip
        before = previous_patch(patch)
        moved = [f"{c.champ} {c.role.value}: {c.text()}"
                 for c in changes(table, db.measured(before), before)[:6]]  # fmt: skip
        return {"on": on, "games": db.collected_games(patch), "covered": covered,
                "wanted": wanted, "gap": gap, "patch": patch, "changes": moved}  # fmt: skip

    def _research_plan(self, _: dict[str, Any]) -> dict[str, Any]:
        """What the agents' replies in research/results/ would change (nothing is written)."""
        if not self.can_research:
            return {"error": NO_RESEARCH}
        found = research_import.plan(self.paths, list(self.champion_names()),
                                     datetime.now().astimezone())  # fmt: skip
        return {"lines": found.lines(), "empty": found.empty,
                "files": [r.path.name for r in found.replies]}  # fmt: skip

    def _research_apply(self, _: dict[str, Any]) -> dict[str, Any]:
        """Apply them (the page asked the owner first); re-planned so it's what they just saw."""
        if not self.can_research:
            return {"error": NO_RESEARCH}
        found = research_import.plan(self.paths, list(self.champion_names()),
                                     datetime.now().astimezone())  # fmt: skip
        if found.empty:
            return {"ok": True, "done": ["Nothing to change."]}
        version = current_version(self.paths) or ""
        done = research_import.apply(self.paths, found, short_patch(version) if version else "")
        if self._config().report.research_reminders:
            regenerate_prompts(self.paths)  # the prompts follow what's due now
        self._due_at = 0.0  # recheck what's due
        self.reload_when_idle()  # new game facts and class definitions: next game
        return {"ok": True, "done": done}

    def _reports(self) -> Path:
        try:
            return self.paths.reports_dir(self._config().report.save_dir)
        except ConfigError:
            return self.paths.reports_dir()

    def _history(self, _: dict[str, Any]) -> dict[str, Any]:
        """Past games on this PC, newest first (M23)."""
        games = past.listing(self._reports(), self.paths.history_dir / "postgame.csv")
        now = self.account.riot_id if self.account else ""
        return {"games": games, "account": now,
                "accounts": sorted({g["account"] for g in games if g["account"]})}  # fmt: skip

    def _history_game(self, payload: dict[str, Any]) -> dict[str, Any]:
        found = past.game(self._reports(), self.paths.history_dir / "postgame.csv",
                          str(payload.get("id", "")))  # fmt: skip
        return found if found is not None else {"error": "That game isn't saved here."}

    def _set_research_reminders(self, payload: dict[str, Any]) -> dict[str, Any]:
        on = bool(payload.get("on"))
        text = self.paths.config_file.read_text(encoding="utf-8")
        self._write_config(with_value(text, "report", "research_reminders", on, add=True))
        self._due_at = 0.0
        return {"ok": True}

    def _set_collect(self, payload: dict[str, Any]) -> dict[str, Any]:
        on = bool(payload.get("on"))
        text = self.paths.config_file.read_text(encoding="utf-8")
        self._write_config(with_value(text, "stats", "collect", on, add=True))
        return {"ok": True}

    def _set_players(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Players' records at the loading screen on or off (M16; docs/POLICY.md)."""
        on = bool(payload.get("on"))
        text = self.paths.config_file.read_text(encoding="utf-8")
        self._write_config(with_value(text, "report", "player_records", on, add=True))
        session = self.session
        if session is not None:
            config = self._config()
            session.watcher.opgg_region = (REGION_OF_PLATFORM.get(config.player.platform, "")
                                           if on else "")  # fmt: skip
        return {"ok": True}

    def _save_key(self, payload: dict[str, Any]) -> dict[str, Any]:
        kind, value = payload.get("kind"), str(payload.get("value", "")).strip()
        if kind == "riot":
            if not value.startswith("RGAPI-"):
                return {"error": "Riot keys start with RGAPI-. Copy it again from "
                                 "developer.riotgames.com."}  # fmt: skip
            config = self._config()
            riot = RiotApi(value, config.player.platform, config.player.regional_route)
            try:
                riot.check()
            except RiotError as exc:
                riot.close()
                return {"error": f"Riot didn't accept it ({exc}). Nothing saved."}
            self._write_env("RIOT_API_KEY", value)
            session = self.session
            if session is not None:
                old, session.riot = session.riot, riot
                session.watcher.riot = riot
                if old is not None:
                    old.close()
            else:
                riot.close()
            self.echo("Riot key saved and working.")
            return {"ok": True}
        if kind == "anthropic":
            if not value.startswith("sk-ant-"):
                return {"error": "Anthropic keys start with sk-ant-. Copy it again from "
                                 "console.anthropic.com."}  # fmt: skip
            problem = anthropic_key_problem(value)
            if problem:
                return {"error": problem + " Nothing saved."}
            self._write_env("ANTHROPIC_API_KEY", value)
            config = self._config()
            session = self.session
            if session is not None and self.options["llm"]:
                knowledge = session.watcher.knowledge
                session.watcher.writer = make_writer(config, self.paths, knowledge, self.echo)
            self.echo("Anthropic key saved and working.")
            return {"ok": True}
        return {"error": "Which key?"}

    def _write_env(self, name: str, value: str) -> None:
        env = self.paths.env_file
        text = env.read_text(encoding="utf-8") if env.exists() else ""
        env.write_text(with_env_value(text, name, value), encoding="utf-8", newline="\n")

    def _refresh(self, _: dict[str, Any]) -> dict[str, Any]:
        return self._start_job("Refreshing data", self._refresh_work)

    def _refresh_work(self, auto: bool = False) -> None:
        """`scout refresh --pool`; a new patch's data is used from the next game. The automatic
        refresh only speaks up for a new patch (its problems go to the log)."""
        before = current_version(self.paths)
        ok = self._refresh_process()
        after = current_version(self.paths)
        if after != before:
            self.notice = f"New patch data ({after}): it's used from the next game."
            self._due_at = 0.0  # research may be due for the new patch
            self.reload_when_idle()
        elif not ok:
            if not auto:
                self.notice = "Refresh had problems: see reports/debug/app.log."
            self.log("Refresh had problems (the lines above).")
        elif not auto:
            self.notice = "Data refreshed."

    def _check_status(self) -> Status:
        """A newer release (installed app) or newer commits (a developer copy with git)."""
        if self.installed:
            with http_client() as client:
                return check_release(self.build.version, client)
        if (self.paths.root / ".git").exists():
            return check_git(self.paths.root)
        return Status(error="This copy has no update source (not installed, no git).")

    def _offer(self, status: Status) -> dict[str, Any]:
        return {"behind": status.behind, "commits": status.commits[:5], "version": status.version}

    def _check_update(self, _: dict[str, Any]) -> dict[str, Any]:
        status = self._check_status()
        self.update_available = self._offer(status) if status.available else None
        return {**asdict(status), "available": status.available}

    def _update(self, _: dict[str, Any]) -> dict[str, Any]:
        session = self.session
        if session is not None and not session.watcher.idle():
            return {"error": "Finish this game first: updating restarts Sidekick."}

        def work() -> None:
            self.echo("Downloading the update from GitHub...")
            if self.installed:
                with http_client() as client:
                    release = latest_release(client)
                    if version_key(release.version) <= version_key(self.build.version):
                        self.notice, self.update_available = "Already up to date.", None
                        return
                    installer = download_release(self.paths, release, client)
                write_marker(marker_file(self.paths), release_marker(self.build.version, release))
                self.echo(f"Installing Sidekick {release.version}; it reopens by itself...")
                install_release(installer)
            else:
                marker = pull(self.paths)
                self.echo(f"Got {len(marker.commits)} change(s). Restarting Sidekick...")
                hand_off(self.paths)
            if self.bridge is not None:
                self.bridge.close()

        return self._start_job("Updating", work)

    def _shortcut(self, _: dict[str, Any]) -> dict[str, Any]:
        try:
            made = shortcut.create(self.paths.user)
        except shortcut.ShortcutError as exc:
            return {"error": str(exc)}
        return {"ok": True, "made": [str(p) for p in made]}

    def _open_folder(self, payload: dict[str, Any]) -> dict[str, Any]:
        targets = {"reports": self._reports(), "log": self.log.path.parent,
                   "folder": self.paths.user, "research": self.paths.research_dir}  # fmt: skip
        target = targets.get(str(payload.get("what")))
        if target is None or not hasattr(os, "startfile"):
            return {"error": "Can't open that here."}
        target.mkdir(parents=True, exist_ok=True)
        os.startfile(target)  # noqa: S606 (Explorer, on a folder of ours)
        return {"ok": True}

    def _icons(self, payload: dict[str, Any]) -> dict[str, Any]:
        ids = [str(i) for i in payload.get("ids") or []][:250]
        portraits = self.portraits
        if portraits is None:
            version = current_version(self.paths)
            if not version:
                return {"icons": {}}
            portraits = Portraits(self.paths.cache_dir / "img" / "champion", version,
                                  self.champion_names(), http_get())  # fmt: skip
            self.portraits = portraits
        return {"icons": portraits.many(ids)}

    def _dismiss(self, _: dict[str, Any]) -> dict[str, Any]:
        self.notice = ""
        return {"ok": True}


# ---------------------------------------------------------------- starting the app


def _only_copy() -> object | None:
    """A named lock so a second Sidekick doesn't start; None if one is already open."""
    if sys.platform != "win32":
        return object()
    kernel = ctypes.windll.kernel32
    handle = kernel.CreateMutexW(None, False, MUTEX)
    if kernel.GetLastError() == 183:  # ERROR_ALREADY_EXISTS
        return None
    return handle


def _app_id() -> None:
    """Group the window under Sidekick's own taskbar icon, not Python's."""
    if sys.platform == "win32":
        with contextlib.suppress(Exception):
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("Sidekick.Scout")


def run_app(paths: Paths, *, echo: Echo | None = None, title: str = "Sidekick",
            **options: bool) -> bool:  # fmt: skip
    """Open the app. False if another copy is already open."""
    from scout.app.window import run as run_window

    lock = _only_copy()
    if lock is None:
        return False
    _app_id()
    app = App(paths, echo=echo, **options)
    run_window(app.start, paths.cache_dir / "app.json", title=title, actions=app.action,
               meta=app.meta)  # fmt: skip
    return True


def main() -> None:
    """The `sidekick` launcher (no console window)."""
    paths = Paths.from_env()
    if not run_app(paths) and sys.platform == "win32":
        ctypes.windll.user32.MessageBoxW(None, "Sidekick is already open (check the taskbar).",
                                         "Sidekick", 0x40)  # fmt: skip


if __name__ == "__main__":
    main()
