"""The app without a command line (M14): pool.yaml with comfort ratings, the Settings actions,
the Update button's git steps, champion pictures, config edits. No network, no window: the
updater runs against local git repositories, pictures come from a fake download."""

import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

from scout.app.main import App, first_run
from scout.app.portraits import Portraits
from scout.app.update import check, pull, read_marker
from scout.config import ConfigError, load_config, with_value
from scout.data.store import static_complete
from scout.model.roles import Role
from scout.paths import Paths
from scout.picks import Candidate, Option, _rank, candidates
from scout.pool import PoolError, champion_lists, load_pool, parse_pool, pool_text, save_pool
from scout.report.view import status_view

PNG = b"\x89PNG\r\n\x1a\nfake"


# ---------------------------------------------------------------- pool.yaml


def test_pool_round_trip_best_rated_first(tmp_path):
    path = tmp_path / "pool.yaml"
    save_pool(path, {Role.JUNGLE: {"Elise": 4, "LeeSin": 5, "Amumu": 4}})
    pool = load_pool(path)
    assert list(pool[Role.JUNGLE].items()) == [("LeeSin", 5), ("Elise", 4), ("Amumu", 4)]
    assert pool[Role.TOP] == {}
    assert path.read_text(encoding="utf-8").startswith("# Your champions per lane")
    assert champion_lists(pool)[Role.JUNGLE] == ("LeeSin", "Elise", "Amumu")


def test_pool_falls_back_to_config_lists(tmp_path):
    pool = load_pool(tmp_path / "missing.yaml", {Role.SUPPORT: ("Braum", "Nautilus")})
    assert pool[Role.SUPPORT] == {"Braum": 3, "Nautilus": 3}


def test_pool_accepts_plain_lists_and_clamps(tmp_path):
    pool = parse_pool({"mid": ["Ahri"], "top": {"Gnar": 9}})
    assert pool[Role.MID] == {"Ahri": 3}
    assert pool[Role.TOP] == {"Gnar": 5}


@pytest.mark.parametrize("raw, message", [
    ({"middle": {"Ahri": 3}}, "isn't a lane"),
    ({"mid": {"Ahri": "five"}}, "rating must be 1-5"),
    ({"mid": "Ahri"}, "must list champions"),
    (["mid"], "must map lanes"),
])  # fmt: skip
def test_pool_errors_say_how_to_fix(raw, message):
    with pytest.raises(PoolError, match=message):
        parse_pool(raw)


def test_pool_text_reads_back():
    pool = {Role.BOT: {"Sivir": 2}}
    assert parse_pool(yaml.safe_load(pool_text(pool)))[Role.BOT] == {"Sivir": 2}


# ---------------------------------------------------------------- comfort in pick ranking


def _option(champ, stars, rate, comfort=0):
    return Option(Candidate(champ, "pool", comfort, stars), champ, "even", rate, "")


def test_comfort_stars_win_close_calls():
    # a 5-star champion 3 points behind a 1-star one: within 4 stars x 1 point, so it's first
    ranked = _rank([_option("Sure", 5, 0.50), _option("Shaky", 1, 0.53, comfort=1)])
    assert [o.name for o in ranked] == ["Sure", "Shaky"]
    # 5 points behind: the numbers win
    ranked = _rank([_option("Sure", 5, 0.50), _option("Shaky", 1, 0.55, comfort=1)])
    assert [o.name for o in ranked] == ["Shaky", "Sure"]
    # equal stars: the old 1-point tie-break by pool order
    ranked = _rank([_option("A", 3, 0.505, comfort=1), _option("B", 3, 0.51, comfort=0)])
    assert [o.name for o in ranked] == ["B", "A"]


def test_candidates_from_rated_pool():
    pool = {Role.JUNGLE: {"Elise": 2, "LeeSin": 5}}
    found = candidates(Role.JUNGLE, pool, {}, None, [], unavailable={"Amumu"})
    assert [(c.champ, c.stars, c.comfort) for c in found] == [("LeeSin", 5, 0), ("Elise", 2, 1)]


# ---------------------------------------------------------------- config.yaml edits


def test_with_value_changes_one_line_and_keeps_comments(example_config_path):
    text = example_config_path.read_text(encoding="utf-8")
    new = with_value(with_value(text, "llm", "provider", "none"), "player", "platform", "euw1")
    changed = [(a, b) for a, b in zip(text.splitlines(), new.splitlines(), strict=True) if a != b]
    assert len(changed) == 2
    assert changed[0][1].startswith("  platform: euw1  ")
    assert "# Riot API platform routing" in changed[0][1]
    assert changed[1][1].startswith("  provider: none") and "# anthropic | ollama" in changed[1][1]
    with pytest.raises(ConfigError, match="no `nope:` under `llm:`"):
        with_value(text, "llm", "nope", "x")


# ---------------------------------------------------------------- data format check


def test_static_rebuilds_when_a_files_columns_change(scout_home):
    version = "16.19.1"
    assert static_complete(scout_home, version)
    path = scout_home.static_dir(version) / "champions.csv"
    text = path.read_text(encoding="utf-8")
    path.write_text(text.replace("champ_id", "champion", 1), encoding="utf-8")
    assert not static_complete(scout_home, version)


# ---------------------------------------------------------------- champion pictures


def test_portraits_download_once_and_cache(tmp_path):
    calls = []

    def get(url):
        calls.append(url)
        if "Gnar" in url:
            raise OSError("offline")
        return PNG

    pics = Portraits(tmp_path, "16.19.1", ["LeeSin", "Gnar"], get)
    assert pics.data_uri("LeeSin").startswith("data:image/png;base64,")
    assert pics.data_uri("LeeSin")  # second time from disk
    assert calls == ["https://ddragon.leagueoflegends.com/cdn/16.19.1/img/champion/LeeSin.png"]
    assert pics.data_uri("Gnar") is None and pics.data_uri("Gnar") is None
    assert len(calls) == 2  # a failure isn't retried every frame
    assert pics.data_uri("../../secrets") is None  # only known champion ids
    assert pics.many(["LeeSin", "Gnar", "Nope"]).keys() == {"LeeSin"}
    assert (tmp_path / "LeeSin.png").read_bytes() == PNG


def test_portraits_fetch_missing(tmp_path):
    pics = Portraits(tmp_path, "16.19.1", ["Elise", "LeeSin"], lambda url: PNG)
    assert pics.fetch_missing() == (2, 0)
    assert pics.fetch_missing() == (0, 0)


# ---------------------------------------------------------------- the app's Settings actions


def test_first_run_makes_files(tmp_path, repo_paths):
    paths = Paths(tmp_path)
    shutil.copy(repo_paths.config_example, paths.config_example)
    shutil.copy(repo_paths.env_example, paths.env_example)
    assert first_run(paths) == ["config.yaml", "pool.yaml", ".env"]
    assert load_pool(paths.pool_file)[Role.JUNGLE] == {}  # not the example's champions
    assert first_run(paths) == []


@pytest.fixture
def app(scout_home):
    return App(scout_home)


def test_settings_shows_state(app, scout_home):
    s = app.action("settings", {})
    assert "pool" not in s  # the Champions page has its own action (M22)
    assert s["account"]["region"] == "NA"
    assert s["llm"]["on"] is True and s["llm"]["has_key"] is False
    assert s["riot"]["state"] == "none"
    assert s["app"]["owner"] is False and s["collect"]["on"] is False  # not the owner's PC
    config = scout_home.config_file
    config.write_text(config.read_text(encoding="utf-8").replace("owner: false", "owner: true"),
                      encoding="utf-8")  # fmt: skip
    owner = app.action("settings", {})
    assert owner["app"]["owner"] is True and owner["collect"]["on"] is True
    assert owner["collect"]["games"] == 0
    assert app.action("set_collect", {"on": False}) == {"ok": True}  # the owner can pause it
    assert app.action("settings", {})["collect"]["on"] is False
    assert app.action("research_plan", {})["empty"] is True
    assert s["app"]["patch"] == "16.19.1"


def test_save_pool_checks_and_writes(app, scout_home):
    bad = app.action("save_pool", {"pool": {"jungle": [{"id": "NotAChamp", "stars": 3}]}})
    assert "isn't a champion" in bad["error"]
    bad = app.action("save_pool", {"pool": {"jungle": [{"id": "LeeSin", "stars": 7}]}})
    assert "1 to 5" in bad["error"]
    ok = app.action("save_pool", {"pool": {"jungle": [{"id": "Elise", "stars": 3},
                                                      {"id": "LeeSin", "stars": 5}]}})  # fmt: skip
    assert ok == {"ok": True}
    assert list(load_pool(scout_home.pool_file)[Role.JUNGLE]) == ["LeeSin", "Elise"]
    page = app.action("champions", {})  # no client yet, no account seen: pool.yaml
    assert page["account"] is None
    assert page["pool"]["jungle"] == [{"id": "LeeSin", "name": "Lee Sin", "stars": 5},
                                      {"id": "Elise", "name": "Elise", "stars": 3}]  # fmt: skip
    assert {"id": "Gnar", "name": "Gnar"} in page["champions"]


def test_llm_switch_and_account(app, scout_home):
    assert app.action("set_llm", {"on": False}) == {"ok": True}
    assert load_config(scout_home.config_file).llm.provider == "none"
    on = app.action("set_llm", {"on": True})
    assert "no Anthropic key" in on["warning"]
    assert "Pick your region" in app.action("save_account", {"region": "Mars"})["error"]
    assert app.action("save_account", {"region": "EUW"}) == {"ok": True}  # no name to type
    player = load_config(scout_home.config_file).player
    assert (player.platform, player.regional_route) == ("euw1", "europe")
    account = app.action("settings", {})["account"]
    assert account["region"] == "EUW" and account["logged_in"] == "" and not account["detected"]


def test_keys_are_checked_before_saving(app, scout_home):
    assert "RGAPI-" in app.action("save_key", {"kind": "riot", "value": "hello"})["error"]
    assert "sk-ant-" in app.action("save_key", {"kind": "anthropic", "value": "x"})["error"]
    assert not scout_home.env_file.exists()  # nothing saved


def test_unknown_action_and_icons(app):
    assert "Unknown action" in app.action("format_disk", {})["error"]
    app.portraits = Portraits(Path("unused"), "16.19.1", ["LeeSin"], None)
    assert app.action("icons", {"ids": ["LeeSin"]}) == {"icons": {}}  # offline, not cached


def test_problem_screen_has_a_title():
    view = status_view("problem", "config.yaml is broken", title="Settings need a look")
    assert view == {"screen": "status", "state": "problem", "message": "config.yaml is broken",
                    "title": "Settings need a look"}  # fmt: skip


def test_page_has_the_logo_inlined():
    from scout.app.window import page

    html = page()
    assert "__LOGO__" not in html and "data:image/png;base64," in html


# ---------------------------------------------------------------- the Update button (git)


def _git(cwd, *args):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


@pytest.fixture
def repos(tmp_path):
    """origin (bare), `mine` (the app's copy) and `dev` (where a new commit comes from)."""
    if shutil.which("git") is None:
        pytest.skip("git isn't installed")
    origin, mine, dev = tmp_path / "origin.git", tmp_path / "mine", tmp_path / "dev"
    _git(tmp_path, "init", "--bare", "-b", "main", str(origin))
    _git(tmp_path, "clone", str(origin), str(dev))
    for repo in (dev,):
        _git(repo, "config", "user.email", "test@example.com")
        _git(repo, "config", "user.name", "Test")
    (dev / "pyproject.toml").write_text("v1\n", encoding="utf-8")
    (dev / "notes.txt").write_text("a\n", encoding="utf-8")
    _git(dev, "add", ".")
    _git(dev, "commit", "-m", "First")
    _git(dev, "push", "-u", "origin", "main")
    _git(tmp_path, "clone", str(origin), str(mine))
    return mine, dev


def test_update_check_and_pull(repos):
    mine, dev = repos
    assert check(mine).behind == 0 and not check(mine).available
    (dev / "notes.txt").write_text("b\n", encoding="utf-8")
    _git(dev, "commit", "-am", "Better notes")
    _git(dev, "push")
    status = check(mine)
    assert (status.behind, status.commits, status.available) == (1, ["Better notes"], True)
    marker = pull(Paths(mine))
    assert marker.commits == ["Better notes"] and marker.reinstall is False
    assert (mine / "notes.txt").read_text(encoding="utf-8") == "b\n"
    assert read_marker(mine / "data" / "cache" / "update.json") == marker


def test_update_reinstalls_when_pyproject_changes(repos):
    mine, dev = repos
    (dev / "pyproject.toml").write_text("v2\n", encoding="utf-8")
    _git(dev, "commit", "-am", "New dependency")
    _git(dev, "push")
    assert pull(Paths(mine)).reinstall is True


def test_update_keeps_local_edits_safe(repos):
    mine, dev = repos
    (dev / "notes.txt").write_text("theirs\n", encoding="utf-8")
    _git(dev, "commit", "-am", "Their notes")
    _git(dev, "push")
    (mine / "notes.txt").write_text("mine\n", encoding="utf-8")  # an uncommitted edit
    status = check(mine)
    assert status.edited == ["notes.txt"]
    from scout.app.update import UpdateError

    with pytest.raises(UpdateError, match="files you've edited here, so nothing was changed"):
        pull(Paths(mine))
    assert (mine / "notes.txt").read_text(encoding="utf-8") == "mine\n"


def test_player_records_switch_even_on_an_older_config(app, scout_home):
    assert app.action("settings", {})["players"] == {"on": True}
    assert app.action("set_players", {"on": False}) == {"ok": True}
    assert load_config(scout_home.config_file).report.player_records is False
    old = scout_home.config_file.read_text(encoding="utf-8")
    lines = [line for line in old.splitlines() if "player_records" not in line]
    scout_home.config_file.write_text("\n".join(lines) + "\n", encoding="utf-8")  # pre-M16 file
    assert load_config(scout_home.config_file).report.player_records is True  # the default
    assert app.action("set_players", {"on": False}) == {"ok": True}  # the key gets added
    assert load_config(scout_home.config_file).report.player_records is False
