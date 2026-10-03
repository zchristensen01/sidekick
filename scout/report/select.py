"""Choose what goes in the report for my role: sections in order, items by priority.

Sections and their order per role: docs/ROLES.md. Items come from fired rules (audience and
section per role), insights (gank ranking, lane timeline, jungle threat, threats, game plan)
and champion facts (an opponent's key note under Punish). Each section keeps its top items by
priority; the writer (M7) condenses them to the word budget, and the deterministic renderer
shows them as they are.
"""

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field

from scout.analysis.insights import Insights
from scout.analysis.lanes import PHASE_LABEL, PHASES, VOLATILE_AT
from scout.analysis.players import Player
from scout.analysis.roam import reaching
from scout.analysis.stats import MatchupStat
from scout.analysis.team import FRONTLINE_AT
from scout.counterpick import verdict_text
from scout.data.patch import display_patch
from scout.data.store import Knowledge
from scout.model.roles import LANE_ROLES, Lane, Role, lane_of
from scout.rules.engine import Fired

TITLES = {
    "gank_first": "Best gank options", "lanes_in_trouble": "Lanes in trouble",
    "enemy_jungler": "Enemy jungler", "start_objectives": "Start and objectives",
    "your_lane": "Your lane", "opponent": "Know your opponent", "counterpick": "Counter-pick",
    "punish": "Punish",
    "jungle": "Junglers", "map_threats": "Watch the map", "roams": "Roams and the map",
    "your_job": "Your job later", "fights": "Fights", "protect_or_engage": "Protect or engage",
    "watch_out": "Watch out for", "dont_feed": "Don't let them get fed", "game_plan": "Game plan",
}  # fmt: skip
ORDER: dict[Role, tuple[str, ...]] = {
    Role.JUNGLE: ("gank_first", "lanes_in_trouble", "enemy_jungler", "start_objectives",
                  "counterpick", "watch_out", "dont_feed", "game_plan"),
    Role.TOP: ("your_lane", "opponent", "counterpick", "punish", "jungle", "map_threats",
               "your_job", "watch_out", "dont_feed", "game_plan"),
    Role.MID: ("your_lane", "opponent", "counterpick", "punish", "jungle", "roams", "watch_out",
               "dont_feed", "game_plan"),
    Role.BOT: ("your_lane", "opponent", "counterpick", "punish", "jungle", "map_threats", "fights",
               "watch_out", "dont_feed", "game_plan"),
    Role.SUPPORT: ("your_lane", "opponent", "counterpick", "punish", "roams", "jungle",
                   "protect_or_engage", "watch_out", "dont_feed", "game_plan"),
}  # fmt: skip
ALWAYS: dict[Role, frozenset[str]] = {
    Role.JUNGLE: frozenset({"gank_first", "lanes_in_trouble", "enemy_jungler",
                            "start_objectives", "game_plan"}),
    **{r: frozenset({"your_lane", "jungle", "game_plan"})
       for r in (Role.TOP, Role.MID, Role.BOT, Role.SUPPORT)},
}  # fmt: skip
# Where our own team's combos go (the pair rules' section, watch_out, is for enemy combos).
ALLY_COMBO_SECTION = {Role.JUNGLE: "game_plan", Role.TOP: "your_job", Role.MID: "game_plan",
                      Role.BOT: "fights", Role.SUPPORT: "protect_or_engage"}  # fmt: skip
MAX_ITEMS = 3  # per section
# Sections that carry an overview line, or two champions (bot lane's opponents)
WIDE_SECTIONS = {"lanes_in_trouble": 4, "jungle": 4, "opponent": 4}
SHORT_SECTIONS = {"watch_out": 2, "dont_feed": 2}  # laners get less of these
LOW_CONFIDENCE = 0.6  # enemy role guesses below this are named in warnings


@dataclass(frozen=True)
class Item:
    source: str  # rule id, insight:<name>, fact:<champ>, note
    text: str
    confidence: str = "high"
    priority: int = 50
    subject: str = ""  # the champion it's about; one item per champion per section
    numbers: tuple[str, ...] = ()  # pre-formatted stats strings the writer copies exactly


@dataclass
class Section:
    key: str
    title: str
    always: bool
    items: list[Item] = field(default_factory=list)


@dataclass
class Report:
    role: Role
    champion: str
    patch: str
    queue: str
    ally: dict[Role, str]
    enemy: dict[Role, str]
    sections: list[Section]
    warnings: list[str]
    your_notes: list[str]
    side: str = ""  # blue | red | ""


def select(
    insights: Insights,
    fired: Iterable[Fired],
    notes: Iterable[Mapping[str, str]] = (),
    low_confidence: float = LOW_CONFIDENCE,
) -> Report:
    game, lineup = insights.game, insights.lineup
    role = game.my_role
    order = ORDER[role]
    items: dict[str, list[Item]] = {key: [] for key in order}

    for f in fired:
        if role not in f.audience:
            continue
        key = f.rule.section_for(role)
        if key == "map_threats" and "map_threats" not in items:
            key = "roams"  # mid and support see cross-map threats under Roams and the map
        if key == "watch_out" and f.team == "us":
            key = ALLY_COMBO_SECTION[role]  # our own combos aren't threats
        if key in items:
            items[key].append(Item(f.id, f.text, f.rule.confidence, f.rule.priority, f.subject))

    for key, item in _insight_items(insights, role):
        if key in items:
            items[key].append(item)

    sections = []
    for key in order:
        limit = WIDE_SECTIONS.get(key, MAX_ITEMS)
        if role is not Role.JUNGLE and key in SHORT_SECTIONS:
            limit = 1
        chosen = _top(items[key], limit)
        always = key in ALWAYS[role]
        if chosen or always:
            if not chosen:
                chosen = [Item("insight:none", "Nothing stands out here for this draft.", "med")]
            sections.append(Section(key, TITLES[key], always, chosen))

    me = lineup.us.get(role)
    return Report(
        role=role,
        champion=me.name if me else "",
        patch=display_patch(game.ddragon_version),
        queue=game.queue.value,
        ally={r: p.name for r, p in lineup.us.items()},
        enemy={r: p.name for r, p in lineup.them.items()},
        sections=sections,
        warnings=_warnings(insights, low_confidence),
        your_notes=_your_notes(insights, notes),
        side=game.side,
    )


def _top(items: list[Item], limit: int) -> list[Item]:
    seen: set[str] = set()
    unique = []
    for item in sorted(items, key=lambda i: -i.priority):  # stable: rule order breaks ties
        keys = {item.text} | ({f"subject:{item.subject}"} if item.subject else set())
        if not keys & seen:
            seen |= keys
            unique.append(item)
    return unique[:limit]


# ---------------------------------------------------------------- insight and fact items


def _insight_items(ins: Insights, role: Role) -> list[tuple[str, Item]]:
    out: list[tuple[str, Item]] = []
    lineup = ins.lineup
    my_lane = lane_of(role)

    if role is Role.JUNGLE:
        ranked = sorted((g for g in ins.ganks.values() if g.our_rank), key=lambda g: g.our_rank)
        for g in ranked[:2]:
            if g.our_rank == 1 or (g.on_them or 0) >= 6:
                why = "; ".join(g.reasons_on_them) or "the best odds of the three lanes"
                out.append(("gank_first", Item("insight:gank_rank",
                                               f"{g.lane.value.capitalize()}: {why}.", "high",
                                               90 - g.our_rank)))  # fmt: skip
        jg = ins.jungle
        if jg.them:
            # The style rules (JG-ENEMY-GANKER / -FARMER) already name their first gank.
            parts = []
            if jg.diff == 0:
                parts.append(f"even early 1v1 with {jg.us.name if jg.us else 'yours'}")
            if jg.their_first_gank and not jg.them.style:
                parts.append(f"likely first gank: {jg.their_first_gank.value}")
            if parts:
                text = f"{jg.them.name}: {', '.join(parts)}."
                out.append(("enemy_jungler", Item("insight:jungle_matchup", text, "high", 40)))
            if jg.them.key_note:
                out.append(
                    (
                        "watch_out",
                        Item(
                            f"fact:{jg.them.champ_id}",
                            f"{jg.them.name}: {jg.them.key_note}",
                            "med",
                            40,
                        ),
                    )
                )
        overview = f"At a glance: {_lanes_overview(ins)}."
        out.append(("lanes_in_trouble", Item("insight:lanes_overview", overview, "high", 95)))
        out.append(("start_objectives", Item("insight:jungle_path", _path_text(ins), "med", 85)))
        for item in _game_fact_items(ins):
            out.append(("start_objectives", item))
    elif my_lane is not None:
        if ins.brief is None:  # a matchup brief replaces the computed timeline
            out.append(("your_lane", _timeline_item(ins, my_lane)))
        out.append(("jungle", _jungle_item(ins, my_lane)))
    verdict = ins.counterpick
    if verdict is not None:
        numbers = tuple(n for n in (verdict.display, *(a.display for a in verdict.alternatives))
                        if n)  # fmt: skip
        out.append(("counterpick", Item("insight:counterpick", verdict_text(verdict), "high", 96,
                                        numbers=numbers)))  # fmt: skip
    stats_section = "enemy_jungler" if role is Role.JUNGLE else "your_lane"
    out += _opponent_items(ins, role, ins.knowledge)
    for key, item in _brief_items(ins, role):
        out.append((key, item))
    for item in _stats_items(ins, role):
        out.append(("punish" if item.source.startswith("stat:tip") and role is not Role.JUNGLE
                    else stats_section, item))  # fmt: skip
    if my_lane is not None:
        for opponent in _punish_targets(lineup.them, role):
            if opponent.key_note:
                out.append(
                    (
                        "punish",
                        Item(
                            f"fact:{opponent.champ_id}",
                            f"{opponent.name}: {opponent.key_note}",
                            "med",
                            60,
                        ),
                    )
                )

    if role is Role.TOP:
        out.append(("your_job", Item("insight:your_job", _top_job(ins), "med", 40)))
    if role is Role.SUPPORT:
        out += [("protect_or_engage", item) for item in _support_job(ins)]
    if role is Role.BOT:
        diver = next((t.player for t in ins.threats if _dives(t.player)), None)
        if diver is not None:
            text = (
                f"In fights, track {diver.name}: they can reach you, so stay behind your frontline."
            )
            out.append(("fights", Item("insight:threats", text, "med", 45, diver.name)))

    limit = 2 if role is Role.JUNGLE else 1
    for threat in _feed_threats(ins, role)[:limit]:
        why = ", ".join(threat.reasons) or "a big threat if ahead"
        out.append(("dont_feed", Item("insight:threats", f"{threat.player.name}: {why}.",
                                      "med", 50, threat.player.name)))  # fmt: skip
    out.append(("game_plan", Item("insight:game_plan", _game_plan(ins), "med", 80)))
    return out


def _timeline_item(ins: Insights, lane: Lane) -> Item:
    timeline = ins.timelines[lane]
    if all(v == "unknown" for v in timeline.phases.values()):
        why = "; ".join(ins.lanes[lane].reasons) or "missing traits"
        return Item("insight:lane_timeline", f"Lane timeline unknown ({why}).", "med", 90)
    words = {"us": "you", "them": "them", "even": "even", "unknown": "?"}
    phases = ", ".join(f"{PHASE_LABEL[p]}: {words[timeline.phases[p]]}" for p in PHASES)
    why = list(dict.fromkeys(r for p in PHASES for r in timeline.reasons[p]))
    text = f"Who's favored: {phases}." + (f" Why: {'; '.join(why[:3])}." if why else "")
    return Item("insight:lane_timeline", text, "med", 90)


def _jungle_item(ins: Insights, lane: Lane) -> Item:
    gank, jg = ins.ganks[lane], ins.jungle
    parts = []
    if jg.them:
        threat = {
            "high": "a big threat to your lane",
            "med": "some threat to your lane",
            "low": "a low early gank threat to your lane",
            "unknown": "unknown threat",
        }[gank.threat]
        parts.append(f"{jg.them.name} is {threat}")  # fmt: skip
    if jg.our_first_gank:
        side = "your lane" if jg.our_first_gank == lane else jg.our_first_gank.value
        parts.append(f"your jungler's best gank is {side}")
    text = "; ".join(parts).capitalize() + "." if parts else "Jungle matchup unknown."

    return Item("insight:jungle_threat", text, "med", 70)


def _feed_threats(ins: Insights, role: Role) -> list:
    """Threats this player can do something about: the jungler sees all of them; a laner sees
    their lane opponents, the enemy jungler, and enemies whose roams or ults reach their lane."""
    lane = lane_of(role)
    if lane is None:
        return list(ins.threats)
    relevant = {p.champ_id for r, p in ins.lineup.them.items()
                if r in LANE_ROLES[lane] or r is Role.JUNGLE}  # fmt: skip
    relevant |= {p.champ_id for p in reaching(ins.reach, "them", lane)}
    return [t for t in ins.threats if t.player.champ_id in relevant]


def _lanes_overview(ins: Insights, skip: Lane | None = None) -> str:
    """'Top even; Mid you win early; Bot they win early, you scale (volatile)'."""
    words = {"winning": "you win early", "losing": "they win early", "even": "even",
             "unknown": "unknown"}  # fmt: skip
    parts = []
    for lane in Lane:
        if lane is skip:
            continue
        state, late = ins.lanes[lane], ins.timelines[lane].phases.get("item1")
        verdict = words[state.verdict]
        if state.verdict == "losing" and late == "us":
            verdict += ", you scale"
        elif state.verdict == "winning" and late == "them":
            verdict += ", they scale"
        if (state.volatility or 0) >= VOLATILE_AT:
            verdict += " (volatile)"
        stat = ins.stats.matchups.get(LANE_ROLES[lane][0])
        if stat is not None and stat.shown:
            verdict += f" (game win rate {stat.display})"
        parts.append(f"{lane.value.capitalize()} {verdict}")
    return "; ".join(parts)


def _stats_items(ins: Insights, role: Role) -> list[Item]:
    """OP.GG numbers for my matchup (and the bot duos), the opponent's usual build into me,
    and OP.GG's tip. Numbers come pre-formatted (STATS.md rule 4)."""
    stats, me, opp = ins.stats, ins.lineup.us.get(role), ins.lineup.them.get(role)
    if me is None or opp is None:
        return []
    items = []
    stat = stats.matchups.get(role)
    labels = _labels_text(stat, opp) if stat is not None and stat.shown else ""
    if labels:  # the win rate itself is in the counter-pick verdict
        items.append(Item(f"stat:matchup:{role.value}", labels, "high", 88))
    duo_parts, duo_numbers = [], []
    if role in (Role.BOT, Role.SUPPORT):
        for side, whose in (("us", "Your"), ("them", "Their")):
            duo = stats.duos.get(side)
            if duo is not None and duo.shown:
                names = {p.champ_id: p.name for p in ins.lineup.players()}
                duo_parts.append(f"{whose} {names.get(duo.a, duo.a)} + {names.get(duo.b, duo.b)}"
                                 f" win {duo.display} together")  # fmt: skip
                duo_numbers.append(duo.display)
    if duo_parts:
        items.append(Item("stat:synergy:bot", "; ".join(duo_parts) + ".", "med", 52,
                          numbers=tuple(duo_numbers)))  # fmt: skip
    build = stats.builds.get(role)
    if build:
        text = f"{opp.name}'s usual build into {me.name}: {', '.join(build)}."
        items.append(Item(f"stat:items:{role.value}", text, "med", 50, opp.name))
    if stat is not None and stat.labels is not None and stat.labels.tip:
        text = f"OP.GG's tip against {opp.name}: {stat.labels.tip}"
        items.append(Item(f"stat:tip:{role.value}", text, "med", 45))
    return items


def _opponent_items(
    ins: Insights, role: Role, knowledge: Knowledge | None
) -> list[tuple[str, Item]]:
    """What my lane opponents do, in Riot's words: each one's passive and Riot's first tip for
    playing against them (both enemies in bot lane). The jungler gets the enemy jungler's."""
    if knowledge is None:
        return []
    lane = lane_of(role)
    roles = LANE_ROLES[lane] if lane else (Role.JUNGLE,)
    section = "opponent" if lane else "enemy_jungler"
    out = []
    for r in roles:
        opp = ins.lineup.them.get(r)
        if opp is None:
            continue
        passive = next((a for a in knowledge.abilities.get(opp.champ_id, ()) if a["slot"] == "P"),
                       None)  # fmt: skip
        if passive and passive["description"]:
            text = f"{opp.name}'s passive, {passive['name']}: {passive['description']}"
            out.append((section, Item(f"riot:passive:{opp.champ_id}", text, "high", 72, "")))
        for n, tip in enumerate(knowledge.tips.get((opp.champ_id, "enemy"), ())[:2]):
            text = f"Riot's tip against {opp.name}: {tip}"
            out.append((section, Item(f"riot:tip:{opp.champ_id}", text, "high", 68 - 4 * n, "")))
    return out


def _brief_items(ins: Insights, role: Role) -> list[tuple[str, Item]]:
    """docs/KNOWLEDGE.md layer 3: my matchup's brief, by phase."""
    b = ins.brief
    if b is None:
        return []
    source = f"brief:{b.role.value}:{b.champ}:{b.opp}"
    confidence = "high" if b.reviewed else "med"
    lane = "enemy_jungler" if role is Role.JUNGLE else "your_lane"
    ask = "enemy_jungler" if role is Role.JUNGLE else "jungle"
    return [
        (lane, Item(source, f"Levels 1-3: {b.early} Levels 3-6: {b.levels_3_6}", confidence, 89)),
        (lane, Item(source, f"Trading: {b.trade_pattern}", confidence, 76)),
        (lane, Item(source, f"After 6: {b.after_6} First item: {b.first_item}", confidence, 73)),
        (ask, Item(source, f"Ask your jungler: {b.jungle_ask}" if role is not Role.JUNGLE
                   else b.jungle_ask, confidence, 77)),
    ]  # fmt: skip


def _labels_text(stat: MatchupStat, opp: Player) -> str:
    """OP.GG's read of the early lane: 'Per OP.GG, the early lane is even and Elise gets
    more solo kills.' Empty when OP.GG gives no labels."""
    advantage = stat.labels.lane_advantage if stat.labels else ""
    solo_kills = stat.labels.solo_kill_advantage if stat.labels else ""
    lane = {"us": "you have the early lane", "them": f"{opp.name} has the early lane",
            "even": "the early lane is even"}.get(advantage)  # fmt: skip
    solo = {"us": "you get more solo kills",
            "them": f"{opp.name} gets more solo kills"}.get(solo_kills)  # fmt: skip
    said = [part for part in (lane, solo) if part]
    return f"Per OP.GG, {' and '.join(said)}." if said else ""


def _path_text(ins: Insights) -> str:
    path, them = ins.path, ins.jungle.them
    if path.target is None:
        return "Route: not enough champion data to suggest one."
    start = "either side" if path.start_side == "either" else f"{path.start_side} side"
    why = f" ({'; '.join(path.reasons)})" if path.reasons else ""
    text = f"Suggested route: start {start} so your first clear ends near {path.target.value}{why}."
    if path.counter is not None and them is not None:
        if path.counter == path.target:
            text += (f" {them.name} most likely goes {path.counter.value} too, so getting there "
                     "first also sets up a counter-gank.")  # fmt: skip
        else:
            text += (f" {them.name} most likely ganks {path.counter.value} first: ward that side, "
                     "or path near it for a counter-gank.")  # fmt: skip
    return text


def _dives(p: Player) -> bool:
    return bool(p.classes & {"diver", "assassin"}) or p.has("dive")


def _top_job(ins: Insights) -> str:
    me = ins.lineup.us.get(Role.TOP)
    if me is None:
        return "Your job later: unknown."
    others_front = [p for r, p in ins.lineup.us.items()
                    if r is not Role.TOP and (p.frontline or 0) >= FRONTLINE_AT]  # fmt: skip
    carries = [p.name for r, p in ins.lineup.them.items() if r in (Role.MID, Role.BOT)]
    if (me.frontline or 0) >= FRONTLINE_AT and not others_front:
        return "Your job later: be the frontline; nobody else on your team can stand in front."
    if _dives(me):
        return f"Your job later: reach their backline ({' and '.join(carries)}) once fights start."
    if me.has("split_push"):
        return "Your job later: pressure a side lane and join fights when objectives are up."
    return "Your job later: group with your team for objectives and fight with them."


def _support_job(ins: Insights) -> list[Item]:
    me, carry = ins.lineup.us.get(Role.SUPPORT), ins.lineup.us.get(Role.BOT)
    items: list[Item] = []
    if me is None:
        return items
    if (me.engage or 0) >= 2 or me.has("ult_engage"):
        targets = [p for r, p in ins.lineup.them.items()
                   if r in (Role.MID, Role.BOT) and p.escape is not None]  # fmt: skip
        if targets:
            target = min(targets, key=lambda p: p.escape or 0)
            text = f"Engage target in fights: {target.name} (the carry with the least escape)."
            items.append(Item("insight:support_job", text, "med", 50, target.name))
    if me.has("peel") and carry is not None:
        text = f"In fights, stay near {carry.name} and keep your peel for them."
        items.append(Item("insight:support_job", text, "med", 45))
    return items


def _punish_targets(enemy: dict[Role, Player], role: Role) -> list[Player]:
    if role in (Role.BOT, Role.SUPPORT):
        return [p for r in (Role.SUPPORT, Role.BOT) if (p := enemy.get(r))]
    return [p for p in [enemy.get(role)] if p]


def _game_plan(ins: Insights) -> str:
    """One line: when to fight, where to play, and who to keep down. The early part is about
    the whole team, so a laner whose own lane reads the other way hears both (a team that's
    stronger early doesn't make a losing lane safe)."""
    us, them = ins.teams["us"], ins.teams["them"]
    early = _diff(us.early, them.early)
    scaling = _diff(us.scaling, them.scaling)
    lane = lane_of(ins.game.my_role)
    mine = ins.lanes.get(lane) if lane else None
    lane_bad = mine is not None and (mine.verdict == "losing"
                                     or mine.label in ("survive", "pushed"))  # fmt: skip
    lane_good = mine is not None and mine.verdict == "winning" and not lane_bad
    parts = []
    if early is not None and early <= -0.4 and lane_good:
        parts.append("use your lane lead while the rest of the team plays safe early")
    elif early is not None and early <= -0.4:
        parts.append(
            "survive the early game"
            + (" and win the later fights" if (scaling or 0) >= 0.4 else "")
        )
    elif early is not None and early >= 0.4 and lane_bad:
        parts.append("hold your lane while the rest of the team uses its early edge")
    elif early is not None and early >= 0.4:
        parts.append(
            "press your early advantage"
            + (" and close before their spikes" if (scaling or 0) <= -0.4 else "")
        )
    elif scaling is not None and scaling >= 0.4:
        parts.append("play safe early and win the later fights")
    elif scaling is not None and scaling <= -0.4:
        parts.append("build a lead early and end before their spikes")
    winning = [lane.value for lane, s in ins.lanes.items() if s.verdict == "winning"]
    focus = winning or ([ins.jungle.our_first_gank.value] if ins.jungle.our_first_gank else [])
    if focus:
        parts.append(f"play around {' and '.join(focus)}")
    if ins.threats:
        parts.append(f"keep {ins.threats[0].player.name} from getting ahead")
    if not parts:
        return "Even draft: lane states and jungle tempo decide it."
    text = ", ".join(parts[:-1]) + (" and " if len(parts) > 1 else "") + parts[-1]
    return text[0].upper() + text[1:] + "."


def _game_fact_items(ins: Insights) -> list[Item]:
    """The jungler's timers from data/manual/game_facts.csv (Riot's patch notes and the wiki):
    static pre-game facts, never live timers (docs/POLICY.md)."""
    knowledge = ins.knowledge
    if knowledge is None:
        return []
    items = []
    for topic, priority in (("objective", 30), ("camps", 28)):
        facts = knowledge.facts_about(topic)
        if facts:
            text = " ".join(f["text"] for f in facts)
            items.append(Item(f"fact:game:{topic}", text, "high", priority))
    return items


def _diff(a: float | None, b: float | None) -> float | None:
    return round(a - b, 2) if a is not None and b is not None else None


# ---------------------------------------------------------------- warnings and notes


def _warnings(ins: Insights, low_confidence: float) -> list[str]:
    warnings = list(ins.game.notes)
    for role, pick in ins.lineup.them.items():
        if pick.confidence < low_confidence:
            odds = ins.game.enemy_role_odds.get(role, [])
            others = [c for c, p in odds[1:3] if p >= 0.15]
            names = {p.champ_id: p.name for p in ins.lineup.players()}
            also = f"; could be {' or '.join(names.get(c, c) for c in others)}" if others else ""
            warnings.append(
                f"{pick.name} as their {role.value} is a guess ({round(pick.confidence * 100)}% "
                f"sure{also})."
            )
    if ins.stats.notice:
        warnings.append(ins.stats.notice)
    if ins.brief is not None and not ins.brief.reviewed:
        names = {p.champ_id: p.name for p in ins.lineup.players()}
        b = ins.brief
        me, opp = names.get(b.champ, b.champ), names.get(b.opp, b.opp)
        warnings.append(f"The matchup brief for {me} vs {opp} is a draft, not yet reviewed "
                        "(data/manual/matchup_briefs.csv).")  # fmt: skip
    for lane, state in ins.lanes.items():
        if state.disagrees:
            data = "you win" if state.verdict == "winning" else "they win"
            warnings.append(
                f"{lane.value.capitalize()}: OP.GG's matchup data says {data} early; the "
                "champion notes said the opposite. Going with the data."
            )
    for p in ins.lineup.players():
        if p.off_role:
            share = round((p.role_share or 0) * 100)
            warnings.append(f"No data for {p.name} {p.role.value}: OP.GG has {share}% of "
                            f"{p.name}'s games there, so nothing here is measured for this pick. "
                            "The written report can add the AI's read of its kit, marked as "
                            "such.")  # fmt: skip
    unreviewed = [p for p in ins.lineup.players() if p.has_traits and not p.reviewed]
    missing = [p.name for p in ins.lineup.players() if not p.has_traits]
    if missing:
        warnings.append(f"No traits for {', '.join(missing)}: advice about them is limited.")
    if unreviewed:
        names = [p.name for p in unreviewed]
        listed = ", ".join(names) if len(names) <= 3 else f"{len(names)} champions"
        unmeasured = [p for p in unreviewed if p.source_of("early") != "riot-measured"]
        drafted = ("Early game, wave clear and roaming, engage, power spikes and the champion notes"
                   if unmeasured else "Engage, power spikes and the champion notes")  # fmt: skip
        sourced = ("crowd control, mobility and toughness are Riot's ratings, mechanics the LoL "
                   "Wiki's")  # fmt: skip
        if len(unmeasured) < len(unreviewed):  # some measured from Riot's match data (M19)
            sourced += ", early game, wave clear and roaming measured from Riot's games"
        if unmeasured and len(unmeasured) < len(unreviewed):
            drafted += f" (the first three for {', '.join(p.name for p in unmeasured[:3])})"
        warnings.append(f"{drafted} are still drafts for {listed} (`scout review`); "
                        f"{sourced}.")  # fmt: skip
    return warnings


def _your_notes(ins: Insights, notes: Iterable[Mapping[str, str]]) -> list[str]:
    role = ins.game.my_role
    me = ins.lineup.us.get(role)
    opponent = ins.lineup.them.get(role)
    if me is None or opponent is None:
        return []
    return [
        n["note"] for n in notes
        if n.get("role") == role.value and n.get("champ_id") == me.champ_id
        and n.get("opp_champ_id") == opponent.champ_id and n.get("note")
    ]  # fmt: skip
