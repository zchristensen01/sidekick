"""Finding the League client: process arguments, lockfile fallback, pinned certificate."""

import ssl

import psutil
import pytest

from scout.lcu import connection
from scout.lcu.connection import (
    CERT_PATH,
    LcuCredentials,
    discover,
    from_lockfile,
    from_process,
    parse_lockfile,
    parse_process_args,
    ssl_context,
)

UX_ARGS = [
    "C:/Riot Games/League of Legends/LeagueClientUx.exe",
    "--riotclient-auth-token=riot-client-token",
    "--riotclient-app-port=50100",
    "--no-rads",
    "--app-port=50200",
    "--remoting-auth-token=lcu-token_1",
    "--install-directory=C:/Riot Games/League of Legends",
]


class FakeProc:
    def __init__(self, name: str, args: list[str] | None = None, error: Exception | None = None):
        self.info = {"name": name}
        self._args = args or []
        self._error = error

    def cmdline(self) -> list[str]:
        if self._error:
            raise self._error
        return self._args


def test_parse_process_args():
    creds = parse_process_args(UX_ARGS)
    assert creds == LcuCredentials(port=50200, token="lcu-token_1", source="process")
    assert creds.base_url == "https://127.0.0.1:50200"
    assert creds.auth == ("riot", "lcu-token_1")


def test_parse_process_args_handles_quotes():
    args = ['"--app-port=50200"', '--remoting-auth-token="lcu-token"']
    assert parse_process_args(args) == LcuCredentials(50200, "lcu-token", "process")


@pytest.mark.parametrize(
    "args",
    [
        [],
        ["--app-port=50200"],  # no token
        ["--remoting-auth-token=t"],  # no port
        ["--app-port=abc", "--remoting-auth-token=t"],
        ["--riotclient-app-port=50100", "--riotclient-auth-token=t"],  # the Riot Client's own API
    ],
)
def test_parse_process_args_rejects_incomplete(args):
    assert parse_process_args(args) is None


def test_from_process_only_reads_league_client_ux(monkeypatch):
    procs = [
        FakeProc("RiotClientServices.exe", ["--app-port=1", "--remoting-auth-token=riot"]),
        FakeProc("LeagueClientUxRender.exe", ["--app-port=2", "--remoting-auth-token=render"]),
        FakeProc("LeagueClientUx.exe", error=psutil.AccessDenied()),
        FakeProc("leagueclientux.exe", UX_ARGS),
    ]
    monkeypatch.setattr(psutil, "process_iter", lambda attrs=None: iter(procs))
    assert from_process() == LcuCredentials(50200, "lcu-token_1", "process")


def test_from_process_none_when_not_running(monkeypatch):
    monkeypatch.setattr(psutil, "process_iter", lambda attrs=None: iter([FakeProc("explorer.exe")]))
    assert from_process() is None


def test_parse_lockfile():
    pid, creds = parse_lockfile("LeagueClient:4242:50200:lcu-token:https\n")
    assert pid == 4242
    assert creds == LcuCredentials(50200, "lcu-token", "lockfile")


@pytest.mark.parametrize(
    "text",
    ["", "LeagueClient:4242:50200:lcu-token", "LeagueClient:4242:50200:tok:http",
     "LeagueClient:x:50200:tok:https", "LeagueClient:4242:50200::https"],
)  # fmt: skip
def test_parse_lockfile_rejects_malformed(text):
    assert parse_lockfile(text) is None


def test_from_lockfile(tmp_path, monkeypatch):
    lockfile = tmp_path / "lockfile"
    lockfile.write_text("LeagueClient:4242:50200:lcu-token:https", encoding="utf-8")
    monkeypatch.setattr(psutil, "pid_exists", lambda pid: pid == 4242)
    assert from_lockfile(lockfile) == LcuCredentials(50200, "lcu-token", "lockfile")


def test_from_lockfile_ignores_stale_and_missing(tmp_path, monkeypatch):
    lockfile = tmp_path / "lockfile"
    lockfile.write_text("LeagueClient:4242:50200:lcu-token:https", encoding="utf-8")
    monkeypatch.setattr(psutil, "pid_exists", lambda pid: False)  # the client crashed
    assert from_lockfile(lockfile) is None
    assert from_lockfile(tmp_path / "missing") is None


def test_discover_prefers_process_then_lockfile(tmp_path, monkeypatch):
    from_file = LcuCredentials(1, "file", "lockfile")
    from_args = LcuCredentials(2, "args", "process")
    monkeypatch.setattr(connection, "from_lockfile", lambda path: from_file)
    monkeypatch.setattr(connection, "from_process", lambda: from_args)
    assert discover(tmp_path / "lockfile") is from_args
    monkeypatch.setattr(connection, "from_process", lambda: None)
    assert discover(tmp_path / "lockfile") is from_file


def test_token_never_in_repr():
    assert "secret-token" not in repr(LcuCredentials(50200, "secret-token", "process"))


def test_ssl_context_pins_riot_root_certificate():
    assert CERT_PATH.exists()
    context = ssl_context()
    assert context.verify_mode == ssl.CERT_REQUIRED  # the certificate chain is checked
    assert context.check_hostname is True  # the client's certificate lists 127.0.0.1
    assert not context.verify_flags & ssl.VERIFY_X509_STRICT
    subjects = [dict(field[0] for field in ca["subject"]) for ca in context.get_ca_certs()]
    assert subjects == [
        {
            "countryName": "US", "stateOrProvinceName": "California",
            "localityName": "Santa Monica", "organizationName": "Riot Games",
            "organizationalUnitName": "LoL Game Engineering",
            "commonName": "LoL Game Engineering Certificate Authority",
            "emailAddress": "gametechnologies@riotgames.com",
        }
    ]  # fmt: skip
