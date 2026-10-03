"""The installed app (M24): program files apart from each user's own files, updates from
GitHub Releases checked against their fingerprint, and what the app shows. No network: GitHub
is a fake transport."""

import hashlib
import json
from pathlib import Path

import httpx
import pytest

import scout.app.main as app_main
import scout.paths as paths_module
from scout.app.update import (
    DOWNLOADS,
    LATEST_URL,
    Marker,
    UpdateError,
    check_release,
    download_release,
    marker_file,
    parse_release,
    release_marker,
    scout_command,
    version_key,
    write_marker,
)
from scout.paths import Paths
from scout.version import current_build

INSTALLER = b"MZ pretend installer bytes"
DIGEST = hashlib.sha256(INSTALLER).hexdigest()
URL = DOWNLOADS + "v2026.10.5.3/SidekickSetup.exe"


def latest(**changes) -> dict:
    raw = {"version": "2026.10.5.3", "installer": URL, "sha256": DIGEST,
           "notes": ["M24: a real installer", "Fixes"]}  # fmt: skip
    return raw | changes


def github(answer: dict | None, body: bytes = INSTALLER) -> httpx.Client:
    """A fake GitHub: latest.json, then the installer."""

    def handle(request: httpx.Request) -> httpx.Response:
        if str(request.url) == LATEST_URL:
            return httpx.Response(404) if answer is None else httpx.Response(200, json=answer)
        if str(request.url) == URL:
            return httpx.Response(200, content=body)
        return httpx.Response(404)

    return httpx.Client(transport=httpx.MockTransport(handle))


# ---------------------------------------------------------------- where files go


def test_program_files_and_user_files_are_apart(tmp_path):
    p = Paths(tmp_path / "program", tmp_path / "me")
    for user_file in (p.config_file, p.env_file, p.pool_file, p.pools_dir, p.notes_file,
                      p.recordings_dir, p.generated_dir, p.cache_dir, p.history_dir,
                      p.stats_db, p.reports_dir(), p.static_dir("16.19.1")):  # fmt: skip
        assert (tmp_path / "me") in user_file.parents, user_file
    for program_file in (p.config_example, p.env_example, p.manual_dir, p.report_agent_doc,
                         p.traits_doc, p.build_file, p.research_dir):  # fmt: skip
        assert (tmp_path / "program") in program_file.parents, program_file


def test_one_folder_when_asked(tmp_path, monkeypatch):
    assert Paths(tmp_path).user == tmp_path  # tests and SCOUT_HOME keep everything together
    monkeypatch.setenv("SCOUT_HOME", str(tmp_path))
    found = Paths.from_env()
    assert found.root == found.user == tmp_path.resolve()


def test_default_folders(tmp_path, monkeypatch):
    monkeypatch.delenv("SCOUT_HOME", raising=False)
    monkeypatch.setattr(paths_module.sys, "platform", "win32")
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    found = Paths.from_env()
    assert found.user == tmp_path / "Sidekick"
    assert found.root == paths_module.PACKAGE_DIR.parent  # from source: the repo folder
    monkeypatch.setattr(paths_module.sys, "frozen", True, raising=False)
    monkeypatch.setattr(paths_module.sys, "_MEIPASS", str(tmp_path / "_internal"), raising=False)
    assert Paths.from_env().root == (tmp_path / "_internal").resolve()  # installed


def test_first_start_makes_the_user_folder(tmp_path):
    program = tmp_path / "program"
    program.mkdir()
    (program / "config.example.yaml").write_text("player: {}\n", encoding="utf-8")
    (program / ".env.example").write_text("RIOT_API_KEY=\n", encoding="utf-8")
    p = Paths(program, tmp_path / "me" / "Sidekick")
    made = app_main.first_run(p)
    assert made == ["config.yaml", "pool.yaml", ".env"]
    assert p.config_file.exists() and p.env_file.exists() and p.pool_file.exists()
    assert not (program / "config.yaml").exists()  # nothing personal next to the program


# ---------------------------------------------------------------- versions and releases


def test_versions_compare_as_numbers():
    assert version_key("2026.10.5.12") > version_key("2026.10.5.9")
    assert version_key("2026.10.5.3") > version_key("dev") == ()
    assert version_key("1.x") == ()


def test_build_file(tmp_path):
    p = Paths(tmp_path)
    assert current_build(p).version == "dev"
    p.build_file.write_text(json.dumps({"version": "2026.10.5.3", "commit": "abc1234",
                                        "built": "2026-10-05"}), encoding="utf-8")  # fmt: skip
    assert current_build(p).version == "2026.10.5.3" and current_build(p).commit == "abc1234"


def test_a_release_must_come_from_sidekicks_page_with_a_fingerprint():
    assert parse_release(latest()).version == "2026.10.5.3"
    with pytest.raises(UpdateError, match="isn't on Sidekick's GitHub page"):
        parse_release(latest(installer="https://example.com/SidekickSetup.exe"))
    with pytest.raises(UpdateError, match="fingerprint"):
        parse_release(latest(sha256="abc"))
    with pytest.raises(UpdateError, match="usable version"):
        parse_release(latest(version="latest"))


def test_check_offers_only_a_newer_release():
    with github(latest()) as client:
        newer = check_release("2026.10.5.2", client)
        assert newer.available and newer.version == "2026.10.5.3"
        assert newer.commits == ["M24: a real installer", "Fixes"]
        assert not check_release("2026.10.5.3", client).available
    with github(None) as client:
        assert check_release("2026.10.5.2", client).error == "No release on GitHub yet."


def test_download_is_checked_against_the_fingerprint(tmp_path):
    p = Paths(tmp_path)
    with github(latest()) as client:
        installer = download_release(p, parse_release(latest()), client)
    assert installer.read_bytes() == INSTALLER and installer.name == "SidekickSetup-2026.10.5.3.exe"
    with github(latest(), body=b"something else") as client, pytest.raises(
        UpdateError, match="doesn't match"
    ):
        download_release(p, parse_release(latest(version="2026.10.5.4")), client)
    assert not list((p.cache_dir / "updates").glob("*2026.10.5.4*"))  # deleted, never kept


def test_hidden_commands_use_the_helper_when_installed(monkeypatch, tmp_path):
    assert scout_command("refresh")[-3:] == ["-m", "scout", "refresh"]  # from source
    monkeypatch.setattr(paths_module.sys, "frozen", True, raising=False)
    monkeypatch.setattr("scout.app.update.sys.executable", str(tmp_path / "Sidekick.exe"))
    assert scout_command("refresh", "--pool") == [str(tmp_path / "sidekick-helper.exe"),
                                                  "refresh", "--pool"]  # fmt: skip


# ---------------------------------------------------------------- the app, installed


@pytest.fixture
def installed(scout_home, monkeypatch):
    monkeypatch.setattr(app_main, "frozen", lambda: True)
    scout_home.build_file.write_text(json.dumps({"version": "2026.10.5.3",
                                                 "built": "2026-10-05"}), encoding="utf-8")
    return app_main.App(scout_home)


def test_settings_say_installed_and_research_stays_on_the_developer_copy(installed):
    s = installed.action("settings", {})
    assert s["app"]["installed"] is True and s["app"]["can_research"] is False
    assert s["app"]["commit"] == "2026.10.5.3 (built 2026-10-05)"
    assert "developer copy" in installed.action("research_plan", {})["error"]
    assert installed.research_due() == {}


def test_an_update_that_didnt_finish_says_so(installed, scout_home):
    write_marker(marker_file(scout_home), release_marker("2026.10.5.3",
                 parse_release(latest(version="2026.10.6.1"))))  # fmt: skip
    installed._finish_update(Marker(**json.loads(marker_file(scout_home).read_text())))
    assert "didn't finish" in installed.notice and "2026.10.5.3" in installed.notice
    assert not marker_file(scout_home).exists()


def test_the_check_reports_a_release(installed, monkeypatch):
    monkeypatch.setattr(app_main, "http_client", lambda: github(latest(version="2026.10.6.1")))
    found = installed.action("check_update", {})
    assert found["available"] is True and found["version"] == "2026.10.6.1"
    assert installed.update_available["version"] == "2026.10.6.1"


def test_no_personal_files_in_the_repo_folder():
    """Hard rule 10: the repo folder never holds settings, keys or personal data files."""
    repo = Path(__file__).resolve().parent.parent
    tracked = (repo / ".gitignore").read_text(encoding="utf-8")
    for pattern in (".env", "config.yaml", "pool.yaml", "pools/", "reports/", "data/generated/"):
        assert pattern in tracked
