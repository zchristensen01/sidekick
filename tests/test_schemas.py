import csv
import sqlite3

from scout.data.schemas import MANUAL_FILES, STATS_DB_SCHEMA, TRAIT_TAGS


def test_manual_files_exist_with_schema_headers(repo_paths):
    for name, columns in MANUAL_FILES.items():
        path = repo_paths.manual_dir / name
        assert path.exists(), f"data/manual/{name} missing"
        with path.open(newline="", encoding="utf-8") as f:
            assert tuple(next(csv.reader(f))) == columns, f"{name} header drifted from schemas.py"


def test_stats_schema_creates_cleanly():
    db = sqlite3.connect(":memory:")
    db.executescript(STATS_DB_SCHEMA)
    tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    expected = {"lane_stats", "matchups", "matchup_labels", "synergies", "game_length",
                "matchup_builds", "fetch_log"}  # fmt: skip
    assert expected <= tables


def test_tag_vocabulary_matches_traits_doc(repo_paths):
    doc = (repo_paths.root / "docs" / "TRAITS.md").read_text(encoding="utf-8")
    for tag in TRAIT_TAGS:
        assert f"`{tag}`" in doc, f"tag {tag} is not documented in docs/TRAITS.md"
