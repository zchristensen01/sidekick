"""Which Sidekick this is (M24): the installed app's version, from build.json.

The release build writes build.json next to the program's files (packaging/build.py); a
developer copy has none and is "dev" (its commit comes from git).
"""

import json
from dataclasses import dataclass

from scout.paths import Paths


@dataclass(frozen=True)
class Build:
    version: str  # "2026.10.4.12" when installed; "dev" for a developer copy
    commit: str = ""  # the commit it was built from (short)
    built: str = ""  # the build date, YYYY-MM-DD


def current_build(paths: Paths) -> Build:
    try:
        raw = json.loads(paths.build_file.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return Build("dev")
    if not isinstance(raw, dict):
        return Build("dev")
    return Build(str(raw.get("version") or "dev"), str(raw.get("commit") or ""),
                 str(raw.get("built") or ""))  # fmt: skip
