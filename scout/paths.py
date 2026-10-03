"""Every filesystem location in one place.

Two folders (DECISIONS #113):
- `root`, the program's own files: rules, the shared champion knowledge (data/manual/), the
  writer's prompt, the example settings. The repo folder for a developer copy; inside the
  installed app (`_internal`) for everyone else. Never holds anything personal.
- `home`, this Windows user's files: settings, keys, champion lists, notes, reports,
  recordings, downloaded and measured data. `%LOCALAPPDATA%\\Sidekick` for both the installed
  app and a developer copy, so nothing personal ever sits in the repo folder.

Set SCOUT_HOME to keep everything in one folder instead (tests do), or SIDEKICK_USER_DIR to
move only this user's files.
"""

import os
import sys
from dataclasses import dataclass
from pathlib import Path

PACKAGE_DIR = Path(__file__).resolve().parent
APP_NAME = "Sidekick"


def frozen() -> bool:
    """True when running as the installed app (built with PyInstaller), not from source."""
    return bool(getattr(sys, "frozen", False))


def program_dir() -> Path:
    """The program's own files: the bundle folder when installed, else the repo folder."""
    bundle = getattr(sys, "_MEIPASS", None)
    return Path(bundle).resolve() if frozen() and bundle else PACKAGE_DIR.parent


def user_dir() -> Path:
    """This user's own Sidekick folder (created on first use). SIDEKICK_USER_DIR moves it
    (for trying a build without touching your real files)."""
    moved = os.environ.get("SIDEKICK_USER_DIR")
    if moved:
        return Path(moved).resolve()
    if sys.platform == "win32":
        local = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
        return Path(local) / APP_NAME
    share = os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
    return Path(share) / APP_NAME.lower()


@dataclass(frozen=True)
class Paths:
    root: Path  # the program's own files
    home: Path | None = None  # this user's files; None means the same folder as root

    @classmethod
    def from_env(cls) -> "Paths":
        one = os.environ.get("SCOUT_HOME")
        if one:
            folder = Path(one).resolve()
            return cls(folder, folder)
        return cls(program_dir(), user_dir())

    @property
    def user(self) -> Path:
        """Where this user's files live."""
        return self.home or self.root

    # --- this user's settings, keys and lists
    @property
    def config_file(self) -> Path:
        return self.user / "config.yaml"

    @property
    def env_file(self) -> Path:
        return self.user / ".env"

    @property
    def pool_file(self) -> Path:
        return self.user / "pool.yaml"

    @property
    def pools_dir(self) -> Path:
        """Each League account's champions (scout/accounts.py)."""
        return self.user / "pools"

    @property
    def notes_file(self) -> Path:
        """This user's own matchup notes, shown as "Your notes"."""
        return self.user / "matchup_notes.csv"

    @property
    def recordings_dir(self) -> Path:
        """Scrubbed champ select recordings (`scout record`, the app)."""
        return self.user / "recordings"

    def reports_dir(self, save_dir: str | Path = "reports") -> Path:
        path = Path(save_dir)
        return path if path.is_absolute() else self.user / path

    # --- this user's downloaded and measured data (docs/DATA.md, Storage layout)
    @property
    def generated_dir(self) -> Path:
        return self.user / "data" / "generated"

    @property
    def cache_dir(self) -> Path:
        return self.user / "data" / "cache"

    @property
    def history_dir(self) -> Path:
        return self.user / "data" / "history"

    @property
    def patch_file(self) -> Path:
        return self.generated_dir / "PATCH"

    @property
    def refresh_log(self) -> Path:
        return self.generated_dir / "REFRESH_LOG.md"

    @property
    def review_queue(self) -> Path:
        return self.generated_dir / "review_queue.csv"

    @property
    def stats_db(self) -> Path:
        return self.generated_dir / "stats.sqlite"

    def static_dir(self, ddragon_version: str) -> Path:
        return self.generated_dir / "static" / ddragon_version

    # --- the program's own files
    @property
    def config_example(self) -> Path:
        return self.root / "config.example.yaml"

    @property
    def env_example(self) -> Path:
        return self.root / ".env.example"

    @property
    def manual_dir(self) -> Path:
        """The shared champion knowledge, kept by hand (CLAUDE.md hard rule 4)."""
        return self.root / "data" / "manual"

    @property
    def report_agent_doc(self) -> Path:
        return self.root / "docs" / "REPORT_AGENT.md"

    @property
    def traits_doc(self) -> Path:
        return self.root / "docs" / "TRAITS.md"

    @property
    def rules_file(self) -> Path:
        return PACKAGE_DIR / "rules" / "league_rules.yaml"

    @property
    def build_file(self) -> Path:
        """The installed app's version and commit, written when it was built."""
        return self.root / "build.json"

    # --- a developer copy only (not in the installed app)
    @property
    def research_dir(self) -> Path:
        return self.root / "research"

    @property
    def fixtures_dir(self) -> Path:
        return self.root / "tests" / "fixtures"
