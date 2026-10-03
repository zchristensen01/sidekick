"""Build the writer input JSON from the selected report (docs/REPORT_AGENT.md, Input contract).

Numbers are already inside the item texts (attack ranges, levels); the writer may only copy
them. `facts` carries every champion's whole kit in Riot's own words (passives included;
cooldowns for the player and their lane opponents), Riot's tips, ratings, mechanics and
measured figures, so the writer can explain a kit without relying on memory. Warnings and
The owner's own notes are rendered by code, not sent, except the role-guess and loading lines
(`enemy_role_notes`) and the off-role "no data" notes.
"""

from typing import Any

from scout.analysis.insights import Insights
from scout.analysis.players import Player
from scout.counterpick import Verdict
from scout.data.patch import display_patch
from scout.data.store import Knowledge
from scout.model.roles import LANE_ROLES, Role, lane_of
from scout.postgame.backtest import track_record
from scout.postgame.claims import claims_from
from scout.report.select import Report

SLOT_NAMES = {"P": "Passive", "Q": "Q", "W": "W", "E": "E", "R": "R"}
# Riot's own words for its 1-3 playstyle ratings, as the client shows them.
RIOT_RATINGS = {"cc": "control", "mobility": "mobility", "durability": "toughness",
                "damage": "damage", "utility": "utility"}  # fmt: skip
RIOT_LEVELS = {0: "none", 1: "low", 2: "moderate", 3: "high"}


def build_input(
    report: Report, insights: Insights, knowledge: Knowledge, max_words: int
) -> dict[str, Any]:
    sections = [
        {
            "key": section.key,
            "title": section.title,
            "always": section.always,
            "items": [
                {"source": item.source, "confidence": item.confidence, "text": item.text,
                 "numbers": list(item.numbers)}
                for item in section.items
            ],
        }
        for section in report.sections
    ]  # fmt: skip
    me = insights.lineup.us.get(report.role)
    # Every champion comes with its whole kit in Riot's words and Riot's tips against the
    # enemies (M17: the writer knows the whole game); my lane opponents (the enemy jungler for
    # a jungler) and I also get cooldowns (2026-10-02 and 2026-10-03).
    lane = lane_of(report.role)
    focus = {p.champ_id for r, p in insights.lineup.them.items()
             if (lane and r in LANE_ROLES[lane]) or (not lane and r is Role.JUNGLE)}  # fmt: skip
    facts = {
        p.name: _facts(p, knowledge, full=p.champ_id in focus or p is me, me=p is me)
        for p in insights.lineup.players()
    }
    role_notes = [w for w in report.warnings if "is a guess" in w or "at loading" in w]
    payload = {
        "patch": display_patch(insights.game.ddragon_version),
        "queue": report.queue,
        "side": report.side,
        "player": {"role": report.role.value, "champion": report.champion},
        "max_words": max_words,
        "game": {
            "ally": {r.value: name for r, name in report.ally.items()},
            "enemy": {r.value: name for r, name in report.enemy.items()},
            "enemy_role_notes": role_notes,
        },
        "sections": sections,
        "facts": facts,
    }
    if insights.counterpick is not None:
        payload["counterpick"] = counterpick_block(insights.counterpick)
    in_game = {c for p in insights.lineup.players() for c in p.classes}
    if knowledge.class_definitions and in_game:
        payload["class_definitions"] = {
            c: {"quote": row["quote"], "source": row["source"]}
            for c, row in knowledge.class_definitions.items() if c in in_game
        }  # fmt: skip
    # M20: how often each of this report's calls came true in past games
    track = track_record(claims_from(insights, [], set()), knowledge) if knowledge.track else []
    if track:
        payload["track_record"] = track
    role = report.role.value
    payload["game_facts"] = [
        {"text": f["text"], "source": f["source"], "patch": f["patch"]}
        for topic in ("objective", "camps", "role_quest")
        for f in knowledge.facts_about(topic, role)
    ]
    return payload


def counterpick_block(v: Verdict) -> dict[str, Any]:
    """docs/COUNTERPICK.md (Output block). Numbers are display strings only."""
    return {
        "opponent": v.opponent.name,
        "opponent_role_confidence": round(v.confidence, 2),
        "picked_after_me": v.picked_after_me,
        "outlook": v.outlook,
        "specific": v.specific,
        "label": v.label,
        "evidence": {
            "source": v.source,
            "display": v.display,
            "delta_display": v.delta_display,
            "blended_previous_patch": v.previous_patch,
        },
        "structural_flags": list(v.flags),
        "alternatives": [
            {"opponent": a.name, "outlook": a.outlook, "display": a.display}
            for a in v.alternatives
        ],
    }


def _facts(player: Player, knowledge: Knowledge, full: bool = False,
           me: bool = False) -> dict[str, Any]:  # fmt: skip
    abilities = {}
    for row in knowledge.abilities.get(player.champ_id, ()):
        entry = {"name": row["name"], "description": row["description"]}
        if full and row["cooldowns"]:
            entry["cooldowns"] = row["cooldowns"].replace("|", "/") + " s"
        abilities[SLOT_NAMES.get(row["slot"], row["slot"])] = entry
    champ = knowledge.facts(player.champ_id)
    return {
        "side": "ally" if player.side == "us" else "enemy",
        "role": player.role.value,
        "class": sorted(player.classes),
        "range": player.range,
        "attack_range": round(player.attack_range) if player.attack_range else None,
        "riot_ratings": {RIOT_RATINGS[k]: RIOT_LEVELS.get(v, str(v)) for k, v in champ.ratings
                         if k in RIOT_RATINGS},
        "wiki_mechanics": sorted(champ.mechanics),
        "game_length_data": player.scaling_note or None,
        **({"measured": {"source": player.measured_source, "figures": list(player.measured),
                         "changed_since_last_patch": list(player.measured_changes)}}
           if player.measured else {}),
        "notes_are": "reviewed by the player" if player.reviewed else "drafted, not reviewed",
        **({"off_role": True,
            "no_data": [f"{player.name} is rarely played {player.role.value}: OP.GG has "
                        f"{round((player.role_share or 0) * 100)}% of its games there, so "
                        "there are no numbers or notes for this pick in this role"]}
           if player.off_role else {}),
        "reviewed": player.reviewed,
        "spikes": list(player.spikes),
        "key_note": player.key_note,
        "ult_note": player.ult_note,
        "spike_note": player.spike_note,
        "abilities": abilities,
        **({"riot_tips_against": list(knowledge.tips.get((player.champ_id, "enemy"), ()))}
           if player.side == "them" else {}),
        **({"riot_tips_playing": list(knowledge.tips.get((player.champ_id, "ally"), ()))}
           if me else {}),
        "summoner_spells": sorted(player.spells),
    }  # fmt: skip
