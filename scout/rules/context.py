"""Build the context for each rule scope from the insights, plus the schema of allowed paths.

The schema lives here, next to the builders, so the two can't drift: every path a builder
fills is in the schema, and the rules file may only use schema paths. docs/RULES.md (Scopes,
default audience, and context paths).
"""

from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any

from scout.analysis.insights import Insights
from scout.analysis.lanes import PHASE_LABEL, PHASES, SideView
from scout.analysis.players import Player
from scout.analysis.roam import reaching
from scout.analysis.stats import lane_advantage
from scout.analysis.team import FRONTLINE_AT
from scout.model.roles import LANE_ROLES, Lane, Role

CHAMP_FIELDS = (
    "early", "engage", "cc", "escape", "scaling", "roam", "waveclear", "frontline", "spikes",
    "tags", "style", "range", "attack_range", "move_speed", "range_varies", "classes",
    "damage_type", "reviewed", "spells",
)  # fmt: skip
SIDE_FIELDS = (
    "early", "scaling", "engage", "cc", "roam", "waveclear", "frontline", "escape", "range",
    "tags", "classes", "power", "attack_range", "range_varies", "spells",
)  # fmt: skip
CLASSES = (
    "juggernaut", "diver", "skirmisher", "assassin", "burst", "battlemage", "artillery",
    "catcher", "enchanter", "vanguard", "warden", "marksman", "specialist",
)  # fmt: skip
ROLE_KEYS = {Role.TOP: "top", Role.JUNGLE: "jg", Role.MID: "mid", Role.BOT: "bot",
             Role.SUPPORT: "support"}  # fmt: skip
TEAM_FIELDS = (
    "early", "scaling", "n_engagers", "n_frontline", "n_hard_cc", "archetype",
    "damage.physical", "damage.magic", "damage.mixed", "n_dive_threats",
    *(f"n_{c}" for c in CLASSES),
)  # fmt: skip
STATS_LANE = ("stats.matchup_wr", "stats.matchup_games", "stats.matchup_delta",
              "stats.lane_advantage")  # fmt: skip

SCHEMA: dict[str, frozenset[str]] = {
    "lane": frozenset(
        [f"{side}.{f}" for side in ("us", "them") for f in SIDE_FIELDS]
        + [f"{side}.{role}.{f}" for side in ("us", "them") for role in ("bot", "support")
           for f in CHAMP_FIELDS]
        + ["state.verdict", "state.diff", "state.volatility", "state.range_mismatch",
           "state.prio", "state.fight", "state.label",
           "state.source", "state.range_gap", "gank.on_them", "gank.on_us", "gank.our_rank",
           "gank.their_rank",
           "threat", "plan.kind", "plan.phase", "reach.them_count", "reach.us_count",
           "my_lane"]
        + [f"timeline.{p}" for p in PHASES] + list(STATS_LANE)
    ),
    "map": frozenset(
        [f"{side}.{key}.{f}" for side in ("us", "them") for key in ROLE_KEYS.values()
         for f in CHAMP_FIELDS]
        + ["jg_diff", "invade_risk", "priority.side", "priority.them_side", "gank_rank.us",
           "gank_rank.us_score", "gank_rank.them", "my_lane", "them_divers",
           "roam_target.us.mid", "roam_target.us.mid_gank", "path.start_side", "path.target",
           "path.counter"]
        + [f"skirmish.{lane.value}" for lane in Lane]
        + [f"priority.{lane.value}" for lane in Lane]
        + [f"lanes.{lane.value}.{f}" for lane in Lane
           for f in ("state.verdict", "state.diff", "state.volatility", "gank.on_them",
                     "gank.on_us", "threat", "plan.kind")]
        + [f"roam.{side}.{role}" for side in ("us", "them") for role in ("mid", "support")]
    ),
    "team": frozenset(
        [f"{side}.team.{f}" for side in ("us", "them") for f in TEAM_FIELDS]
        + ["early_diff", "scaling_diff"]
    ),
    "champ": frozenset([f"them.{f}" for f in (*CHAMP_FIELDS, "role", "feed_rank", "confidence")]),
    "ally": frozenset([f"us.{f}" for f in (*CHAMP_FIELDS, "role")] + ["team.n_frontline_others"]),
    "pair": frozenset([f"{x}.{f}" for x in ("a", "b") for f in (*CHAMP_FIELDS, "role")]
                      + ["team", "stats.synergy_wr", "stats.synergy_games"]),
    "counterpick": frozenset(
        ["outlook", "specific", "label", "picked_after_me", "p_hat", "games", "source",
         "me.role"]
        + [f"{who}.{f}" for who in ("me", "opp") for f in CHAMP_FIELDS]
    ),
}  # fmt: skip

PLACEHOLDERS: dict[str, frozenset[str]] = {
    "lane": frozenset(
        {
            "lane",
            "us",
            "them",
            "phase",
            "plan_why",
            "reach_them",
            "reach_us",
            "us_range",
            "them_range",
            "range_gap",
        }
    ),
    "map": frozenset(
        {
            "us_jg",
            "them_jg",
            "gank_lane",
            "their_gank_lane",
            "prio_side",
            "us_mid",
            "us_support",
            "them_mid",
            "them_support",
            "dive_threat",
            "mid_roam_lane",
            *(f"{lane.value}_fight_{side}" for lane in Lane for side in ("us", "them")),
        }
    ),
    "team": frozenset(),
    "champ": frozenset({"name", "role", "scaling_data"}),
    "ally": frozenset({"name", "role"}),
    "pair": frozenset({"team", "a", "b"}),
    "counterpick": frozenset({"me", "opp"}),
}


@dataclass(frozen=True)
class Context:
    """One evaluation of one scope: the values rules test, and the text placeholders."""

    scope: str
    values: dict[str, Any]
    fill: dict[str, str]
    lane: Lane | None = None
    subject: str = ""  # champion name for champ/ally scope, "A + B" for pairs
    subject_role: Role | None = None  # the champion's own role (ally scope)
    extra: dict[str, Any] = field(default_factory=dict)


def contexts(ins: Insights) -> Iterator[Context]:
    """Every context for a game: 3 lanes, the map, the team, each champion, each pair."""
    my_lane = _lane_of(ins.game.my_role)
    for lane in Lane:
        yield _lane(ins, lane, my_lane)
    yield _map(ins, my_lane)
    yield _team(ins)
    feed_rank = {t.player.champ_id: rank for rank, t in enumerate(ins.threats, 1)}
    for p in ins.lineup.them.values():
        values = {f"them.{k}": v for k, v in _champ(p).items()}
        values.update({"them.role": p.role.value, "them.feed_rank": feed_rank.get(p.champ_id),
                       "them.confidence": p.confidence})  # fmt: skip
        data = f" ({p.scaling_note})" if p.scaling_note else ""
        yield Context("champ", values, {"name": p.name, "role": p.role.value, "scaling_data": data},
                      subject=p.name, subject_role=p.role)  # fmt: skip
    for p in ins.lineup.us.values():
        values = {f"us.{k}": v for k, v in _champ(p).items()} | {"us.role": p.role.value}
        values["team.n_frontline_others"] = sum(
            1 for o in ins.lineup.us.values() if o is not p and (o.frontline or 0) >= FRONTLINE_AT
        )
        yield Context("ally", values, {"name": p.name, "role": p.role.value}, subject=p.name,
                      subject_role=p.role)  # fmt: skip
    if ins.counterpick is not None:
        yield _counterpick(ins)
    for side in ("us", "them"):
        team = list(ins.lineup.side(side).values())
        for a in team:
            for b in team:
                if a is b:
                    continue
                values = ({f"a.{k}": v for k, v in _champ(a).items()}
                          | {f"b.{k}": v for k, v in _champ(b).items()}
                          | {"a.role": a.role.value, "b.role": b.role.value, "team": side}
                          | _pair_stats(ins, side, a, b))  # fmt: skip
                fill = {"team": "Your" if side == "us" else "Enemy", "a": a.name, "b": b.name}
                yield Context("pair", values, fill, subject=f"{a.name} + {b.name}")


def _counterpick(ins: Insights) -> Context:
    v = ins.counterpick
    assert v is not None
    values = {
        "outlook": v.outlook, "specific": v.specific, "label": v.label,
        "picked_after_me": v.picked_after_me, "source": v.source,
        "p_hat": round(v.p_hat * 100, 1) if v.p_hat is not None else None, "games": v.games,
        "me.role": ins.game.my_role.value,
        **{f"me.{k}": x for k, x in _champ(v.me).items()},
        **{f"opp.{k}": x for k, x in _champ(v.opponent).items()},
    }  # fmt: skip
    # No subject: every counter-pick line is about the same opponent, and the section should
    # keep the verdict plus how to play it, not one line per champion.
    return Context("counterpick", values, {"me": v.me.name, "opp": v.opponent.name},
                   subject_role=ins.game.my_role)  # fmt: skip


def _lane_of(role: Role) -> Lane | None:
    return next((lane for lane, roles in LANE_ROLES.items() if role in roles), None)


def _champ(p: Player) -> dict[str, Any]:
    return {
        "early": p.early, "engage": p.engage, "cc": p.cc, "escape": p.escape,
        "scaling": p.scaling, "roam": p.roam, "waveclear": p.waveclear,
        "frontline": p.frontline, "spikes": p.spikes if p.has_traits else None,
        "tags": p.tags if p.has_traits else None, "style": p.style if p.has_traits else None,
        "range": p.range, "attack_range": p.attack_range, "move_speed": p.move_speed,
        "range_varies": p.range_varies, "classes": p.classes or None,
        "damage_type": p.damage_type,
        "reviewed": p.reviewed,
        "spells": p.spells or None,  # None until known, so spell rules can't fire on a guess
    }  # fmt: skip


def _side(prefix: str, side: SideView) -> dict[str, Any]:
    has_players = bool(side.players)
    return {
        f"{prefix}.early": side.early, f"{prefix}.scaling": side.scaling,
        f"{prefix}.engage": side.engage, f"{prefix}.cc": side.cc, f"{prefix}.roam": side.roam,
        f"{prefix}.waveclear": side.waveclear, f"{prefix}.frontline": side.frontline,
        f"{prefix}.escape": side.escape, f"{prefix}.range": side.range,
        f"{prefix}.tags": side.tags if has_players else None,
        f"{prefix}.classes": side.classes if has_players else None,
        f"{prefix}.power": side.power,
        f"{prefix}.attack_range": side.attack_range,
        f"{prefix}.range_varies": side.range_varies if has_players else None,
        f"{prefix}.spells": side.spells or None,
    }  # fmt: skip


def _lane(ins: Insights, lane: Lane, my_lane: Lane | None) -> Context:
    state, timeline = ins.lanes[lane], ins.timelines[lane]
    gank, plan = ins.ganks[lane], ins.plans[lane]
    values: dict[str, Any] = {**_side("us", state.us), **_side("them", state.them)}
    for side_name, side in (("us", ins.lineup.us), ("them", ins.lineup.them)):
        for role, key in ((Role.BOT, "bot"), (Role.SUPPORT, "support")):
            player = side.get(role) if lane is Lane.BOT else None
            for f in CHAMP_FIELDS:
                values[f"{side_name}.{key}.{f}"] = _champ(player)[f] if player else None
    them_reach = reaching(ins.reach, "them", lane)
    us_reach = reaching(ins.reach, "us", lane)
    values.update({
        "state.verdict": state.verdict, "state.diff": state.diff,
        "state.volatility": state.volatility, "state.range_mismatch": state.range_mismatch,
        "state.source": state.source, "state.range_gap": state.range_gap,
        "state.prio": state.prio, "state.fight": state.fight, "state.label": state.label or None,
        "gank.on_them": gank.on_them, "gank.on_us": gank.on_us,
        "gank.our_rank": gank.our_rank, "gank.their_rank": gank.their_rank,
        "threat": gank.threat, "plan.kind": plan.kind, "plan.phase": plan.phase or None,
        "reach.them_count": len(them_reach), "reach.us_count": len(us_reach),
        "my_lane": my_lane.value if my_lane else None,
        **{f"timeline.{p}": timeline.phases[p] for p in PHASES},
        **_lane_stats(ins, lane),
    })  # fmt: skip
    fill = {
        "lane": lane.value.capitalize(), "us": state.us.names or "your lane",
        "them": state.them.names or "their lane", "phase": plan.phase or "early",
        "plan_why": "; ".join(plan.reasons) or "the lane state",
        "reach_them": _names(them_reach), "reach_us": _names(us_reach),
        "us_range": _whole(state.us.attack_range), "them_range": _whole(state.them.attack_range),
        "range_gap": _whole(abs(state.range_gap) if state.range_gap is not None else None),
    }  # fmt: skip
    return Context("lane", values, fill, lane=lane,
                   extra={"phase_label": PHASE_LABEL})  # fmt: skip


def _lane_stats(ins: Insights, lane: Lane) -> dict[str, Any]:
    """OP.GG numbers for the lane's main matchup (the ADCs in bot), when shown (STATS.md)."""
    stat = ins.stats.matchups.get(LANE_ROLES[lane][0])
    if stat is None or not stat.shown:
        return dict.fromkeys(STATS_LANE)
    return {
        "stats.matchup_wr": round(stat.rate * 100, 1),
        "stats.matchup_games": stat.games,
        "stats.matchup_delta": round(stat.delta * 100, 1),
        "stats.lane_advantage": lane_advantage(stat),
    }


def _pair_stats(ins: Insights, side: str, a: Player, b: Player) -> dict[str, Any]:
    duo = ins.stats.duos.get(side)
    if duo is None or not duo.shown or {duo.a, duo.b} != {a.champ_id, b.champ_id}:
        return {"stats.synergy_wr": None, "stats.synergy_games": None}
    return {"stats.synergy_wr": round(duo.rate * 100, 1), "stats.synergy_games": duo.games}


def _map(ins: Insights, my_lane: Lane | None) -> Context:
    values: dict[str, Any] = {}
    for side_name, side in (("us", ins.lineup.us), ("them", ins.lineup.them)):
        for role, key in ROLE_KEYS.items():
            player = side.get(role)
            for f in CHAMP_FIELDS:
                values[f"{side_name}.{key}.{f}"] = _champ(player)[f] if player else None
    for lane in Lane:
        st, gk = ins.lanes[lane], ins.ganks[lane]
        values.update({
            f"lanes.{lane.value}.state.verdict": st.verdict,
            f"lanes.{lane.value}.state.diff": st.diff,
            f"lanes.{lane.value}.state.volatility": st.volatility,
            f"lanes.{lane.value}.gank.on_them": gk.on_them,
            f"lanes.{lane.value}.gank.on_us": gk.on_us,
            f"lanes.{lane.value}.threat": gk.threat,
            f"lanes.{lane.value}.plan.kind": ins.plans[lane].kind,
            f"priority.{lane.value}": ins.priority.by_lane.get(lane),
        })  # fmt: skip
    jg = ins.jungle
    values.update({
        "jg_diff": jg.diff, "invade_risk": jg.invade_risk,
        "priority.side": ins.priority.side, "priority.them_side": ins.priority.them_side,
        "gank_rank.us": jg.our_first_gank.value if jg.our_first_gank else None,
        "gank_rank.them": jg.their_first_gank.value if jg.their_first_gank else None,
        "gank_rank.us_score": (ins.ganks[jg.our_first_gank].on_them
                               if jg.our_first_gank else None),
        "my_lane": my_lane.value if my_lane else None,
        "them_divers": len(_dive_threats(ins)),
    })  # fmt: skip
    for lane, fight in ins.skirmishes.items():
        values[f"skirmish.{lane.value}"] = fight.winner
    values["path.start_side"] = ins.path.start_side
    values["path.target"] = ins.path.target.value if ins.path.target else None
    values["path.counter"] = ins.path.counter.value if ins.path.counter else None
    mid_roam = ins.roams["us"].get(Role.MID)
    target = mid_roam.target if mid_roam else None
    values["roam_target.us.mid"] = target.value if target else None
    values["roam_target.us.mid_gank"] = ins.ganks[target].on_them if target else None
    for side in ("us", "them"):
        for role in (Role.MID, Role.SUPPORT):
            roam = ins.roams[side].get(role)
            values[f"roam.{side}.{role.value}"] = roam.score if roam else None
    fill = {
        "us_jg": jg.us.name if jg.us else "your jungler",
        "them_jg": jg.them.name if jg.them else "their jungler",
        "gank_lane": jg.our_first_gank.value if jg.our_first_gank else "the best lane",
        "their_gank_lane": jg.their_first_gank.value if jg.their_first_gank else "a lane",
        "prio_side": ins.priority.side,
        "dive_threat": _names(_dive_threats(ins)[:2]) or "their divers",
        "mid_roam_lane": target.value if target else "a side lane",
    }  # fmt: skip
    for lane, s in ins.skirmishes.items():  # "Illaoi + Lee Sin"
        fill[f"{lane.value}_fight_us"] = s.us_names.replace("/", " + ") or "your side"
        fill[f"{lane.value}_fight_them"] = s.them_names.replace("/", " + ") or "their side"
    for side_name, side in (("us", ins.lineup.us), ("them", ins.lineup.them)):
        for role in (Role.MID, Role.SUPPORT):
            player = side.get(role)
            fill[f"{side_name}_{role.value}"] = player.name if player else f"their {role.value}"
    return Context("map", values, fill)


def _team(ins: Insights) -> Context:
    values: dict[str, Any] = {}
    for side, profile in ins.teams.items():
        values.update({
            f"{side}.team.early": profile.early, f"{side}.team.scaling": profile.scaling,
            f"{side}.team.n_engagers": profile.n_engagers,
            f"{side}.team.n_frontline": profile.n_frontline,
            f"{side}.team.n_hard_cc": profile.n_hard_cc,
            f"{side}.team.archetype": profile.archetype,
            f"{side}.team.n_dive_threats": sum(
                1 for p in ins.lineup.side(side).values() if _dives(p)
            ),
            **{f"{side}.team.damage.{d}": profile.damage.get(d, 0)
               for d in ("physical", "magic", "mixed")},
            **{f"{side}.team.n_{c}": profile.classes.get(c, 0) for c in CLASSES},
        })  # fmt: skip
    us, them = ins.teams["us"], ins.teams["them"]
    values["early_diff"] = _diff(us.early, them.early)
    values["scaling_diff"] = _diff(us.scaling, them.scaling)
    return Context("team", values, {})


def _dives(p: Player) -> bool:
    return bool(p.classes & {"diver", "assassin"}) or p.has("dive")


def _dive_threats(ins: Insights) -> list[Player]:
    """Enemy divers and assassins, biggest feed threat first."""
    return [t.player for t in ins.threats if _dives(t.player)]


def _diff(ours: float | None, theirs: float | None) -> float | None:
    return round(ours - theirs, 2) if ours is not None and theirs is not None else None


def _whole(value: float | None) -> str:
    return str(round(value)) if value is not None else "?"


def _names(players: list[Player]) -> str:
    names = [p.name for p in players]
    return ", ".join(names[:-1]) + f" and {names[-1]}" if len(names) > 1 else "".join(names)
