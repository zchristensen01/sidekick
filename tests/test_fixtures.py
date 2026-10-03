"""Fixtures stay usable and documented."""

import json

import yaml

from scout.model.roles import Role


def test_source_fixtures_parse_and_are_documented(repo_paths):
    sources = repo_paths.fixtures_dir / "sources"
    readme = (sources / "README.md").read_text(encoding="utf-8")
    files = [p for p in sources.rglob("*") if p.is_file() and p.name != "README.md"]
    assert files, "no source fixtures recorded"
    for path in files:
        rel = path.relative_to(sources).as_posix()
        assert f"`{rel}`" in readme, f"{rel} is not listed in sources/README.md"
        if path.suffix == ".json":
            json.loads(path.read_text(encoding="utf-8"))


def test_game_fixtures_have_every_role(repo_paths):
    games = list((repo_paths.fixtures_dir / "games").glob("*.yaml"))
    assert games
    roles = {r.value for r in Role}
    for path in games:
        game = yaml.safe_load(path.read_text(encoding="utf-8"))
        assert game["name"] == path.stem
        assert set(game["ally"]) == roles and set(game["enemy"]) == roles
        assert game["my_role"] in roles
