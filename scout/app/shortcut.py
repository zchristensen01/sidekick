"""Desktop and Start-menu shortcuts to a developer copy of Sidekick (M14).

The installed app's shortcuts come from its installer (packaging/sidekick.iss). A developer
copy's are named "Sidekick (developer)" so they never replace those. Made with Windows' own
shortcut maker (WScript.Shell, through PowerShell), so no extra packages. The shortcut opens
the `sidekick` launcher that pip puts next to Python (.venv/Scripts/sidekick.exe).
"""

import ctypes
import os
import subprocess
import sys
from pathlib import Path

from scout.paths import frozen

ICON = Path(__file__).with_name("sidekick.ico")
NAME = "Sidekick.lnk" if frozen() else "Sidekick (developer).lnk"
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
DESKTOP, PROGRAMS = 0x10, 0x02  # CSIDL_DESKTOPDIRECTORY, CSIDL_PROGRAMS (the Start menu)
SCRIPT = """
$shell = New-Object -ComObject WScript.Shell
foreach ($link in $env:SK_LINKS.Split('|')) {
  $s = $shell.CreateShortcut($link)
  $s.TargetPath = $env:SK_TARGET
  $s.WorkingDirectory = $env:SK_WORKDIR
  $s.IconLocation = $env:SK_ICON
  $s.Description = 'Sidekick: pre-game scouting for League of Legends'
  $s.Save()
}
"""


class ShortcutError(Exception):
    pass


def folder(csidl: int) -> Path | None:
    """A Windows special folder (follows OneDrive's moved Desktop); None off Windows."""
    if sys.platform != "win32":
        return None
    buffer = ctypes.create_unicode_buffer(260)
    if ctypes.windll.shell32.SHGetFolderPathW(None, csidl, None, 0, buffer) != 0:
        return None
    return Path(buffer.value)


def links() -> list[Path]:
    return [f / NAME for f in (folder(DESKTOP), folder(PROGRAMS)) if f is not None]


def launcher() -> Path | None:
    """The `sidekick` launcher pip made (next to this Python), if it exists."""
    found = Path(sys.executable).with_name("sidekick.exe")
    return found if found.exists() else None


def exists() -> bool:
    return any(link.exists() for link in links())


def create(workdir: Path) -> list[Path]:
    """Make (or update) both shortcuts. Raises ShortcutError with a plain reason."""
    target = launcher()
    if target is None:
        raise ShortcutError("No sidekick.exe next to Python yet: run tools/dev_setup.ps1, "
                            "then try again.")  # fmt: skip
    made = links()
    if not made:
        raise ShortcutError("Shortcuts only work on Windows.")
    env = dict(os.environ, SK_LINKS="|".join(str(p) for p in made), SK_TARGET=str(target),
               SK_WORKDIR=str(workdir), SK_ICON=f"{ICON},0")  # fmt: skip
    try:
        done = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
             "-Command", SCRIPT],
            env=env, capture_output=True, text=True, timeout=60, creationflags=NO_WINDOW,
        )  # fmt: skip
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ShortcutError(f"PowerShell didn't run: {exc}") from None
    if done.returncode != 0:
        raise ShortcutError((done.stderr or done.stdout).strip()[-400:] or "PowerShell failed")
    return [p for p in made if p.exists()]
