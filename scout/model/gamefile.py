"""Load a hand-written game (tests/fixtures/games/<name>.yaml) as a GameState.

Used by `scout report --file` and the golden tests. Format: tests/fixtures/README.md.
Mistakes get a message that says how to fix them (e.g. "Wukong" -> "MonkeyKing").
"""

import difflib
from collections.abc import Collection
from pathlib import Path
from typing import Any

import yaml

from scout.model.game import GameState, Pick
from scout.model.roles import Queue, Role


class GameFileError(ValueError):
    """The game file is invalid; the message names the file and the problem."""


def load_game(path: Path, known_champions: Collection[str] = ()) -> GameState:
    """Parse and check a game file. `known_champions` (Data Dragon ids) enables the id check."""
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise GameFileError(f"{path}: can't read it: {exc}") from None
    if not isinstance(raw, dict):
        raise GameFileError(f"{path}: must be a YAML mapping (see tests/fixtures/README.md)")
    problems: list[str] = []

    if raw.get("name") != path.stem:
        problems.append(f"name must match the file name ({path.stem!r})")
    version = str(raw.get("ddragon_version") or "")
    if not version:
        problems.append('ddragon_version is missing (e.g. "16.19.1")')
    queue = _enum(Queue, raw.get("queue"), "queue", problems)
    my_role = _enum(Role, raw.get("my_role"), "my_role", problems)
    teams = {side: _team(raw.get(side), side, known_champions, problems)
             for side in ("ally", "enemy")}  # fmt: skip

    turns = raw.get("pick_turns") or {}
    if not isinstance(turns, dict) or not all(isinstance(t, int) for t in turns.values()):
        problems.append("pick_turns must map champion ids to draft turn numbers")
        turns = {}
    picked = {c for team in teams.values() for c in team.values()}
    problems += [f"pick_turns names {c}, who isn't in this game" for c in turns if c not in picked]

    confidence: dict[Role, float] = {}
    for role_name, value in (raw.get("enemy_role_confidence") or {}).items():
        role = _enum(Role, role_name, "enemy_role_confidence", problems)
        if not isinstance(value, int | float) or not 0 <= value <= 1:
            problems.append(f"enemy_role_confidence.{role_name} must be between 0 and 1")
        elif role is not None:
            confidence[role] = float(value)

    side = str(raw.get("side") or "").lower()
    if side not in ("", "blue", "red"):
        problems.append(f"side must be blue or red (got {side!r})")
    spells_raw = raw.get("spells") or {}
    lists = isinstance(spells_raw, dict) and all(isinstance(v, list) for v in spells_raw.values())
    if not lists:
        problems.append("spells must map champion ids to lists, e.g. Sivir: [flash, heal]")
        spells_raw = {}
    problems += [f"spells names {c}, who isn't in this game" for c in spells_raw if c not in picked]
    spells = {c: tuple(str(s).lower() for s in v) for c, v in spells_raw.items()}

    if problems:
        raise GameFileError(f"{path}:\n  " + "\n  ".join(problems))
    assert queue is not None and my_role is not None  # problems would have been raised

    def picks(team: str) -> dict[Role, Pick]:
        return {
            role: Pick(champ, role, confidence.get(role, 1.0) if team == "enemy" else 1.0,
                       turns.get(champ), spells.get(champ, ()))
            for role, champ in teams[team].items()
        }  # fmt: skip

    return GameState(
        ddragon_version=version,
        queue=queue,
        my_role=my_role,
        ally=picks("ally"),
        enemy=picks("enemy"),
        side=side,
        notes=[str(n) for n in raw.get("notes") or []],
        bans=[str(b) for b in raw.get("bans") or []],
    )


def _enum(kind: Any, value: Any, field: str, problems: list[str]) -> Any:
    try:
        return kind(str(value).strip().lower())
    except ValueError:
        choices = ", ".join(member.value for member in kind)
        problems.append(f"{field} must be one of: {choices} (got {value!r})")
        return None


def _team(value: Any, side: str, known: Collection[str], problems: list[str]) -> dict[Role, str]:
    if not isinstance(value, dict):
        problems.append(f"{side} must map each role to a champion id")
        return {}
    team: dict[Role, str] = {}
    for role_name, champ in value.items():
        role = _enum(Role, role_name, f"{side} role", problems)
        if role is None:
            continue
        champ = str(champ)
        if known and champ not in known:
            close = difflib.get_close_matches(champ, list(known), n=1)
            hint = f"; did you mean {close[0]}?" if close else ""
            problems.append(f"{side}.{role.value}: unknown champion id {champ!r}{hint}")
        team[role] = champ
    missing = [r.value for r in Role if r not in team]
    if missing:
        problems.append(f"{side} is missing roles: {', '.join(missing)}")
    return team
