"""Find the running League client and its credentials.

Order: the LeagueClientUx.exe process arguments (psutil), then the lockfile. The port and token
change every time the client restarts, so callers re-discover after a failed request
(scout/lcu/client.py does this). The connection pins Riot's root certificate, riotgames.pem,
shipped next to this file. See docs/LCU.md section 1.
"""

import ssl
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path

import psutil

PROCESS_NAME = "leagueclientux.exe"  # compared lowercase; not LeagueClientUxRender.exe
CERT_PATH = Path(__file__).with_name("riotgames.pem")


@dataclass(frozen=True)
class LcuCredentials:
    port: int
    token: str = field(repr=False)
    source: str  # "process" or "lockfile"

    @property
    def base_url(self) -> str:
        return f"https://127.0.0.1:{self.port}"

    @property
    def auth(self) -> tuple[str, str]:
        """HTTPS basic auth: user `riot`, password = the token."""
        return ("riot", self.token)


def discover(lockfile_path: Path) -> LcuCredentials | None:
    """Credentials for the running client, or None if it isn't running."""
    return from_process() or from_lockfile(lockfile_path)


def from_process() -> LcuCredentials | None:
    """Read `--app-port` and `--remoting-auth-token` from the LeagueClientUx.exe command line."""
    for proc in psutil.process_iter(["name"]):
        if (proc.info.get("name") or "").lower() != PROCESS_NAME:
            continue
        try:
            args = proc.cmdline()
        except psutil.Error:  # gone, or not allowed to read it: try the lockfile instead
            continue
        credentials = parse_process_args(args)
        if credentials:
            return credentials
    return None


def parse_process_args(args: Sequence[str]) -> LcuCredentials | None:
    """Credentials from command-line arguments like `--app-port=51234`, or None."""
    values: dict[str, str] = {}
    for arg in args:
        arg = arg.strip().strip('"')
        if arg.startswith("--") and "=" in arg:
            key, _, value = arg[2:].partition("=")
            values[key] = value.strip('"')
    port, token = values.get("app-port", ""), values.get("remoting-auth-token", "")
    if not port.isdigit() or not token:
        return None
    return LcuCredentials(port=int(port), token=token, source="process")


def from_lockfile(path: Path) -> LcuCredentials | None:
    """Credentials from the lockfile, or None if it's missing, malformed, or left by a crash."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None
    parsed = parse_lockfile(text)
    if parsed is None:
        return None
    pid, credentials = parsed
    if not psutil.pid_exists(pid):  # stale lockfile: the client crashed or was killed
        return None
    return credentials


def parse_lockfile(text: str) -> tuple[int, LcuCredentials] | None:
    """Parse `LeagueClient:<pid>:<port>:<password>:https` into (pid, credentials)."""
    parts = text.strip().split(":")
    if len(parts) != 5 or parts[4] != "https":
        return None
    _, pid, port, token, _ = parts
    if not pid.isdigit() or not port.isdigit() or not token:
        return None
    return int(pid), LcuCredentials(port=int(port), token=token, source="lockfile")


def ssl_context() -> ssl.SSLContext:
    """TLS settings for the client: trust only Riot's root certificate, check the hostname.

    One check is relaxed (docs/LCU.md section 1): Python 3.13's strict mode, which rejects the
    client's certificate ("Missing Authority Key Identifier": it names its issuer the old way).
    The chain to riotgames.pem and the hostname 127.0.0.1 are still verified.
    """
    context = ssl.create_default_context(cafile=str(CERT_PATH))
    context.verify_flags &= ~ssl.VERIFY_X509_STRICT
    return context
