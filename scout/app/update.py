"""The app's Update button (M14): check GitHub for new commits, pull them, restart.

1. `check` fetches and counts the commits this copy is missing (`git fetch`, nothing changes).
2. `pull` fast-forwards (`git pull --ff-only`: it refuses rather than merge or overwrite your
   edits) and writes data/cache/update.json saying what changed.
3. `hand_off` starts this module as a small hidden helper and the app closes. The helper waits
   for the app to exit (Windows locks the running sidekick.exe, so pip can't replace it while
   it runs), reinstalls only if pyproject.toml changed, and opens the app again.
4. On start, the app sees update.json, refreshes the data (`scout refresh`) and says what's new.

Run as `python -m scout.app.update --after <pid>` (the helper). Never prompts: git is told
not to ask for a password on a terminal nobody can see.
"""

import argparse
import contextlib
import json
import os
import subprocess
import sys
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path

from scout.paths import Paths

GIT_TIMEOUT_S = 90
PIP_TIMEOUT_S = 900
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
DETACHED = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(
    subprocess, "CREATE_NEW_PROCESS_GROUP", 0
)


class UpdateError(Exception):
    """Something stopped the update; nothing was changed unless the message says so."""


@dataclass
class Status:
    behind: int = 0  # commits on GitHub this copy doesn't have
    ahead: int = 0  # local commits GitHub doesn't have (a developer's copy)
    commits: list[str] = field(default_factory=list)  # their subjects, newest first
    edited: list[str] = field(default_factory=list)  # tracked files with local edits
    branch: str = ""
    error: str = ""

    @property
    def available(self) -> bool:
        return self.behind > 0 and not self.error


@dataclass
class Marker:
    """data/cache/update.json: written by `pull`, finished by the helper, read on start."""

    before: str
    after: str
    commits: list[str]
    reinstall: bool  # pyproject.toml changed: dependencies or the app's commands
    at: str = ""
    install_ok: bool | None = None  # set by the helper
    install_log: str = ""


def git(root: Path, *args: str, timeout: float = GIT_TIMEOUT_S) -> str:
    env = dict(os.environ, GIT_TERMINAL_PROMPT="0")
    try:
        done = subprocess.run(
            ["git", *args], cwd=root, capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=timeout, env=env, creationflags=NO_WINDOW,
        )  # fmt: skip
    except FileNotFoundError:
        raise UpdateError("Git isn't installed (or isn't on PATH): install Git for Windows, "
                          "then run install.ps1 again.") from None  # fmt: skip
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
                              "changed. Save a copy of your edits (or ask Claude Code to commit "
                              "them), then update again.") from None  # fmt: skip
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


def app_command() -> list[str]:
    """How to open the app again: the installed Sidekick launcher, else pythonw."""
    exe = Path(sys.executable)
    launcher = exe.with_name("sidekick.exe")
    if launcher.exists():
        return [str(launcher)]
    gui = exe.with_name("pythonw.exe")
    return [str(gui if gui.exists() else exe), "-m", "scout.app.main"]


def hand_off(paths: Paths) -> None:
    """Start the hidden helper; the caller closes the app right after."""
    subprocess.Popen(
        [console_python(), "-m", "scout.app.update", "--after", str(os.getpid()),
         "--root", str(paths.root)],
        cwd=paths.root, creationflags=NO_WINDOW | DETACHED, close_fds=True,
    )  # fmt: skip


# ---------------------------------------------------------------- the helper process


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
    args = parser.parse_args()
    finish(Paths(args.root.resolve()), args.after)


if __name__ == "__main__":
    main()
