"""Turn a champ select session into a GameState.

Queue gate, my team by localPlayerCellId (which changes on pick-order swaps), champions from
the team arrays, pick turns from completed `pick` actions matched by champion, final
assignedPosition, the ally Smite role-swap check, enemy roles via
scout/analysis/role_inference.py, unknown champion keys as placeholders. Step by step:
docs/LCU.md section 4 and docs/ROLES.md (Enemy roles and pick order).
"""

import dataclasses
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from scout.analysis.role_inference import RoleRates, infer_roles
from scout.model.game import GameState, Pick
from scout.model.roles import Role, has_positions, queue_from_id, queue_label, role_from_lcu


class NotReportable(Exception):
    """This champ select doesn't get a report (wrong queue, no position). Message says why."""


@dataclass(frozen=True)
class ChampionIndex:
    """What parsing needs from the static data (data/generated/static/<version>/)."""

    version: str
    by_key: Mapping[int, str]  # LCU championId -> Data Dragon id
    smite_key: int | None  # summoner spell key for Smite, from summoner_spells.csv
    spell_names: Mapping[int, str] = field(default_factory=dict)  # key -> "ignite" (lowercase)

    @classmethod
    def from_static(cls, version: str, tables: Mapping[str, Sequence[Mapping[str, str]]]):
        smite = next(
            (int(r["key"]) for r in tables.get("summoner_spells.csv", []) if r["name"] == "Smite"),
            None,
        )
        by_key = {int(r["key"]): r["champ_id"] for r in tables.get("champions.csv", [])}
        spells = {int(r["key"]): r["name"].lower() for r in tables.get("summoner_spells.csv", [])}
        return cls(version=version, by_key=by_key, smite_key=smite, spell_names=spells)

    def spells(self, *keys: Any) -> tuple[str, ...]:
        """Spell names for summoner spell keys; unknown and empty (0) keys are skipped."""
        return tuple(self.spell_names[k] for k in keys if k in self.spell_names)

    def champ_id(self, key: int, notes: list[str]) -> str:
        """Data Dragon id for a client key; a placeholder (and a note) for unknown keys."""
        if key in self.by_key:
            return self.by_key[key]
        notes.append(f"Unknown champion id {key}: probably new; Refresh data (Settings) adds it.")
        return f"Unknown{key}"


def pick_turns(actions: Any) -> dict[int, int]:
    """Champion key -> index of the draft turn it was locked in (completed `pick` actions).

    `actions` is a list of turns, each a list of actions. Other action types are ignored.
    """
    turns: dict[int, int] = {}
    for index, turn in enumerate(actions if isinstance(actions, list) else []):
        for action in turn if isinstance(turn, list) else []:
            if not isinstance(action, dict):
                continue
            champ = action.get("championId") or 0
            if action.get("type") == "pick" and action.get("completed") and champ:
                turns.setdefault(champ, index)
    return turns


def banned_keys(actions: Any) -> list[int]:
    return [
        action["championId"]
        for turn in (actions if isinstance(actions, list) else [])
        for action in (turn if isinstance(turn, list) else [])
        if isinstance(action, dict) and action.get("type") == "ban"
        and action.get("completed") and (action.get("championId") or 0) > 0  # -1: no ban
    ]  # fmt: skip


def parse_session(
    session: Mapping[str, Any],
    index: ChampionIndex,
    role_rates: RoleRates,
    queue_id: int | None = None,
) -> GameState:
    """GameState for a draft-queue champ select. Raises NotReportable for anything else.

    Works mid-draft too: only locked champions are included.
    """
    qid = queue_id if queue_id is not None else session.get("queueId")
    queue = queue_from_id(qid if isinstance(qid, int) else -1)
    if not has_positions(queue):
        label = queue_label(qid if isinstance(qid, int) else None)
        raise NotReportable(f"{label} isn't a draft or ranked game; no report.")

    notes: list[str] = []
    turns = pick_turns(session.get("actions"))
    locked = set(turns)
    my_cell = session.get("localPlayerCellId")
    my_team = [p for p in session.get("myTeam") or [] if isinstance(p, dict)]
    their_team = [p for p in session.get("theirTeam") or [] if isinstance(p, dict)]

    me = next((p for p in my_team if p.get("cellId") == my_cell), None)
    my_role = role_from_lcu(str((me or {}).get("assignedPosition") or ""))
    if me is None or my_role is None:
        raise NotReportable("Couldn't find your assigned position in champ select.")

    # Allies: role from assignedPosition, Smite swap check, champion once locked.
    ally_roles: dict[int, Role] = {}
    for player in my_team:
        role = role_from_lcu(str(player.get("assignedPosition") or ""))
        if role is not None:
            ally_roles[player.get("cellId")] = role
    swapped = _smite_swap(my_team, ally_roles, index, notes)
    my_role = ally_roles.get(my_cell, my_role)

    ally: dict[Role, Pick] = {}
    for player in my_team:
        key = player.get("championId") or 0
        role = ally_roles.get(player.get("cellId"))
        if key in locked and role is not None:
            spells = index.spells(player.get("spell1Id"), player.get("spell2Id"))
            ally[role] = Pick(index.champ_id(key, notes), role, 1.0, turns.get(key), spells)
    if swapped:
        notes.append(swapped)

    # Enemies: only locked champions; roles guessed.
    enemy_keys = [p["championId"] for p in their_team if (p.get("championId") or 0) in locked]
    enemy_ids = [index.champ_id(key, notes) for key in enemy_keys]
    guess = infer_roles(enemy_ids, role_rates)
    turn_of = dict(zip(enemy_ids, (turns.get(k) for k in enemy_keys), strict=True))
    enemy = {
        role: Pick(champ, role, round(guess.confidence(role), 3), turn_of[champ])
        for role, champ in guess.best.items()
    }

    bans = [index.champ_id(key, notes) for key in banned_keys(session.get("actions"))]
    notes[:] = list(dict.fromkeys(notes))  # an unknown champion is mentioned once
    # LCU team 1 is blue side, team 2 red: confirmed against Riot's match data (ranked games
    # recorded as team 2 are teamId 200, red, in Match-V5), and blue picks first.
    side = {1: "blue", 2: "red"}.get((me or {}).get("team"), "")
    return GameState(
        side=side,
        ddragon_version=index.version,
        queue=queue,
        my_role=my_role,
        ally=ally,
        enemy=enemy,
        enemy_role_alternatives=guess.alternatives,
        notes=notes,
        bans=bans,
        enemy_role_odds=guess.by_role,
    )


def _smite_swap(
    my_team: list[dict[str, Any]],
    ally_roles: dict[Any, Role],
    index: ChampionIndex,
    notes: list[str],
) -> str:
    """If a non-jungle ally has Smite and the assigned jungler doesn't, swap their roles.

    Returns the note to show ("" if nothing changed). Ally spells are visible in champ select.
    """
    if index.smite_key is None:
        return ""

    def has_smite(player: dict[str, Any]) -> bool:
        return index.smite_key in (player.get("spell1Id"), player.get("spell2Id"))

    jungler = next((p for p in my_team if ally_roles.get(p.get("cellId")) == Role.JUNGLE), None)
    smiters = [p for p in my_team if has_smite(p) and p is not jungler]
    if jungler is None or has_smite(jungler) or len(smiters) != 1:
        return ""
    other = smiters[0]
    other_role = ally_roles[other.get("cellId")]
    ally_roles[other.get("cellId")], ally_roles[jungler.get("cellId")] = Role.JUNGLE, other_role
    champ_key = other.get("championId") or 0
    name = index.by_key.get(champ_key, "an ally") if champ_key else "an ally"
    return (
        f"Role swap: {name} (assigned {other_role.value}) has Smite, so they're treated as the "
        f"jungler and the assigned jungler as {other_role.value}."
    )


def confirmed_roles(
    roster: Mapping[str, Any] | None, champ_keys: Sequence[int], smite_key: int | None
) -> dict[int, Role]:
    """Roles the game shows at loading for these champions (the recorder's `game_start`).

    Uses positions when the client fills them in; otherwise only the Smite holder is known
    (as the jungler). Champions it can't place are left out.
    """
    if not roster:
        return {}
    wanted = set(champ_keys)
    roles: dict[int, Role] = {}
    for team in ("teamOne", "teamTwo"):
        for player in roster.get(team) or []:
            key = player.get("championId")
            role = role_from_lcu(str(player.get("selectedPosition") or ""))
            if key in wanted and role is not None:
                roles[key] = role
    if smite_key is not None:
        for entry in roster.get("spells") or []:
            key = entry.get("championId")
            if key in wanted and smite_key in (entry.get("spell1Id"), entry.get("spell2Id")):
                roles.setdefault(key, Role.JUNGLE)
    return roles


def apply_spells(game: GameState, roster: Mapping[str, Any], index: ChampionIndex) -> GameState:
    """Everyone's summoner spells from the loading-screen roster (enemy spells are hidden in
    champ select)."""
    by_champ = {}
    for entry in roster.get("spells") or []:
        if isinstance(entry, dict) and entry.get("championId") in index.by_key:
            spells = index.spells(entry.get("spell1Id"), entry.get("spell2Id"))
            by_champ[index.by_key[entry["championId"]]] = spells
    if not by_champ:
        return game

    def update(team: dict[Role, Pick]) -> dict[Role, Pick]:
        return {r: dataclasses.replace(p, spells=by_champ.get(p.champ_id, p.spells))
                for r, p in team.items()}  # fmt: skip

    return dataclasses.replace(game, ally=update(game.ally), enemy=update(game.enemy))


def apply_confirmed_roles(
    game: GameState, confirmed: Mapping[str, Role], role_rates: RoleRates
) -> tuple[GameState, list[tuple[str, Role | None, Role]]]:
    """Fix the enemy roles the loading screen confirmed and re-guess the rest.

    `confirmed` maps champion ids to roles (from `confirmed_roles`). Returns the updated game
    and the changes as (champ_id, guessed role or None, confirmed role).
    """
    guessed = {p.champ_id: role for role, p in game.enemy.items()}
    turns = {p.champ_id: p.pick_turn for p in game.enemy.values()}
    fixed: dict[str, Role] = {}
    for champ, role in confirmed.items():
        if champ in guessed and role not in fixed.values():
            fixed[champ] = role
    if not fixed:
        return game, []
    rest = [c for c in guessed if c not in fixed]
    guess = infer_roles(rest, role_rates, [r for r in Role if r not in fixed.values()])
    spells = {p.champ_id: p.spells for p in game.enemy.values()}
    enemy = {role: Pick(champ, role, 1.0, turns[champ], spells[champ])
             for champ, role in fixed.items()}  # fmt: skip
    for role, champ in guess.best.items():
        enemy[role] = Pick(champ, role, round(guess.confidence(role), 3), turns[champ],
                           spells[champ])  # fmt: skip
    odds = {role: [(champ, 1.0)] for champ, role in fixed.items()} | guess.by_role
    changes = [(champ, guessed.get(champ), role) for champ, role in fixed.items()]
    updated = dataclasses.replace(
        game, enemy=dict(sorted(enemy.items(), key=lambda item: list(Role).index(item[0]))),
        enemy_role_odds=odds,
    )  # fmt: skip
    return updated, changes
