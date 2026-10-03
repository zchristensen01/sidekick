"""What the dashboard window shows (M13): one plain, JSON-ready dict per screen.

Screens: `status` (waiting for the client or a game, picks locked, writing the report, game
running, game ended), `picks` (champ select before I lock: pick options and the draft),
`report` (the one report, at the loading screen, shown once the LLM has written it). The page
(scout/app/dashboard.html) only draws these. Nothing here decides anything about League: it
reshapes the report, the insights and Riot's text.
"""

from collections.abc import Sequence
from typing import Any

from scout.analysis.insights import Insights
from scout.analysis.lanes import PHASE_LABEL, PHASES
from scout.model.game import GameState
from scout.model.roles import LANE_ROLES, Lane, Role, lane_of
from scout.picks import Suggestions, option_text
from scout.report.select import Report
from scout.report.validator import Written

LABELS = {"bully": "Bully lane", "push_edge": "You push", "shove_respect": "Shove and respect",
          "bait": "Bait lane", "pushed": "Pushed in", "survive": "Survive"}  # fmt: skip
VERDICTS = {"winning": "You win early", "losing": "They win early", "even": "Even early",
            "unknown": "Unknown"}  # fmt: skip
OUTLOOKS = {"favorable": "Favored", "even": "Even", "soft_counter": "Slight disadvantage",
            "hard_counter": "Hard matchup", "unknown": "No numbers"}  # fmt: skip
# Sections the page draws in its own cards; the rest go in the generic list, in report order.
OWN_CARDS = frozenset({"your_lane", "opponent", "counterpick", "game_plan", "lanes_in_trouble"})


def status_view(state: str, message: str, title: str = "") -> dict[str, Any]:
    """state: waiting_client | waiting_game | champ_select | in_game | ended, or the app's
    own: setup (downloading or updating) | problem (with a way into Settings)."""
    view = {"screen": "status", "state": state, "message": message}
    if title:
        view["title"] = title
    return view


def picks_view(s: Suggestions, game: GameState, names: dict[str, str]) -> dict[str, Any]:
    return {
        "screen": "picks",
        "role": s.role.value,
        "opponent": s.opponent,
        "opponent_confidence": round(s.opponent_confidence, 2),
        "options": [
            {
                "name": o.name,
                "outlook": o.outlook,
                "outlook_text": OUTLOOKS.get(o.outlook, ""),
                "rate": round(o.rate * 100) if o.rate is not None else None,
                "own": round(o.own * 100) if o.own is not None else None,
                "blind": list(o.blind) if o.blind else None,
                "source": o.candidate.source,
                "id": o.candidate.champ,
                "stars": o.candidate.stars,
                "main": o.candidate.source == "pool" and o.candidate.comfort == 0,
                "reason": o.reason,
                "synergy": o.synergy_text,
                "text": option_text(o, s.opponent, s.role),
            }
            for o in s.options
        ],
        "note": s.note,
        "draft": _draft(game, names),
    }


def report_view(
    report: Report,
    ins: Insights,
    written: Written | None = None,
    phase: str = "final",
    addendum: Sequence[str] = (),
    players: Sequence[dict[str, Any]] = (),
) -> dict[str, Any]:
    """phase: final (the loading-screen report; there's no draft read since 2026-10-03).
    `players`: PlayerCard.view() dicts once the loading-screen records are in (M16)."""
    role = report.role
    lane = lane_of(role)
    lines = _section_lines(report, written)
    plan = lines.get("game_plan", [])
    view: dict[str, Any] = {
        "screen": "report",
        "phase": phase,
        "written": written is not None,
        "header": {
            "role": role.value, "champion": report.champion, "patch": report.patch,
            "champion_id": me.champ_id if (me := ins.game.ally.get(role)) else "",
            "ally_ids": {r.value: p.champ_id for r, p in ins.game.ally.items()},
            "enemy_ids": {r.value: p.champ_id for r, p in ins.game.enemy.items()},
            "queue": report.queue.replace("_", " "), "side": report.side,
            "ally": {r.value: n for r, n in report.ally.items()},
            "enemy": {r.value: n for r, n in report.enemy.items()},
        },  # fmt: skip
        "plan": plan[0] if plan else "",
        "plan_more": plan[1:],
        "lane": _lane_card(ins, lane, lines.get("your_lane", [])) if lane else None,
        "lanes": _lanes(ins, lines.get("lanes_in_trouble", [])) if role is Role.JUNGLE else None,
        "opponents": _opponents(ins, role),
        "counterpick": _counterpick(ins, lines.get("counterpick", [])),
        "team": _team(ins),
        "sections": [
            {"key": s.key, "title": s.title, "items": lines.get(s.key, [])}
            for s in report.sections if s.key not in OWN_CARDS
        ],  # fmt: skip
        "warnings": list(report.warnings),
        "notes": list(report.your_notes),
        "addendum": list(addendum),
        "players": list(players),
        "kits": _kits(ins),
    }
    return view


def _section_lines(report: Report, written: Written | None) -> dict[str, list[str]]:
    rules = {s.key: [i.text for i in s.items] for s in report.sections}
    if written is None:
        return rules
    by_key = {s.key: [line.text for line in s.lines] for s in written.sections}
    return {key: by_key.get(key, items) for key, items in rules.items()}


def _lane_card(ins: Insights, lane: Lane, items: list[str]) -> dict[str, Any]:
    state, timeline = ins.lanes[lane], ins.timelines[lane]
    push = (state.us.push or 0) - (state.them.push or 0) if state.us.push is not None else None
    return {
        "lane": lane.value,
        "us": state.us.names, "them": state.them.names,
        "label": state.label, "label_text": LABELS.get(state.label, ""),
        "verdict": state.verdict, "verdict_text": VERDICTS.get(state.verdict, ""),
        "source": state.source,
        "prio": state.prio, "push_diff": round(push, 2) if push is not None else None,
        "fight": state.fight, "fight_diff": state.diff,
        "volatility": state.volatility,
        "phases": [{"key": p, "label": PHASE_LABEL[p], "side": timeline.phases.get(p, "unknown")}
                   for p in PHASES],
        "items": items,
    }  # fmt: skip


def _lanes(ins: Insights, items: list[str]) -> dict[str, Any]:
    rows = []
    for lane in Lane:
        state, gank = ins.lanes[lane], ins.ganks[lane]
        rows.append({
            "lane": lane.value, "us": state.us.names, "them": state.them.names,
            "us_ids": _lane_ids(ins.game.ally, lane), "them_ids": _lane_ids(ins.game.enemy, lane),
            "verdict": state.verdict, "verdict_text": VERDICTS.get(state.verdict, ""),
            "label_text": LABELS.get(state.label, ""),
            "volatile": (state.volatility or 0) >= 4.0,
            "gank_rank": gank.our_rank, "threat": gank.threat,
            "plan": ins.plans[lane].kind,
        })  # fmt: skip
    path = ins.path
    return {
        "rows": rows,
        "items": items,
        "route": {"start": path.start_side, "target": path.target.value if path.target else None,
                  "counter": path.counter.value if path.counter else None},  # fmt: skip
    }


def _opponents(ins: Insights, role: Role) -> list[dict[str, Any]]:
    """My lane opponents (the enemy jungler for a jungler): Riot's passive text and tips."""
    knowledge = ins.knowledge
    lane = lane_of(role)
    roles = LANE_ROLES[lane] if lane else (Role.JUNGLE,)
    out = []
    for r in roles:
        p = ins.lineup.them.get(r)
        if p is None:
            continue
        passive = None
        tips: tuple[str, ...] = ()
        if knowledge is not None:
            passive = next((a for a in knowledge.abilities.get(p.champ_id, ())
                            if a["slot"] == "P"), None)  # fmt: skip
            tips = knowledge.tips.get((p.champ_id, "enemy"), ())
        out.append({
            "id": p.champ_id, "name": p.name, "role": r.value, "classes": sorted(p.classes),
            "range": p.range, "attack_range": round(p.attack_range) if p.attack_range else None,
            "spells": sorted(p.spells),
            "passive": ({"name": passive["name"], "text": passive["description"]}
                        if passive else None),
            "tips": list(tips[:2]),
            "kit": [{"slot": a["slot"], "name": a["name"], "text": first_sentence(a["description"])}
                    for a in (knowledge.abilities.get(p.champ_id, ()) if knowledge else ())
                    if a["slot"] != "P"],
        })  # fmt: skip
    return out


def first_sentence(text: str) -> str:
    """Riot's text up to its first full stop (shortened, never reworded)."""
    cut = text.find(". ")
    return text if cut < 0 else text[: cut + 1]


RIOT_LEVELS = {0: "none", 1: "low", 2: "moderate", 3: "high"}
RIOT_WORDS = (("cc", "Control"), ("mobility", "Mobility"), ("durability", "Toughness"),
              ("damage", "Damage"), ("utility", "Utility"))  # fmt: skip


def _kits(ins: Insights) -> list[dict[str, Any]]:
    """All ten champions in Riot's and the wiki's words, for the Both teams panel (M17)."""
    knowledge = ins.knowledge
    if knowledge is None:
        return []
    out = []
    for p in ins.lineup.players():
        facts = knowledge.facts(p.champ_id)
        ratings = dict(facts.ratings)
        rows = knowledge.abilities.get(p.champ_id, ())
        tips = knowledge.tips.get((p.champ_id, "enemy" if p.side == "them" else "ally"), ())
        out.append({
            "side": p.side, "role": p.role.value, "id": p.champ_id, "name": p.name,
            "classes": sorted(p.classes), "range": p.range,
            "ratings": [{"name": word, "level": RIOT_LEVELS.get(ratings[key], "")}
                        for key, word in RIOT_WORDS if key in ratings],
            "mechanics": sorted(facts.mechanics),
            "abilities": [{"slot": a["slot"], "name": a["name"], "text": a["description"]}
                          for a in rows],
            "tips": list(tips),
            "tips_kind": "against" if p.side == "them" else "playing",
            "measured": list(p.measured), "measured_source": p.measured_source,
            "measured_changes": list(p.measured_changes),
            "off_role": p.off_role,
        })  # fmt: skip
    return out


def _counterpick(ins: Insights, items: list[str]) -> dict[str, Any] | None:
    v = ins.counterpick
    if v is None:
        return None
    return {
        "label": v.label, "outlook": v.outlook, "outlook_text": OUTLOOKS.get(v.outlook, ""),
        "rate": round(v.p_hat * 100) if v.p_hat is not None else None,
        "display": v.display, "items": items,
        "build": list(ins.stats.builds.get(ins.game.my_role, ())),
    }  # fmt: skip


def _team(ins: Insights) -> dict[str, Any]:
    out = {}
    for side, profile in ins.teams.items():
        out[side] = {
            "physical": profile.damage.get("physical", 0), "magic": profile.damage.get("magic", 0),
            "mixed": profile.damage.get("mixed", 0), "engagers": profile.n_engagers,
            "frontline": profile.n_frontline, "hard_cc": profile.n_hard_cc,
        }  # fmt: skip
    return out


def _draft(game: GameState, names: dict[str, str]) -> dict[str, Any]:
    def side(team: dict[Role, Any], enemy: bool) -> list[dict[str, Any]]:
        out = []
        for r in Role:
            p = team.get(r)
            name = names.get(p.champ_id, p.champ_id) if p else None
            confidence = round(p.role_confidence, 2) if p and enemy else None
            out.append({"role": r.value, "id": p.champ_id if p else None, "name": name,
                        "confidence": confidence})  # fmt: skip
        return out

    return {"ally": side(game.ally, False), "enemy": side(game.enemy, True),
            "bans": [names.get(b, b) for b in game.bans], "ban_ids": list(game.bans),
            "me": game.my_role.value}  # fmt: skip


def _lane_ids(team: dict[Role, Any], lane: Lane) -> list[str]:
    return [team[r].champ_id for r in LANE_ROLES[lane] if r in team]
