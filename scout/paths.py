"""Every filesystem location in one place.

The repo root is the folder above the `scout` package (the app is installed with
`pip install -e .`). Set the SCOUT_HOME environment variable to point somewhere else.
"""

import os
from dataclasses import dataclass
from pathlib import Path

PACKAGE_DIR = Path(__file__).resolve().parent


@dataclass(frozen=True)
class Paths:
    root: Path

    @classmethod
    def from_env(cls) -> "Paths":
        home = os.environ.get("SCOUT_HOME")
        return cls(Path(home).resolve() if home else PACKAGE_DIR.parent)

    # --- config and secrets
    @property
    def config_file(self) -> Path:
        return self.root / "config.yaml"

    @property
    def config_example(self) -> Path:
        return self.root / "config.example.yaml"

    @property
    def env_file(self) -> Path:
        return self.root / ".env"

    @property
    def env_example(self) -> Path:
        return self.root / ".env.example"

    @property
    def pool_file(self) -> Path:
        return self.root / "pool.yaml"

    @property
    def pools_dir(self) -> Path:
        """Each League account's champions (scout/accounts.py)."""
        return self.root / "pools"

    # --- data (docs/DATA.md, Storage layout)
    @property
    def data_dir(self) -> Path:
        return self.root / "data"

    @property
    def manual_dir(self) -> Path:
        return self.data_dir / "manual"

    @property
    def generated_dir(self) -> Path:
        return self.data_dir / "generated"

    @property
    def cache_dir(self) -> Path:
        return self.data_dir / "cache"

    @property
    def history_dir(self) -> Path:
        return self.data_dir / "history"

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

    # --- docs, rules, reports, fixtures
    @property
    def report_agent_doc(self) -> Path:
        return self.root / "docs" / "REPORT_AGENT.md"

    @property
    def rules_file(self) -> Path:
        return PACKAGE_DIR / "rules" / "league_rules.yaml"

    @property
    def fixtures_dir(self) -> Path:
        return self.root / "tests" / "fixtures"

    def reports_dir(self, save_dir: str | Path = "reports") -> Path:
        path = Path(save_dir)
        return path if path.is_absolute() else self.root / path
