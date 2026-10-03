import json
import shutil
from pathlib import Path

import pytest

from scout.data import cdragon, ddragon, static, wiki
from scout.data.schemas import MANUAL_FILES, STATIC_FILES
from scout.data.store import Knowledge, build_knowledge, read_csv, write_csv
from scout.paths import Paths

REPO_ROOT = Path(__file__).resolve().parent.parent
SOURCES = REPO_ROOT / "tests" / "fixtures" / "sources"
STATIC_VERSION = "16.19.1"


@pytest.fixture
def repo_paths() -> Paths:
    return Paths(REPO_ROOT)


@pytest.fixture
def example_config_path() -> Path:
    return REPO_ROOT / "config.example.yaml"


def _source(name: str):
    text = (SOURCES / name).read_text(encoding="utf-8")
    return json.loads(text) if name.endswith(".json") else text


@pytest.fixture(scope="session")
def static_tables() -> dict[str, list[dict[str, str]]]:
    """Static tables built from the recorded source samples (Elise, Gnar, LeeSin, Nautilus)."""
    cd = [cdragon.parse_champion(_source(f"cdragon/champion_{k}.json")) for k in (60, 64, 111, 150)]
    built = static.build(
        STATIC_VERSION,
        champions=ddragon.parse_champions(_source("ddragon/championFull_sample.json")),
        summoner_spells=ddragon.parse_summoner_spells(_source("ddragon/summoner.json")),
        items=ddragon.parse_items(_source("ddragon/item_sample.json")),
        cdragon={c.champ_id: c for c in cd},
        wiki=wiki.parse_module(_source("wiki/ChampionData_sample.lua")),
        overrides=[],
    )
    return built.tables


@pytest.fixture
def scout_home(tmp_path, monkeypatch, static_tables) -> Paths:
    """A throwaway SCOUT_HOME: example config, empty manual files, built static data."""
    paths = Paths(tmp_path)
    shutil.copy(REPO_ROOT / "config.example.yaml", paths.config_file)
    (paths.root / "docs").mkdir()
    shutil.copy(REPO_ROOT / "docs" / "TRAITS.md", paths.root / "docs" / "TRAITS.md")
    for name, columns in MANUAL_FILES.items():
        write_csv(paths.manual_dir / name, columns, [])
    for name, columns in STATIC_FILES.items():
        write_csv(paths.static_dir(STATIC_VERSION) / name, columns, static_tables[name])
    (paths.static_dir(STATIC_VERSION) / "manifest.json").write_text("{}", encoding="utf-8")
    paths.patch_file.write_text(STATIC_VERSION + "\n", encoding="utf-8")
    monkeypatch.setenv("SCOUT_HOME", str(tmp_path))
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("RIOT_API_KEY", raising=False)
    return paths


@pytest.fixture(scope="session")
def knowledge() -> Knowledge:
    """Champion facts and traits frozen for tests: tests/fixtures/static/16.19.1/.

    The traits are a copy of data/manual/champion_traits.csv from 2026-10-02, so golden tests
    check the engine, not the owner's later edits. Re-copy on purpose to pick up reviewed traits.
    """
    folder = REPO_ROOT / "tests" / "fixtures" / "static" / STATIC_VERSION
    tables = {name: read_csv(folder / name) for name in ("champions.csv", "champion_meta.csv")}
    return build_knowledge(STATIC_VERSION, tables, read_csv(folder / "champion_traits.csv"))
