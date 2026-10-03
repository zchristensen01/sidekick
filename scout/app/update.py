"""The app's Update button (M14, M24): a new version, and the restart into it.

The installed app (built by GitHub, DECISIONS #114) updates from GitHub Releases:
1. `check_release` reads the newest release's `latest.json` (version, what changed, the
   installer's address and its SHA-256 fingerprint). Nothing changes.
2. `download_release` saves the installer to data/cache/updates and checks the fingerprint;
   a file that doesn't match is deleted, never run. `write_marker` notes what's coming.
3. `install_release` starts the installer quietly and the app closes. The installer waits for
   Sidekick to close, replaces the program files (your own files are elsewhere: scout/paths.py)
   and opens Sidekick again.
4. On start, the app sees update.json, refreshes the data and says what's new.

A developer copy (the repo) updates with git instead:
1. `check` fetches and counts the commits this copy is missing (`git fetch`, nothing changes).
2. `pull` fast-forwards (`git pull --ff-only`: it refuses rather than merge or overwrite your
   edits) and writes the marker.
3. `hand_off` starts this module as a small hidden helper and the app closes. The helper waits
   for the app to exit (Windows locks the running sidekick.exe, so pip can't replace it while
   it runs), reinstalls only if pyproject.toml changed, and opens the app again.
Run as `python -m scout.app.update --after <pid>` (the helper). Never prompts: git is told
not to ask for a password on a terminal nobody can see.
"""

import argparse
import contextlib
import hashlib
import json
import os
import subprocess
import sys
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx

from scout.paths import Paths, frozen

GIT_TIMEOUT_S = 90
PIP_TIMEOUT_S = 900
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
DETACHED = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(
    subprocess, "CREATE_NEW_PROCESS_GROUP", 0
)
REPO = "zchristensen01/sidekick"
LATEST_URL = f"https://github.com/{REPO}/releases/latest/download/latest.json"
DOWNLOADS = f"https://github.com/{REPO}/releases/download/"  # every installer comes from here
MAX_INSTALLER_BYTES = 400_000_000
HELPER = "sidekick-helper.exe"  # the installed app's hidden command-line twin (packaging/)
INSTALLER_FLAGS = ("/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/SP-")


class UpdateError(Exception):
    """Something stopped the update; nothing was changed unless the message says so."""


@dataclass
class Status:
    behind: int = 0  # versions (installed) or commits (developer copy) this copy doesn't have
    ahead: int = 0  # local commits GitHub doesn't have (a developer's copy)
    commits: list[str] = field(default_factory=list)  # what changed, newest first
    edited: list[str] = field(default_factory=list)  # tracked files with local edits
    branch: str = ""
    error: str = ""
    version: str = ""  # the release on offer (installed app)

    @property
    def available(self) -> bool:
        return self.behind > 0 and not self.error


@dataclass
class Marker:
    """data/cache/update.json: written before the restart, read on start."""

    before: str
    after: str  # a commit (developer copy) or the version being installed
    commits: list[str]
    reinstall: bool  # pyproject.toml changed: dependencies or the app's commands
    at: str = ""
    install_ok: bool | None = None  # set by the helper
    install_log: str = ""


@dataclass(frozen=True)
class Release:
    """One release, as its latest.json describes it (packaging/release.py writes it)."""

    version: str
    installer_url: str
    sha256: str
    notes: list[str]


# ---------------------------------------------------------------- the installed app


def version_key(version: str) -> tuple[int, ...]:
    """'2026.10.4.12' -> (2026, 10, 4, 12); anything else (a developer copy's 'dev') -> ()."""
    parts = version.strip().split(".")
    return tuple(int(p) for p in parts) if all(p.isdigit() for p in parts) else ()


def http_client() -> httpx.Client:
    return httpx.Client(follow_redirects=True, timeout=30,
                        headers={"User-Agent": "Sidekick-updater"})  # fmt: skip


def parse_release(raw: Any) -> Release:
    """A checked Release, or UpdateError saying what's wrong with the file."""
    if not isinstance(raw, dict):
        raise UpdateError("The release information isn't readable.")
    version, url = str(raw.get("version", "")), str(raw.get("installer", ""))
    digest = str(raw.get("sha256", "")).lower()
    if not version_key(version):
        raise UpdateError(f"The release has no usable version ({version or 'none'}).")
    if not url.startswith(DOWNLOADS):
        raise UpdateError("The release's installer isn't on Sidekick's GitHub page; not used.")
    if len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
        raise UpdateError("The release has no installer fingerprint (SHA-256); not used.")
    notes = [str(n) for n in raw.get("notes") or [] if str(n).strip()]
    return Release(version, url, digest, notes)


def latest_release(client: httpx.Client) -> Release:
    try:
        response = client.get(LATEST_URL)
    except httpx.HTTPError as exc:
        raise UpdateError(f"Couldn't reach GitHub ({type(exc).__name__}: no internet?).") from None
    if response.status_code == 404:
        raise UpdateError("No release on GitHub yet.")
    if response.status_code != 200:
        raise UpdateError(f"GitHub answered {response.status_code}; try again later.")
    try:
        return parse_release(response.json())
    except ValueError:
        raise UpdateError("The release information isn't readable.") from None


def check_release(current: str, client: httpx.Client) -> Status:
    """Is there a newer release than `current`? Never changes anything."""
    status = Status()
    try:
        release = latest_release(client)
    except UpdateError as exc:
        status.error = str(exc)
        return status
    if version_key(release.version) > version_key(current):
        status.behind, status.version, status.commits = 1, release.version, release.notes[:20]
    return status


def updates_dir(paths: Paths) -> Path:
    return paths.cache_dir / "updates"


def download_release(paths: Paths, release: Release, client: httpx.Client) -> Path:
    """The installer, saved and checked against its fingerprint. Raises UpdateError."""
    folder = updates_dir(paths)
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / f"SidekickSetup-{release.version}.exe"
    part = target.with_suffix(".part")
    digest, size = hashlib.sha256(), 0
    try:
        with client.stream("GET", release.installer_url, timeout=120) as response:
            if response.status_code != 200:
                raise UpdateError(f"GitHub answered {response.status_code} for the installer.")
            with part.open("wb") as f:
                for chunk in response.iter_bytes():
                    size += len(chunk)
                    if size > MAX_INSTALLER_BYTES:
                        raise UpdateError("The installer is far bigger than expected; stopped.")
                    digest.update(chunk)
                    f.write(chunk)
    except httpx.HTTPError as exc:
        part.unlink(missing_ok=True)
        raise UpdateError(f"The download stopped ({type(exc).__name__}); try again.") from None
    except UpdateError:
        part.unlink(missing_ok=True)
        raise
    if digest.hexdigest() != release.sha256:
        part.unlink(missing_ok=True)
        raise UpdateError("The downloaded installer doesn't match its published fingerprint, so "
                          "it was deleted and nothing changed. Try again later.")  # fmt: skip
    part.replace(target)
    return target


def install_release(installer: Path) -> None:
    """Start the installer quietly; the caller closes the app right after."""
    subprocess.Popen([str(installer), *INSTALLER_FLAGS], creationflags=DETACHED, close_fds=True)


def release_marker(current: str, release: Release) -> Marker:
    return Marker(current, release.version, release.notes[:20], reinstall=False,
                  at=datetime.now().astimezone().isoformat(timespec="seconds"))  # fmt: skip


# ---------------------------------------------------------------- a developer copy (git)


def git(root: Path, *args: str, timeout: float = GIT_TIMEOUT_S) -> str:
    env = dict(os.environ, GIT_TERMINAL_PROMPT="0")
    try:
        done = subprocess.run(
            ["git", *args], cwd=root, capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=timeout, env=env, creationflags=NO_WINDOW,
        )  # fmt: skip
    except FileNotFoundError:
        raise UpdateError("Git isn't installed (or isn't on PATH).") from None
    except subprocess.TimeoutExpired:
        raise UpdateError(f"`git {args[0]}` took too long (no internet?).") from None
    if done.returncode != 0:
        message = (done.stderr or done.stdout).strip()
        raise UpdateError(f"git {args[0]}: {message[-600:] or 'failed'}")
    return done.stdout.strip()


def check(root: Path) -> Status:
    """What's new on GitHub. Fetches; never changes your files."""
    status = Status()
    try:
        status.branch = git(root, "rev-parse", "--abbrev-ref", "HEAD")
        try:
            git(root, "rev-parse", "--abbrev-ref", "@{u}")
        except UpdateError:
            status.error = f"The branch `{status.branch}` doesn't follow one on GitHub."
            return status
        git(root, "fetch", "--quiet")
        counts = git(root, "rev-list", "--left-right", "--count", "HEAD...@{u}").split()
        status.ahead, status.behind = int(counts[0]), int(counts[1])
        if status.behind:
            log = git(root, "log", "--format=%s", "-n", "20", "HEAD..@{u}")
            status.commits = [line for line in log.splitlines() if line]
        edited = git(root, "diff", "--name-only", "HEAD")  # tracked files changed here
        status.edited = [line for line in edited.splitlines() if line.strip()]
    except UpdateError as exc:
        status.error = str(exc)
    return status


def pull(paths: Paths) -> Marker:
    """Fast-forward to GitHub's version and leave a marker for the restart."""
    root = paths.root
    before = git(root, "rev-parse", "HEAD")
    commits = git(root, "log", "--format=%s", "-n", "20", "HEAD..@{u}").splitlines()
    try:
        git(root, "pull", "--ff-only", "--quiet", timeout=GIT_TIMEOUT_S * 2)
    except UpdateError as exc:
        if "overwritten" in str(exc):
            raise UpdateError("The update changes files you've edited here, so nothing was "
                              "changed. Commit or set aside your edits, then update "
                              "again.") from None  # fmt: skip
        if "Not possible to fast-forward" in str(exc) or "diverg" in str(exc):
            raise UpdateError("This copy has its own commits that GitHub doesn't, so it can't "
                              "update by itself (a developer's copy: pull by hand).") from None
        raise
    after = git(root, "rev-parse", "HEAD")
    changed = git(root, "diff", "--name-only", before, after).splitlines()
    marker = Marker(before, after, [c for c in commits if c], "pyproject.toml" in changed,
                    at=datetime.now().astimezone().isoformat(timespec="seconds"))  # fmt: skip
    write_marker(marker_file(paths), marker)
    return marker


# ---------------------------------------------------------------- shared


def refreshed_file(paths: Paths) -> Path:
    """Touched after each data refresh the app runs; the app refreshes again 6 hours later."""
    return paths.cache_dir / "refreshed"


def marker_file(paths: Paths) -> Path:
    return paths.cache_dir / "update.json"


def write_marker(path: Path, marker: Marker) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(asdict(marker), indent=1), encoding="utf-8")


def read_marker(path: Path) -> Marker | None:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        return Marker(**raw)
    except (OSError, ValueError, TypeError):
        return None


def console_python() -> str:
    """python.exe next to the running interpreter (the app runs under pythonw.exe)."""
    exe = Path(sys.executable)
    if exe.name.lower() == "pythonw.exe" and exe.with_name("python.exe").exists():
        return str(exe.with_name("python.exe"))
    return sys.executable


def scout_command(*args: str) -> list[str]:
    """A `scout` command for a hidden child process: the installed app's helper, else Python."""
    if frozen():
        return [str(Path(sys.executable).with_name(HELPER)), *args]
    return [console_python(), "-m", "scout", *args]


def app_command() -> list[str]:
    """How to open the app again: the Sidekick launcher next to Python, else pythonw."""
    exe = Path(sys.executable)
    launcher = exe.with_name("sidekick.exe")
    if launcher.exists():
        return [str(launcher)]
    gui = exe.with_name("pythonw.exe")
    return [str(gui if gui.exists() else exe), "-m", "scout.app.main"]


def hand_off(paths: Paths) -> None:
    """Start the hidden git helper; the caller closes the app right after."""
    subprocess.Popen(
        [console_python(), "-m", "scout.app.update", "--after", str(os.getpid()),
         "--root", str(paths.root), "--home", str(paths.user)],
        cwd=paths.root, creationflags=NO_WINDOW | DETACHED, close_fds=True,
    )  # fmt: skip


# ---------------------------------------------------------------- the git helper process


def _wait_for_exit(pid: int, timeout_s: float = 60.0) -> None:
    import psutil

    with contextlib.suppress(psutil.NoSuchProcess, psutil.TimeoutExpired):
        psutil.Process(pid).wait(timeout=timeout_s)
    time.sleep(0.5)  # let Windows release the launcher's file lock


def finish(paths: Paths, after_pid: int) -> None:
    _wait_for_exit(after_pid)
    path = marker_file(paths)
    marker = read_marker(path)
    if marker is not None and marker.reinstall and marker.install_ok is None:
        try:
            done = subprocess.run(
                [console_python(), "-m", "pip", "install", "--disable-pip-version-check",
                 "-q", "-e", str(paths.root)],
                cwd=paths.root, capture_output=True, text=True, encoding="utf-8",
                errors="replace", timeout=PIP_TIMEOUT_S, creationflags=NO_WINDOW,
            )  # fmt: skip
            marker.install_ok = done.returncode == 0
            marker.install_log = (done.stdout + done.stderr)[-3000:]
        except (OSError, subprocess.TimeoutExpired) as exc:
            marker.install_ok, marker.install_log = False, str(exc)
        write_marker(path, marker)
    subprocess.Popen(app_command(), cwd=paths.root, creationflags=DETACHED, close_fds=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Finish a Sidekick update (used by the app).")
    parser.add_argument("--after", type=int, required=True, help="the app's process id")
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--home", type=Path, default=None)
    args = parser.parse_args()
    home = args.home.resolve() if args.home else None
    finish(Paths(args.root.resolve(), home), args.after)


if __name__ == "__main__":
    main()
