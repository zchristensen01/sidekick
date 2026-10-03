"""Load config.yaml and .env into typed, validated settings.

config.example.yaml documents every key. Secrets come only from .env (or the environment)
and are never printed.
"""

import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
from dotenv import dotenv_values

from scout.model.roles import Role

LLM_PROVIDERS = ("anthropic", "ollama", "none")


class ConfigError(Exception):
    """A config problem, with a message that says how to fix it."""


@dataclass(frozen=True)
class PlayerConfig:
    platform: str
    regional_route: str
    champ_pool: dict[Role, tuple[str, ...]]


@dataclass(frozen=True)
class ClientConfig:
    lockfile_path: Path
    poll_seconds: float


@dataclass(frozen=True)
class StatsConfig:
    rank_filter: str
    min_games_display: int
    prior_games: int
    synergy_prior_games: int
    previous_patch_weight: float
    max_age_hours: float
    matchup_max_age_hours: float
    opgg_min_interval_s: float
    collect: bool = True  # M19: measure Riot's match data in the background (needs the key)


@dataclass(frozen=True)
class CounterpickConfig:
    favorable_at: float
    even_from: float
    soft_from: float
    specific_delta: float


@dataclass(frozen=True)
class RolesConfig:
    low_confidence_below: float


@dataclass(frozen=True)
class ReportConfig:
    fetch_budget_seconds: float
    save_dir: str
    player_records: bool = True  # loading screen: players' OP.GG records (M16, POLICY.md)


@dataclass(frozen=True)
class LlmConfig:
    provider: str
    model: str
    ollama_model: str
    max_output_tokens: int
    max_words: dict[Role, int]
    max_calls_per_day: int = 40  # after this, the free rules report is shown
    timeout_seconds: float = 30.0
    price_input_per_mtok: float = 1.0  # USD per million tokens, for the usage log's estimate
    price_output_per_mtok: float = 5.0
    ollama_url: str = "http://localhost:11434"


@dataclass(frozen=True)
class Secrets:
    riot_api_key: str | None = field(default=None, repr=False)
    anthropic_api_key: str | None = field(default=None, repr=False)


@dataclass(frozen=True)
class Config:
    player: PlayerConfig
    client: ClientConfig
    stats: StatsConfig
    counterpick: CounterpickConfig
    roles: RolesConfig
    report: ReportConfig
    llm: LlmConfig
    secrets: Secrets
    source: Path
    # The owner's PC (whoever maintains Sidekick): collects Riot match data, runs the backtest,
    # shows research reminders. Everyone else: False, and those parts are hidden.
    owner: bool = False


def load_config(path: Path, env_path: Path | None = None) -> Config:
    """Read and validate a config file. Raises ConfigError with a fix-it message."""
    if not path.exists():
        raise ConfigError(
            f"No config file at {path}. Copy config.example.yaml to config.yaml and edit it."
        )
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        raise ConfigError(f"{path} is not valid YAML: {exc}") from exc
    if not isinstance(raw, dict):
        raise ConfigError(f"{path} must be a YAML mapping of sections.")

    config = Config(
        player=_player(_section(raw, "player")),
        client=_client(_section(raw, "client")),
        stats=_stats(_section(raw, "stats")),
        counterpick=_counterpick(_section(raw, "counterpick")),
        roles=RolesConfig(
            low_confidence_below=_number(_section(raw, "roles"), "low_confidence_below", "roles",
                                         low=0, high=1),
        ),
        report=_report(_section(raw, "report")),
        llm=_llm(_section(raw, "llm")),
        secrets=load_secrets(env_path),
        source=path,
        owner=_flag(raw, "owner", "config", default=False),
    )  # fmt: skip
    return config


def load_secrets(env_path: Path | None) -> Secrets:
    """Secrets from the .env file, falling back to real environment variables."""
    values: dict[str, str | None] = {}
    if env_path is not None and env_path.exists():
        values = dotenv_values(env_path)

    def pick(name: str) -> str | None:
        value = values.get(name) or os.environ.get(name)
        return value.strip() if value and value.strip() else None

    return Secrets(riot_api_key=pick("RIOT_API_KEY"), anthropic_api_key=pick("ANTHROPIC_API_KEY"))


# ---------------------------------------------------------------- sections


def _player(d: dict[str, Any]) -> PlayerConfig:
    pool_raw = d.get("champ_pool") or {}
    if not isinstance(pool_raw, dict):
        raise ConfigError("player.champ_pool must map roles to lists, e.g. jungle: [LeeSin].")
    pool: dict[Role, tuple[str, ...]] = {}
    for role_name, champs in pool_raw.items():
        role = _role(role_name, f"player.champ_pool.{role_name}")
        if champs is None:
            champs = []
        if not isinstance(champs, list) or not all(isinstance(c, str) for c in champs):
            raise ConfigError(f"player.champ_pool.{role_name} must be a list of champion ids.")
        pool[role] = tuple(champs)
    # riot_id and main_role in older config files are ignored: the account and the role
    # come from the League client (M22, champ select)
    return PlayerConfig(
        platform=_text(d, "platform", "player"),
        regional_route=_text(d, "regional_route", "player"),
        champ_pool=pool,
    )


def _client(d: dict[str, Any]) -> ClientConfig:
    return ClientConfig(
        lockfile_path=Path(_text(d, "lockfile_path", "client")),
        poll_seconds=_number(d, "poll_seconds", "client", low=0.1, high=10),
    )


def _stats(d: dict[str, Any]) -> StatsConfig:
    s = "stats"
    return StatsConfig(
        rank_filter=_text(d, "rank_filter", s),
        min_games_display=int(_number(d, "min_games_display", s, low=0)),
        prior_games=int(_number(d, "prior_games", s, low=0)),
        synergy_prior_games=int(_number(d, "synergy_prior_games", s, low=0)),
        previous_patch_weight=_number(d, "previous_patch_weight", s, low=0, high=1),
        max_age_hours=_number(d, "max_age_hours", s, low=0),
        matchup_max_age_hours=_number(d, "matchup_max_age_hours", s, low=0),
        opgg_min_interval_s=_number(d, "opgg_min_interval_s", s, low=0),
        collect=_flag(d, "collect", s, default=True),
    )


def _counterpick(d: dict[str, Any]) -> CounterpickConfig:
    s = "counterpick"
    cp = CounterpickConfig(
        favorable_at=_number(d, "favorable_at", s, low=0, high=100),
        even_from=_number(d, "even_from", s, low=0, high=100),
        soft_from=_number(d, "soft_from", s, low=0, high=100),
        specific_delta=_number(d, "specific_delta", s, low=0, high=50),
    )
    if not cp.soft_from < cp.even_from < cp.favorable_at:
        raise ConfigError(
            "counterpick bands must be in order: soft_from < even_from < favorable_at "
            f"(got {cp.soft_from}, {cp.even_from}, {cp.favorable_at})."
        )
    return cp


def _report(d: dict[str, Any]) -> ReportConfig:
    s = "report"
    return ReportConfig(
        fetch_budget_seconds=_number(d, "fetch_budget_seconds", s, low=0, high=60),
        save_dir=_text(d, "save_dir", s),
        player_records=_flag(d, "player_records", s, default=True),
    )


def _flag(d: dict[str, Any], key: str, section: str, default: bool) -> bool:
    value = d.get(key, default)
    if not isinstance(value, bool):
        raise ConfigError(f"{section}.{key} must be true or false.")
    return value


def _llm(d: dict[str, Any]) -> LlmConfig:
    s = "llm"
    provider = _text(d, "provider", s)
    if provider not in LLM_PROVIDERS:
        raise ConfigError(
            f"llm.provider must be one of {', '.join(LLM_PROVIDERS)} (got {provider!r})."
        )
    if "temperature" in d:
        raise ConfigError(
            "llm.temperature isn't supported: newer models reject it. Remove it "
            "(docs/REPORT_AGENT.md, Model notes)."
        )
    words_raw = d.get("max_words") or {}
    if not isinstance(words_raw, dict):
        raise ConfigError("llm.max_words must map roles to word counts.")
    max_words = {
        _role(name, f"llm.max_words.{name}"): int(_number(words_raw, name, "llm.max_words", low=20))
        for name in words_raw
    }
    missing = [r.value for r in Role if r not in max_words]
    if missing:
        raise ConfigError(f"llm.max_words is missing roles: {', '.join(missing)}.")
    ollama_model = d.get("ollama_model") or ""
    if provider == "ollama" and not ollama_model:
        raise ConfigError("llm.ollama_model must be set when llm.provider is ollama.")
    return LlmConfig(
        provider=provider,
        model=_text(d, "model", s),
        ollama_model=str(ollama_model),
        max_output_tokens=int(_number(d, "max_output_tokens", s, low=100)),
        max_words=max_words,
        max_calls_per_day=int(_optional(d, "max_calls_per_day", s, 40, low=0)),
        timeout_seconds=_optional(d, "timeout_seconds", s, 30.0, low=5, high=120),
        price_input_per_mtok=_optional(d, "price_input_per_mtok", s, 1.0, low=0),
        price_output_per_mtok=_optional(d, "price_output_per_mtok", s, 5.0, low=0),
        ollama_url=str(d.get("ollama_url") or "http://localhost:11434"),
    )


# ---------------------------------------------------------------- helpers


def _section(raw: dict[str, Any], name: str) -> dict[str, Any]:
    value = raw.get(name)
    if not isinstance(value, dict):
        raise ConfigError(f"Missing or invalid section '{name}:' (see config.example.yaml).")
    return value


def _text(d: dict[str, Any], key: str, section: str) -> str:
    value = d.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ConfigError(f"{section}.{key} must be a non-empty string.")
    return value.strip()


def _number(
    d: dict[str, Any], key: str, section: str, low: float | None = None, high: float | None = None
) -> float:
    value = d.get(key)
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ConfigError(f"{section}.{key} must be a number (got {value!r}).")
    if (low is not None and value < low) or (high is not None and value > high):
        raise ConfigError(f"{section}.{key} must be between {low} and {high} (got {value}).")
    return float(value)


def _optional(
    d: dict[str, Any], key: str, section: str, default: float,
    low: float | None = None, high: float | None = None,
) -> float:  # fmt: skip
    """A number that may be left out of config.yaml (older configs don't have it)."""
    return default if d.get(key) is None else _number(d, key, section, low=low, high=high)


def _role(value: Any, where: str) -> Role:
    try:
        return Role(str(value).strip().lower())
    except ValueError:
        names = ", ".join(r.value for r in Role)
        raise ConfigError(f"{where} must be one of: {names} (got {value!r}).") from None


# ---------------------------------------------------------------- writing .env


def with_env_value(text: str, name: str, value: str) -> str:
    """.env text with `name=value` set: the existing line replaced, or one added at the end."""
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if line.split("=", 1)[0].strip() == name and not line.lstrip().startswith("#"):
            lines[i] = f"{name}={value}"
            break
    else:
        lines.append(f"{name}={value}")
    return "\n".join(lines) + "\n"


_PLAIN = re.compile(r"[A-Za-z0-9_.-]+")


def with_value(text: str, section: str, key: str, value: str | int | float | bool,
               add: bool = False) -> str:  # fmt: skip
    """config.yaml text with one `section.key` value replaced; comments and the rest kept.
    With `add`, a missing key is added at the end of its section (an older config.yaml);
    otherwise a missing key raises ConfigError."""
    lines = text.splitlines()
    if isinstance(value, bool):
        shown = "true" if value else "false"
    elif not isinstance(value, str) or _PLAIN.fullmatch(value):
        shown = str(value)
    else:
        shown = json.dumps(value)
    inside, last = False, None
    for i, line in enumerate(lines):
        if line and not line[0].isspace() and not line.startswith("#"):
            inside = line.split(":", 1)[0].strip() == section
            continue
        if inside and line.strip() and not line.lstrip().startswith("#"):
            last = i
        found = inside and re.match(rf"^(\s+{re.escape(key)}:\s*)(.*?)(\s+#.*)?$", line)
        if found:
            lines[i] = found.group(1) + shown + (found.group(3) or "")
            return "\n".join(lines) + "\n"
    if add and last is not None:
        indent = len(lines[last]) - len(lines[last].lstrip())
        lines.insert(last + 1, f"{' ' * indent}{key}: {shown}")
        return "\n".join(lines) + "\n"
    raise ConfigError(f"config.yaml has no `{key}:` under `{section}:` to change.")


# ---------------------------------------------------------------- writing the champ pool

