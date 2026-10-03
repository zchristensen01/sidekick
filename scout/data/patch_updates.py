"""Mid-patch updates (hotfixes) from the LoL Wiki's patch page (M21).

Riot's hotfixes between patches don't change Data Dragon's version, so nothing else tells the
app about them. The LoL Wiki's page for each patch (V26.19) lists them after the patch's own
notes, as sections of their own: "Hotfixes" with dated entries ("May 14th Hotfix"), or one-off
sections ("October 2nd Queue Update"). `scout refresh` reads that page's section titles into
data/generated/patch_updates.json. When patch notes research is applied, research/status.csv
records the updates it covered; an update that appears later makes it due again
(scout/research_import.py).
"""

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

from scout.data.fetch import Fetcher, write_atomic
from scout.data.patch import display_patch, short_patch
from scout.data.wiki import API
from scout.paths import Paths

NOT_UPDATES = frozenset({"New Cosmetics", "References", "See Also"})  # every patch page has these


@dataclass
class Updates:
    patch: str  # Data Dragon's short patch, e.g. 16.19
    updates: list[str] = field(default_factory=list)  # e.g. ["October 2nd Queue Update"]
    checked_on: str = ""
    page: str = ""  # the wiki page's address
    note: str = ""  # why there's nothing, when the page couldn't be read


def page_url(version: str) -> str:
    return f"https://wiki.leagueoflegends.com/en-us/V{display_patch(version)}"


def sections_url(version: str) -> str:
    params = {"action": "parse", "page": f"V{display_patch(version)}", "prop": "sections",
              "format": "json"}  # fmt: skip
    return f"{API}?{urlencode(params)}"


def parse_updates(raw: Any) -> list[str]:
    """The update titles on a patch page: each top-level section that isn't the patch's own
    notes ("League of Legends V26.19") or a standard one, or its dated entries if it has some
    ("Hotfixes" -> "May 14th Hotfix")."""
    sections = (raw or {}).get("parse", {}).get("sections", [])
    out: list[str] = []
    parent = ""  # the current top-level update section, if we're in one
    for s in sections:
        level, title = str(s.get("level", "")), str(s.get("line", "")).strip()
        if level == "2":
            parent = ""
            if title and title not in NOT_UPDATES and not title.startswith("League of Legends"):
                parent = title
                out.append(title)
        elif level == "3" and parent:
            if out and out[-1] == parent:
                out.pop()  # the dated entries replace their "Hotfixes" heading
            out.append(title)
    return out


def check(paths: Paths, fetcher: Fetcher, version: str,
          now: datetime | None = None) -> Updates:  # fmt: skip
    """Read the patch page's updates now (never cached) and save them."""
    stamp = (now or datetime.now().astimezone()).date().isoformat()
    found = Updates(short_patch(version), checked_on=stamp, page=page_url(version))
    raw = fetcher.json(sections_url(version))
    if isinstance(raw, dict) and "error" in raw:  # a brand-new patch: no wiki page yet
        found.note = str(raw["error"].get("info") or raw["error"].get("code") or "no page")
    else:
        found.updates = parse_updates(raw)
    write_atomic(file(paths), json.dumps(asdict(found), indent=1))
    return found


def load(paths: Paths) -> Updates | None:
    path = file(paths)
    if not path.exists():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        return Updates(**{k: raw[k] for k in ("patch", "updates", "checked_on", "page", "note")
                          if k in raw})  # fmt: skip
    except (ValueError, TypeError, KeyError):
        return None


def file(paths: Paths) -> Path:
    return paths.generated_dir / "patch_updates.json"
