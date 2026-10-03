"""Compute every insight for a game once. Rules and the report read the result.

docs/ROLES.md (Shared insights) lists what each insight answers. No I/O here.
"""

import dataclasses
from dataclasses import dataclass

from scout.analysis.ganks import Gank, JunglePlan, ganks, jungle_plan
from scout.analysis.jungle import (
    JungleMatchup,
    JunglePath,
    Priority,
    Skirmish,
    jungle_matchup,
    jungle_path,
    priority,
    skirmishes,
)
from scout.analysis.lanes import LaneState, LaneTimeline, lane_state, lane_timeline, with_stats
from scout.analysis.players import (
    Lineup,
    build_lineup,
    with_data_scaling,
    with_measured,
    with_role_shares,
)
from scout.analysis.roam import Reach, Roam, cross_map, roams
from scout.analysis.stats import NO_STATS, SCALING_MEANINGFUL, GameStats
from scout.analysis.team import TeamProfile, team_profile
from scout.analysis.threats import Threat, feed_ranking
from scout.counterpick import DEFAULT_BANDS, Bands, Verdict, counterpick
from scout.data.briefs import Brief
from scout.data.store import Knowledge, traits_for
from scout.model.game import GameState
from scout.model.roles import Lane, Role


@dataclass(frozen=True)
class Insights:
    game: GameState
    lineup: Lineup
    lanes: dict[Lane, LaneState]
    timelines: dict[Lane, LaneTimeline]
    ganks: dict[Lane, Gank]
    plans: dict[Lane, JunglePlan]
    priority: Priority
    jungle: JungleMatchup
    path: JunglePath
    skirmishes: dict[Lane, Skirmish]
    roams: dict[str, dict[Role, Roam]]
    reach: dict[str, list[Reach]]
    teams: dict[str, TeamProfile]
    threats: list[Threat]
    stats: GameStats = NO_STATS
    counterpick: Verdict | None = None  # my matchup's verdict (docs/COUNTERPICK.md)
    brief: Brief | None = None  # matchup_briefs.csv row for my matchup, if any
    knowledge: Knowledge | None = None  # the champion data the analysis used (kits, Riot's tips)


def analyze(
    game: GameState,
    knowledge: Knowledge,
    stats: GameStats = NO_STATS,
    bands: Bands = DEFAULT_BANDS,
) -> Insights:
    lineup = build_lineup(game, knowledge)
    lineup = with_measured(with_role_shares(with_data_scaling(lineup, stats), stats), stats)
    lanes = {lane: with_stats(lane_state(lineup, lane), stats) for lane in Lane}
    timelines = {lane: lane_timeline(state) for lane, state in lanes.items()}
    gank_info = ganks(lineup, lanes)
    plans = {lane: jungle_plan(lanes[lane], timelines[lane], gank_info[lane]) for lane in Lane}
    prio = priority(lanes)
    matchup = jungle_matchup(lineup, gank_info, prio)
    my_lane = game.my_lane
    verdict = counterpick(
        game,
        lineup.us.get(game.my_role),
        lineup.them.get(game.my_role),
        stats,
        lanes[my_lane] if my_lane else None,
        matchup.diff if game.my_role is Role.JUNGLE else None,
        bands,
        {p.champ_id: p.name for p in lineup.players()},
    )
    return Insights(
        game=game,
        lineup=lineup,
        lanes=lanes,
        timelines=timelines,
        ganks=gank_info,
        plans=plans,
        priority=prio,
        jungle=matchup,
        path=jungle_path(gank_info, lanes, prio, matchup),
        skirmishes=_respect_lane_stats(skirmishes(lineup), lanes),
        roams=roams(lineup, gank_info),
        reach=cross_map(lineup),
        teams={side: team_profile(lineup, side) for side in ("us", "them")},
        threats=feed_ranking(lineup),
        stats=stats,
        counterpick=verdict,
        brief=_brief(game, knowledge),
        knowledge=knowledge,
    )


def _brief(game: GameState, knowledge: Knowledge) -> Brief | None:
    me, opp = game.ally.get(game.my_role), game.enemy.get(game.my_role)
    if me is None or opp is None:
        return None
    return knowledge.briefs.get((game.my_role.value, me.champ_id, opp.champ_id))


def _respect_lane_stats(
    found: dict[Lane, Skirmish], lanes: dict[Lane, LaneState]
) -> dict[Lane, Skirmish]:
    """No 'your lane plus jungler win early fights' where OP.GG says that lane loses early."""
    out = dict(found)
    for lane, s in found.items():
        state = lanes[lane]
        if state.source != "stats":
            continue
        if (s.winner, state.verdict) in (("us", "losing"), ("them", "winning")):
            out[lane] = dataclasses.replace(s, winner="even")
    return out


def stats_disagreements(ins: Insights) -> list[tuple[str, str]]:
    """(champ_id, details) where OP.GG's numbers and the traits disagree, for the review queue
    (docs/STATS.md, Stats vs traits). Lanes: opposite verdicts. Scaling: a big game-length
    swing against the champion's scaling trait."""
    rows = []
    for lane, state in ins.lanes.items():
        if state.disagrees and state.us.players and state.them.players:
            data = "us" if state.verdict == "winning" else "them"
            rows.append((state.us.players[0].champ_id,
                         f"{lane.value} lane vs {state.them.names}: OP.GG lane advantage {data}, "
                         f"traits said {state.traits_verdict}"))  # fmt: skip
    for p in ins.lineup.players():  # the drafted note against OP.GG's data, for the queue
        index = ins.stats.scaling.get(p.champ_id)
        traits = traits_for(ins.knowledge.traits, p.champ_id, p.role) if ins.knowledge else None
        drafted = traits.scaling if traits else None
        if index is None or drafted is None:
            continue
        if (index >= SCALING_MEANINGFUL and drafted <= 1) or (
            index <= -SCALING_MEANINGFUL and drafted == 3
        ):
            rows.append((p.champ_id, f"scaling {drafted} but OP.GG's win rate changes by "
                         f"{index:+.1f} points from short to long games"))  # fmt: skip
    return rows
