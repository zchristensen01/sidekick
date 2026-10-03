"""After the game: check a report's claims against the match (M10).

The claims file (`reports/<report>.json`, scout/postgame/claims.py) has the client's game id;
Match-V5's id is the platform plus that number (`NA1_5123456789`), so the match is fetched
without looking anyone up. Results go to data/history/ (scout/postgame/history.py).

The game itself is kept too, for a later "how did it go against the plan" review
(docs/MATCH_DATA.md, Your own games): `reports/<report>.review.json`, next to the report and its
History screen, on this PC only. It holds every player's figures (champions and roles, no
names), what happened from our side, and each claim's result.
"""

import contextlib
import json
from collections.abc import Sequence
from datetime import datetime
from pathlib import Path
from typing import Any, Protocol

from scout.data.fetch import write_atomic
from scout.data.measure import measure
from scout.data.store import Knowledge
from scout.model.roles import Role
from scout.postgame import claims as claim_files
from scout.postgame import history
from scout.postgame.grade import MatchError, Result, grade, outcome, read_match
from scout.report.past import VIEW_SUFFIX

REVIEW_SUFFIX = ".review.json"
REVIEW_VERSION = 1

KIND_WORDS = {"lane_winner": "lane winner", "priority": "who pushes early",
              "volatility": "early kills", "gank_lane": "first gank lane",
              "jungle_start": "jungle start", "threat": "fed threat",
              "scaling": "long game"}  # fmt: skip


class Matches(Protocol):
    def match(self, match_id: str) -> dict[str, Any]: ...
    def timeline(self, match_id: str) -> dict[str, Any]: ...


def match_id(platform: str, game_id: int) -> str:
    return f"{platform.upper()}_{game_id}"


def check(saved: claim_files.Saved, riot: Matches, knowledge: Knowledge,
          platform: str) -> list[Result]:  # fmt: skip
    """Grade one report. Raises MatchError when the match isn't there (yet)."""
    if not saved.game_id:
        raise MatchError("this report has no game id (made before M10, or a custom game)")
    found = match_id(platform, int(saved.game_id))
    match = riot.match(found)
    if not match.get("info"):
        raise MatchError("Riot hasn't published this match yet (it can take a few minutes)")
    timeline = riot.timeline(found)
    me = knowledge.facts(saved.my_champion)
    m = read_match(match, timeline, me.key, Role(saved.my_role))
    results = grade(saved.claims, m)
    with contextlib.suppress(OSError):  # the check itself still counts
        save_review(saved, match, timeline, knowledge, outcome(m), results)
    return results


def review_path(claims_path: Path) -> Path:
    return claims_path.with_name(claims_path.stem + REVIEW_SUFFIX)


def save_review(saved: claim_files.Saved, match: dict[str, Any], timeline: dict[str, Any],
                knowledge: Knowledge, ours: dict[str, Any],
                results: Sequence[Result]) -> Path:  # fmt: skip
    """The game as it went, next to its report, for the later review against the plan."""
    by_key = {f.key: c for c, f in knowledge.champions.items()}
    players = measure(match, timeline, by_key, frozenset())  # (first item: not needed here)
    mine = next((p for p in players if p.champ_id == saved.my_champion
                 and p.role.value == saved.my_role), None)  # fmt: skip
    data = {
        "version": REVIEW_VERSION, "report": saved.path.stem, "patch": saved.patch,
        "my_role": saved.my_role, "my_champion": saved.my_champion,
        "lane_opponent": mine.opp if mine else "",
        "players": [{"side": "us" if mine and p.team == mine.team else "them",
                     "role": p.role.value, "champion": p.champ_id, "opponent": p.opp,
                     "figures": p.figures} for p in players],
        "outcome": ours,
        "claims": [{"id": r.claim.id, "kind": r.claim.kind, "lane": r.claim.lane,
                    "predicted": r.claim.predicted, "actual": r.actual, "hit": r.hit,
                    "measure": r.measure} for r in results],
    }  # fmt: skip
    path = review_path(saved.path)
    write_atomic(path, json.dumps(data, indent=1))
    return path


def record(folder: Path, saved: claim_files.Saved, results: Sequence[Result],
           now: datetime) -> None:  # fmt: skip
    when = now.isoformat(timespec="seconds")
    history.append(folder, saved, results, when)
    history.rebuild_accuracy(folder)
    claim_files.mark_graded(saved.path, when)


def summary(results: Sequence[Result]) -> list[str]:
    graded = [r for r in results if r.hit is not None]
    hits = sum(1 for r in graded if r.hit)
    head = f"Post-game check: {hits} of {len(graded)} predictions held"
    skipped = len(results) - len(graded)
    head += f" ({skipped} couldn't be checked in this game)." if skipped else "."
    lines = [head]
    for r in results:
        mark = "-" if r.hit is None else ("held" if r.hit else "missed")
        where = f"{r.claim.lane} " if r.claim.lane else ""
        what = KIND_WORDS.get(r.claim.kind, r.claim.kind)
        subject = f" ({r.claim.subject})" if r.claim.subject else ""
        lines.append(f"  {mark:6s} {where}{what}{subject}: predicted {r.claim.predicted}, "
                     f"actual {r.actual or '-'} ({r.measure})")  # fmt: skip
    return lines


def pending(reports_dir: Path) -> list[Path]:
    """Claims files not graded yet, newest first."""
    found = []
    for path in sorted(reports_dir.glob("*.json"), reverse=True):
        if path.name.endswith((VIEW_SUFFIX, REVIEW_SUFFIX)):
            continue  # a saved screen for History (M23) or a game kept for review, not claims
        try:
            saved = claim_files.load(path)
        except (OSError, ValueError, KeyError):
            continue
        if not saved.graded_at and saved.claims:
            found.append(path)
    return found
