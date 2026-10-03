"""What a report predicted, saved as checkable claims next to it (M10).

The final report (at the loading screen) saves `reports/<report>.json`: the draft, the client's
game id (to find the match later, no player lookup needed) and one claim per prediction that
the match timeline can check (docs/TASKS.md M10; the outside review's grading table):

| kind | predicted | checked against (scout/postgame/grade.py) |
|---|---|---|
| lane_winner | us, them or even, per lane | gold difference at 15 minutes |
| priority | us or them: who pushes early | where our laners stood, minutes 3-10 |
| volatility | high or low | kills and deaths in that lane before 14:00 |
| gank_lane | our jungler's best first gank | the first kill our jungler joins before 10:00 |
| jungle_start | top or bot side | our jungler's position at 2:00 |
| threat | the enemy most likely to get fed | their gold share and kills at 15 |
| scaling | which team the long game favors | game length and the winner |

No player identifiers are saved: champions and roles only.
"""

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from scout.analysis.insights import Insights
from scout.analysis.lanes import VOLATILE_AT
from scout.model.game import GameState
from scout.model.roles import Lane
from scout.rules.engine import Fired

VERSION = 1
SCALING_AT = 0.4  # the game plan's own threshold for "one team scales better" (select.py)


@dataclass(frozen=True)
class Claim:
    id: str
    kind: str
    predicted: str
    lane: str | None = None
    subject: str = ""  # a champion id (threat)
    inputs: dict[str, Any] = field(default_factory=dict)  # the numbers behind it, for tuning
    rules: tuple[str, ...] = ()  # shown rules about the same lane


@dataclass
class Saved:
    """One report's claims file."""

    path: Path
    game_id: int | None
    patch: str
    queue: str
    my_role: str
    my_champion: str
    ally: dict[str, str]
    enemy: dict[str, str]
    claims: list[Claim]
    created_at: str
    graded_at: str = ""


def claims_from(ins: Insights, fired: list[Fired], shown: set[str]) -> list[Claim]:
    out = []
    for lane in Lane:
        state = ins.lanes[lane]
        if not state.us.players or not state.them.players:
            continue
        rules = tuple(sorted({f.id for f in fired if f.lane is lane and f.id in shown}))
        inputs = {"prio": state.prio, "fight": state.fight, "diff": state.diff,
                  "volatility": state.volatility, "label": state.label,
                  "source": state.source}  # fmt: skip
        verdict = {"winning": "us", "losing": "them", "even": "even"}.get(state.verdict)
        if verdict:
            out.append(Claim(f"{lane.value}:winner", "lane_winner", verdict, lane.value,
                             inputs=inputs, rules=rules))  # fmt: skip
        if state.prio in ("us", "them"):
            out.append(Claim(f"{lane.value}:priority", "priority", state.prio, lane.value,
                             inputs=inputs, rules=rules))  # fmt: skip
        if state.volatility is not None:
            level = "high" if state.volatility >= VOLATILE_AT else "low"
            out.append(Claim(f"{lane.value}:volatility", "volatility", level, lane.value,
                             inputs=inputs, rules=rules))  # fmt: skip
    if ins.jungle.our_first_gank is not None:
        out.append(Claim("jungle:first_gank", "gank_lane", ins.jungle.our_first_gank.value))
    if ins.path.start_side in ("top", "bot"):
        out.append(Claim("jungle:start", "jungle_start", ins.path.start_side))
    if ins.threats:
        top = ins.threats[0]
        out.append(Claim(f"threat:{top.player.champ_id}", "threat", "fed",
                         subject=top.player.champ_id,
                         inputs={"score": top.score, "reasons": top.reasons}))  # fmt: skip
    us, them = ins.teams["us"].scaling, ins.teams["them"].scaling
    if us is not None and them is not None and abs(us - them) >= SCALING_AT:
        out.append(Claim("team:scaling", "scaling", "us" if us > them else "them",
                         inputs={"us": us, "them": them}))  # fmt: skip
    return out


def save(path: Path, game: GameState, game_id: int | None, claims: list[Claim],
         created_at: str) -> None:  # fmt: skip
    data = {
        "version": VERSION, "game_id": game_id, "patch": game.ddragon_version,
        "queue": game.queue.value, "my_role": game.my_role.value,
        "my_champion": game.ally[game.my_role].champ_id if game.my_role in game.ally else "",
        "ally": {r.value: p.champ_id for r, p in game.ally.items()},
        "enemy": {r.value: p.champ_id for r, p in game.enemy.items()},
        "created_at": created_at, "graded_at": "",
        "claims": [asdict(c) for c in claims],
    }  # fmt: skip
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=1), encoding="utf-8")


def load(path: Path) -> Saved:
    raw = json.loads(path.read_text(encoding="utf-8"))
    claims = [Claim(c["id"], c["kind"], c["predicted"], c.get("lane"), c.get("subject", ""),
                    c.get("inputs") or {}, tuple(c.get("rules") or ()))
              for c in raw.get("claims", [])]  # fmt: skip
    return Saved(path, raw.get("game_id"), raw.get("patch", ""), raw.get("queue", ""),
                 raw.get("my_role", ""), raw.get("my_champion", ""), raw.get("ally", {}),
                 raw.get("enemy", {}), claims, raw.get("created_at", ""),
                 raw.get("graded_at", ""))  # fmt: skip


def mark_graded(path: Path, when: str) -> None:
    raw = json.loads(path.read_text(encoding="utf-8"))
    raw["graded_at"] = when
    path.write_text(json.dumps(raw, indent=1), encoding="utf-8")
