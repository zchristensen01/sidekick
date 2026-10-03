"""Everything a live session needs, built once: used by `scout watch` and by Sidekick.exe.

`build_session` loads the data, the rules, the stats, the writer and the League client
connection, and wires them into a Watcher. Nothing here prints: messages go to `echo`.
"""

import threading
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from scout.analysis.role_inference import merged_rates, rates_from_wiki_positions
from scout.analysis.stats import Lookup, StatsSettings
from scout.config import Config
from scout.counterpick import Bands
from scout.data.opgg import REGION_OF_PLATFORM, McpHttp, Opgg, OpggError
from scout.data.riot import RiotApi, RiotError
from scout.data.stats_db import StatsDb
from scout.data.stats_service import StatsService
from scout.data.store import Knowledge, current_version, load_knowledge, load_static, read_csv
from scout.lcu.champselect import ChampionIndex
from scout.lcu.client import LcuClient
from scout.lcu.connection import discover
from scout.lcu.events import EventWaker
from scout.lcu.recorder import Recorder
from scout.lcu.watcher import Watcher
from scout.llm import anthropic_ask, ollama_ask
from scout.paths import Paths
from scout.picks import Picker
from scout.pool import load_pool
from scout.report.writer import SCHEMA as WRITER_SCHEMA
from scout.report.writer import ReportWriter
from scout.report.writer import system_prompt as writer_prompt
from scout.rules.engine import load_rules

Echo = Callable[[str], None]


class SetupError(Exception):
    """Something the app can't start without (no static data yet, a broken config)."""


@dataclass
class Session:
    watcher: Watcher
    client: LcuClient
    waker: EventWaker
    stats: StatsService
    riot: RiotApi | None
    reports: Path
    errors: Path
    version: str

    def close(self) -> None:
        self.waker.stop()
        self.client.close()
        self.stats.close()
        if self.riot is not None:
            self.riot.close()


def bands(config: Config) -> Bands:
    """Counter-pick bands and the role-guess threshold from config.yaml."""
    cp = config.counterpick
    return Bands(cp.favorable_at, cp.even_from, cp.soft_from, cp.specific_delta,
                 config.roles.low_confidence_below)  # fmt: skip


def stats_service(
    paths: Paths, config: Config, version: str, tables: dict[str, list[dict[str, str]]],
    online: bool,
) -> StatsService:  # fmt: skip
    """The stats database, plus the OP.GG client when online (docs/DATA.md)."""
    s = config.stats
    settings = StatsSettings(s.prior_games, s.synergy_prior_games, s.previous_patch_weight,
                             s.min_games_display)  # fmt: skip
    opgg = Opgg(McpHttp(), min_interval_s=s.opgg_min_interval_s) if online else None
    return StatsService.from_static(
        StatsDb(paths.stats_db, s.rank_filter), settings, version, tables, opgg=opgg,
        max_age_hours=s.matchup_max_age_hours, lane_max_age_hours=s.max_age_hours,
    )  # fmt: skip


def make_writer(config: Config, paths: Paths, knowledge: Knowledge,
                echo: Echo = print) -> ReportWriter | None:  # fmt: skip
    """The LLM writer per config.yaml, or None (with a one-line reason) if it can't run."""
    llm_config = config.llm
    if llm_config.provider == "none":
        echo("LLM writer off (llm.provider: none): rules report only.")
        return None
    if llm_config.provider == "anthropic":
        key = config.secrets.anthropic_api_key
        if not key:
            echo("No ANTHROPIC_API_KEY in .env: rules report only.")
            return None
        ask = anthropic_ask(llm_config.model, key, WRITER_SCHEMA, llm_config.max_output_tokens,
                            llm_config.timeout_seconds)  # fmt: skip
        model = llm_config.model
    else:
        ask = ollama_ask(llm_config.ollama_model, WRITER_SCHEMA, llm_config.ollama_url,
                         llm_config.timeout_seconds)  # fmt: skip
        model = f"ollama:{llm_config.ollama_model}"
    names = set(knowledge.item_names) | {
        part.strip() for rows in knowledge.abilities.values() for row in rows
        for part in row["name"].split("/") if part.strip()
    }  # fmt: skip
    debug = paths.reports_dir(config.report.save_dir) / "debug"
    return ReportWriter(
        ask=ask, system=writer_prompt(paths.report_agent_doc), model=model,
        usage_log=debug / "llm_usage.csv", debug_dir=debug,
        max_calls_per_day=llm_config.max_calls_per_day,
        price_in=llm_config.price_input_per_mtok, price_out=llm_config.price_output_per_mtok,
        names=names,
    )  # fmt: skip


def build_session(paths: Paths, config: Config, *, record: bool = True, llm: bool = True,
                  stats_online: bool = True, echo: Echo = print) -> Session:  # fmt: skip
    """Everything `scout watch` needs. Raises SetupError if the static data isn't there."""
    version = current_version(paths)
    tables = load_static(paths, version) if version else {}
    if not version or not tables:
        raise SetupError("No champion data yet: press Refresh data in Settings (needs internet).")
    try:
        knowledge = load_knowledge(paths, version)
        rules = load_rules(paths.rules_file)
        pool = load_pool(paths.pool_file, config.player.champ_pool)
    except (ValueError, OSError) as exc:  # invalid traits, rules or pool.yaml
        raise SetupError(str(exc)) from None
    find = lambda: discover(config.client.lockfile_path)  # noqa: E731
    client = LcuClient(find)
    reports = paths.reports_dir(config.report.save_dir)
    recorder = Recorder(client, paths.recordings_dir, echo=echo) if record else None
    stats = stats_service(paths, config, version, tables, online=stats_online)
    wiki_rates = rates_from_wiki_positions(tables["champion_meta.csv"])
    watcher = Watcher(
        client=client, knowledge=knowledge, rules=rules,
        rates=merged_rates(stats.role_rates(), wiki_rates),
        index=ChampionIndex.from_static(version, tables), reports_dir=reports,
        notes=read_csv(paths.notes_file),
        low_confidence=config.roles.low_confidence_below,
        recorder=recorder, echo=echo,
        writer=make_writer(config, paths, knowledge, echo) if llm else None,
        max_words=config.llm.max_words, stats=stats,
        fetch_budget_s=config.report.fetch_budget_seconds, review_queue=paths.review_queue,
        bands=bands(config),
        opgg_region=(REGION_OF_PLATFORM.get(config.player.platform, "")
                     if config.report.player_records else ""),
        history_dir=paths.history_dir,
    )  # fmt: skip
    watcher.picker = Picker(
        knowledge=knowledge, pool=pool,
        meta_rows=tables["champion_meta.csv"], role_rates=watcher.rates,
        lookup=lambda: Lookup(stats.db, version, stats.settings, stats.changed),
        bands=bands(config),
    )  # fmt: skip
    if stats_online and stats.lane_stats_stale():

        def refresh_role_rates() -> None:  # in the background: never delays a draft
            try:
                summary = stats.refresh_lane_meta()
            except OpggError as exc:
                echo(f"(Stats refresh failed, using what's cached: {exc})")
                return
            watcher.rates = merged_rates(stats.role_rates(), wiki_rates)
            if watcher.picker is not None:
                watcher.picker.role_rates = watcher.rates
            echo(f"(Stats refreshed: {summary}.)")

        threading.Thread(target=refresh_role_rates, daemon=True).start()
    riot = None
    if config.secrets.riot_api_key:
        riot = RiotApi(config.secrets.riot_api_key, config.player.platform,
                       config.player.regional_route)  # fmt: skip
        try:
            riot.check()
            watcher.riot = riot
        except RiotError as exc:
            echo(f"Loading-screen checks off this session ({exc}).")
    else:
        echo("Loading-screen checks off (no Riot API key; see Settings).")
    waker = EventWaker(find)
    waker.start()
    errors = reports / "debug" / "watch_errors.log"
    return Session(watcher, client, waker, stats, riot, reports, errors, version)
