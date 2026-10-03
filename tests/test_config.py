from pathlib import Path

import pytest
import yaml

from scout.config import ConfigError, load_config
from scout.model.roles import Role


def write_config(tmp_path: Path, example: Path, **changes) -> Path:
    """Copy the example config with some (section, key) values changed or removed."""
    raw = yaml.safe_load(example.read_text(encoding="utf-8"))
    for dotted, value in changes.items():
        section, key = dotted.split("__")
        if value is None:
            raw[section].pop(key, None)
        else:
            raw[section][key] = value
    path = tmp_path / "config.yaml"
    path.write_text(yaml.safe_dump(raw), encoding="utf-8")
    return path


def test_example_config_loads(example_config_path, tmp_path):
    config = load_config(example_config_path)
    assert config.player.champ_pool[Role.JUNGLE] == ()  # nobody's champions in the example
    pool = {"jungle": ["LeeSin", "Elise"], "top": [], "mid": [], "bot": [], "support": []}
    written = load_config(write_config(tmp_path, example_config_path, player__champ_pool=pool))
    assert written.player.champ_pool[Role.JUNGLE] == ("LeeSin", "Elise")
    assert set(config.llm.max_words) == set(Role)
    assert (
        config.counterpick.soft_from
        < config.counterpick.even_from
        < config.counterpick.favorable_at
    )


def test_missing_file_explains_the_fix(tmp_path):
    with pytest.raises(ConfigError, match="config.example.yaml"):
        load_config(tmp_path / "config.yaml")


def test_bad_role_is_rejected(tmp_path, example_config_path):
    path = write_config(tmp_path, example_config_path, player__champ_pool={"adc": ["Jinx"]})
    with pytest.raises(ConfigError, match="player.champ_pool.adc"):
        load_config(path)


def test_older_config_keys_are_ignored(tmp_path, example_config_path):
    """riot_id and main_role came from config.yaml before the client supplied them (M22)."""
    path = write_config(tmp_path, example_config_path, player__riot_id="Name#TAG",
                        player__main_role="jungle")  # fmt: skip
    assert load_config(path).player.platform == "na1"


def test_counterpick_bands_must_be_ordered(tmp_path, example_config_path):
    path = write_config(tmp_path, example_config_path, counterpick__soft_from=50.0)
    with pytest.raises(ConfigError, match="in order"):
        load_config(path)


def test_temperature_is_rejected(tmp_path, example_config_path):
    path = write_config(tmp_path, example_config_path, llm__temperature=0.2)
    with pytest.raises(ConfigError, match="temperature"):
        load_config(path)


def test_secrets_load_from_env_file_and_never_print(tmp_path, example_config_path, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("RIOT_API_KEY", raising=False)
    env = tmp_path / ".env"
    env.write_text("ANTHROPIC_API_KEY=sk-test-123\nRIOT_API_KEY=\n", encoding="utf-8")
    config = load_config(example_config_path, env)
    assert config.secrets.anthropic_api_key == "sk-test-123"
    assert config.secrets.riot_api_key is None
    assert "sk-test-123" not in repr(config)
