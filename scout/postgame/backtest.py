"""Backtesting every read (M20): how often Sidekick's predictions came true in real games.

For each game the collector stored (draft and outcomes, no ids), from each side's point of view
(as that side's jungler, so every lane and the jungle get claims): run the whole analysis on the
draft, make the same claims a final report saves (scout/postgame/claims.py), and grade them
against what happened (scout/postgame/grade.py). The tally is per claim kind, per kind and lane
label, per predicted value, and per rule (a lane rule counts its lane's claims).

Each line is compared with a baseline: always guessing the most common outcome for that kind.
A read is only useful when it beats that ("lift"); the report can then show its track record.

Caveat: the measured figures include these same games, so reads built on them look a little
better here than they will on new games (M20's fitting step holds games out).
"""

from collections import Counter, defaultdict
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from scout.analysis.insights import analyze
from scout.analysis.stats import NO_STATS, GameStats
from scout.counterpick import DEFAULT_BANDS, Bands
from scout.data.store import Knowledge, TrackRecord, read_csv, write_csv
from scout.model.game import GameState, Pick
from scout.model.roles import Queue, Role
from scout.postgame.claims import Claim, claims_from
from scout.postgame.grade import GOLD_BAND, LANE_MINUTE, VOLATILE_KILLS, grade_outcome
from scout.report.select import select
from scout.rules.engine import Rule, evaluate

MIN_SHOWN = 30  # a line needs this many graded claims before its rate is worth reading
REPORT_MIN = 100  # graded calls before a call's record reaches the writer (about +-5 points)


@dataclass
class Line:
    claims: int = 0
    graded: int = 0
    hits: int = 0
    actual: Counter[str] = field(default_factory=Counter)  # what really happened

    @property
    def rate(self) -> float | None:
        return self.hits / self.graded if self.graded else None

    @property
    def baseline(self) -> float | None:
        """Hit rate of always guessing the most common outcome."""
        if not self.graded:
            return None
        return max(self.actual.values()) / self.graded


@dataclass
class Tally:
    games: int = 0
    sides: int = 0
    lines: dict[tuple[str, str], Line] = field(default_factory=lambda: defaultdict(Line))

    def add(self, what: str, name: str, hit: bool | None, actual: str) -> None:
        line = self.lines[(what, name)]
        line.claims += 1
        if hit is not None:
            line.graded += 1
            line.hits += hit
            line.actual[actual] += 1

    def rows(self) -> list[dict[str, str]]:
        out = []
        for (what, name), line in sorted(self.lines.items()):
            rate, base = line.rate, line.baseline
            out.append({
                "what": what, "name": name, "claims": str(line.claims),
                "graded": str(line.graded), "hits": str(line.hits),
                "hit_rate": f"{rate:.3f}" if rate is not None else "",
                "baseline": f"{base:.3f}" if base is not None else "",
                "lift": f"{rate - base:+.3f}" if rate is not None and base is not None else "",
            })  # fmt: skip
        return out


COLUMNS = ("what", "name", "claims", "graded", "hits", "hit_rate", "baseline", "lift")


def game_from(record: Mapping[str, Any], side: str) -> GameState:
    """The draft as one side saw it, from that side's jungler (every lane gets claims)."""
    other = "200" if side == "100" else "100"
    sides = record["sides"]

    def team(draft: Mapping[str, str]) -> dict[Role, Pick]:
        return {Role(r): Pick(c, Role(r)) for r, c in draft.items()}

    version = ".".join(str(record.get("version") or "").split(".")[:2]) + ".1"
    return GameState(ddragon_version=version, queue=Queue.RANKED_SOLO, my_role=Role.JUNGLE,
                     ally=team(sides[side]["draft"]), enemy=team(sides[other]["draft"]),
                     side="blue" if side == "100" else "red")  # fmt: skip


def run(records: Iterable[Mapping[str, Any]], knowledge: Knowledge, rules: list[Rule],
        stats_for: Callable[[GameState], GameStats] | None = None,
        bands: Bands = DEFAULT_BANDS) -> Tally:  # fmt: skip
    tally = Tally()
    for record in records:
        sides = record.get("sides") or {}
        if set(sides) != {"100", "200"}:
            continue
        tally.games += 1
        for side in ("100", "200"):
            game = game_from(record, side)
            if any(p.champ_id not in knowledge.champions
                   for p in (*game.ally.values(), *game.enemy.values())):  # fmt: skip
                continue  # a champion newer than the static data
            tally.sides += 1
            ins = analyze(game, knowledge, stats_for(game) if stats_for else NO_STATS, bands)
            fired = evaluate(rules, ins)
            report = select(ins, fired)
            shown = {i.source for s in report.sections for i in s.items}
            for result in grade_outcome(claims_from(ins, fired, shown), sides[side]["outcome"]):
                c = result.claim
                tally.add("kind", c.kind, result.hit, result.actual)
                tally.add("predicted", f"{c.kind}={c.predicted}", result.hit, result.actual)
                if c.lane:
                    tally.add("call", f"{c.lane} {c.kind}={c.predicted}", result.hit,
                              result.actual)  # fmt: skip
                label = c.inputs.get("label")
                if label:
                    tally.add("label", f"{c.kind}:{label}", result.hit, result.actual)
                based = c.inputs.get("source")  # a lane read: OP.GG's numbers or traits only
                if based:
                    tally.add("based_on", f"{c.kind}:{based}", result.hit, result.actual)
                for rule in c.rules:
                    tally.add("rule", f"{rule} ({c.kind})", result.hit, result.actual)
    return tally


def save(path: Path, tally: Tally) -> None:
    """data/history/backtest.csv: one row per line of the tally (rebuilt on every run)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    write_csv(path, COLUMNS, tally.rows())


def load_track(path: Path) -> dict[str, TrackRecord]:
    """Each call's record from backtest.csv: "lane_winner=us" (every lane) and "bot
    lane_winner=us" (one lane). Empty before the first backtest."""
    out = {}
    for row in read_csv(path):
        if row.get("what") in ("predicted", "call") and row.get("graded") and row.get("baseline"):
            out[row["name"]] = TrackRecord(int(row["graded"]), int(row["hits"]),
                                           float(row["baseline"]))  # fmt: skip
    return out


def track_record(claims: Iterable[Claim], knowledge: Knowledge,
                 min_graded: int = REPORT_MIN) -> list[dict[str, str]]:  # fmt: skip
    """For the writer: each call this report makes, with how often the same call came true in
    past games and how often the usual result happened anyway. Only calls with min_graded+."""
    out = []
    for c in claims:
        call = f"{c.kind}={c.predicted}"
        found = knowledge.track.get(f"{c.lane} {call}") if c.lane else None
        if found is None or found.graded < min_graded:
            found = knowledge.track.get(call)
        if found is None or found.graded < min_graded:
            continue
        right = found.hits / found.graded
        out.append({"call": call_words(c, knowledge), "right": f"{right:.0%}",
                    "usual_result": f"{found.usual:.0%}", "games": f"{found.graded:,}",
                    "beats_usual": "yes" if right > found.usual else "no"})  # fmt: skip
    return out


def call_words(c: Claim, knowledge: Knowledge) -> str:
    """A claim in plain words, by the grader's own measure (scout/postgame/grade.py)."""
    lane = f"{c.lane} lane" if c.lane else ""
    team = "your team" if c.predicted == "us" else "their team"
    if c.kind == "lane_winner":
        if c.predicted == "even":
            return f"{lane} even: within {GOLD_BAND} gold at {LANE_MINUTE}:00"
        return f"{lane} won by {team}: {GOLD_BAND}+ gold ahead at {LANE_MINUTE}:00"
    if c.kind == "priority":
        return f"{lane}: {team} has the wave, minutes 3-10"
    if c.kind == "volatility":
        return f"{lane} kills and deaths before 14:00: {c.predicted} ({VOLATILE_KILLS}+ is high)"
    if c.kind == "gank_lane":
        return f"your jungler's first kill before 10:00 is in {c.predicted} lane"
    if c.kind == "jungle_start":
        return f"your jungler starts on the {c.predicted} side"
    if c.kind == "threat":
        return f"{knowledge.facts(c.subject).name} gets fed"
    if c.kind == "scaling":
        return f"the long game favors {team}"
    return f"{c.kind}: {c.predicted}"


def summary(tally: Tally, min_graded: int = MIN_SHOWN) -> list[str]:
    """Plain lines: each kind of read, then the rules and labels furthest above or below
    their baseline (only lines with enough graded claims)."""
    out = [f"{tally.games} games, {tally.sides} drafts (each side's) checked."]
    for (what, name), line in sorted(tally.lines.items()):
        if what in ("kind", "based_on") and line.graded:
            name = name.replace(":", " from ") if what == "based_on" else name
            out.append(f"  {name}: right {line.hits} of {line.graded} ({line.rate:.0%}); "
                       f"always guessing the usual outcome: {line.baseline:.0%}")  # fmt: skip
    ranked = [(line.rate - line.baseline, what, name, line)
              for (what, name), line in tally.lines.items()
              if what in ("rule", "label") and line.graded >= min_graded]  # fmt: skip
    ranked.sort(key=lambda x: x[0])
    if ranked:
        out.append(f"Rules and lane labels with {min_graded}+ graded claims:")
        for lift, _, name, line in ranked[-5:][::-1]:
            if lift > 0:
                out.append(f"  best  {name}: {line.rate:.0%} vs {line.baseline:.0%} "
                           f"({lift:+.0%}, {line.graded})")  # fmt: skip
        for lift, _, name, line in ranked[:5]:
            if lift < 0:
                out.append(f"  worst {name}: {line.rate:.0%} vs {line.baseline:.0%} "
                           f"({lift:+.0%}, {line.graded})")  # fmt: skip
    return out
