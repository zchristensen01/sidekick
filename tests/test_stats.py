"""Stats (M8): the math (docs/STATS.md), the database, draft-time fetching, reports with
numbers, and the network-down fallback. Recorded OP.GG answers; no network."""

import dataclasses
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from scout.analysis import stats as st
from scout.analysis.insights import analyze, stats_disagreements
from scout.analysis.lanes import with_stats
from scout.analysis.role_inference import infer_roles, merged_rates, rates_from_wiki_positions
from scout.data import opgg
from scout.data.opgg import Opgg, OpggError, OpggNoData
from scout.data.stats_db import Counts, Labels, StatsDb
from scout.data.stats_service import StatsService
from scout.data.store import read_csv
from scout.model.gamefile import load_game
from scout.model.roles import Lane, Role
from scout.report.render import render_text
from scout.report.select import select
from scout.rules.context import contexts
from scout.rules.engine import evaluate, load_rules

ROOT = Path(__file__).resolve().parent.parent
SOURCES = ROOT / "tests/fixtures/sources/opgg"
STATIC = {
    name: read_csv(ROOT / "tests/fixtures/static/16.19.1" / name)
    for name in ("champions.csv", "champion_meta.csv")
}
RULES = load_rules(ROOT / "scout/rules/league_rules.yaml")
NOW = datetime(2026, 10, 2, 20, 0, tzinfo=UTC)
ITEMS = {6692: "Eclipse", 6610: "Sundered Sky", 6333: "Death's Dance"}


def flat(text: str) -> str:
    """The rendered report without its line wrapping."""
    return " ".join(text.split())


def recorded(name: str) -> dict:
    return json.loads((SOURCES / name).read_text(encoding="utf-8"))


TOOLS = recorded("tools_list.json")["result"]["tools"]


# ---------------------------------------------------------------- the math


def test_expected_matchup_from_base_rates():
    assert st.expected_matchup(0.52, 0.48) == pytest.approx(0.54, abs=0.001)
    assert st.expected_matchup(0.5, 0.5) == pytest.approx(0.5)
    assert st.expected_duo(0.5, 0.5) == pytest.approx(0.5)


def test_shrinkage_depends_on_games():
    assert st.shrink(0, 0, 0.5, 1000) == 0.5
    assert st.shrink(47, 100, 0.5, 1000) == pytest.approx(0.497, abs=0.001)  # few games: ~expected
    assert st.shrink(47000, 100000, 0.5, 1000) == pytest.approx(0.47, abs=0.001)


def test_previous_patch_blending():
    this, prev = Counts(100, 60), Counts(1000, 500)
    mixed = st.blend(this, prev, 0.5)
    assert mixed.counts == Counts(600, 310) and mixed.previous_share == pytest.approx(500 / 600)
    assert st.blend(this, prev, 0.0).counts == this  # a changed champion: old data ignored
    assert st.blend(None, None, 0.5) is None


def test_patch_pair():
    assert st.patch_pair(["16.18", "16.19"], "16.19") == ("16.19", "16.18")
    assert st.patch_pair(["16.18"], "16.19") == (None, "16.18")  # OP.GG still on last patch
    assert st.patch_pair(["16.19", "16.20"], "16.19") == ("16.19", None)
    assert st.patch_pair(["16.20"], "16.19") == ("16.20", None)  # OP.GG ahead of our static data
    assert st.patch_pair([], "16.19") == (None, None)
    assert st.patch_pair(["16.15", "16.19"], "16.19") == ("16.19", None)  # a gap: not "last patch"


def test_display_strings():
    assert st.display(0.4761, 3572) == "48% over 3,572 games"
    assert st.display(0.52, 1786.4, "26.18") == "52% over 1,786 games (26.18)"
    assert (
        st.display(0.5, 900, mostly_previous=True)
        == "50% over 900 games (mostly last patch's data)"
    )


def test_scaling_index_from_game_lengths():
    guide = opgg.parse_guide(
        recorded("lane_matchup_guide_LeeSin_vs_Elise_jungle.json")["result"]["content"][0]["text"]
    )
    assert st.scaling_index(guide.game_lengths) == pytest.approx(-5.2, abs=0.05)  # falls off
    assert st.scaling_index({0: 0.5}) is None


# ---------------------------------------------------------------- a fake OP.GG


class FakeOpgg:
    """Answers like OP.GG from the recorded fixtures. Only Lee Sin (jungle) has a guide."""

    def __init__(self, down: bool = False) -> None:
        self.down = down
        self.calls: list[tuple[str, dict]] = []

    def request(self, method, params):
        if self.down:
            raise OpggError("OP.GG unreachable (ConnectError: no network)")
        if method == "tools/list":
            return {"tools": TOOLS}
        tool, args = params["name"], params["arguments"]
        self.calls.append((tool, args))
        if tool == opgg.LANE_META:
            return recorded("lane_meta_all.json")["result"]
        if tool == opgg.SYNERGIES:
            return recorded("champion_synergies_Samira_bot.json")["result"]
        if args["my_champion"] == "LEE_SIN" and args["position"] == "jungle":  # Lee Sin's table
            return recorded("lane_matchup_guide_LeeSin_vs_Elise_jungle.json")["result"]
        raise OpggNoData("Invalid position or champion specified (code -32600)")


def make_service(server: FakeOpgg | None, db: StatsDb | None = None, **kwargs) -> StatsService:
    client = Opgg(server, min_interval_s=0) if server is not None else None
    service = StatsService.from_static(
        db or StatsDb(":memory:"),
        st.StatsSettings(),
        "16.19.1",
        STATIC,
        opgg=client,
        now=lambda: NOW,
        **kwargs,
    )
    service.items = ITEMS
    return service


def game(name: str = "samira_naut", role: Role = Role.JUNGLE, knowledge=None):
    found = load_game(
        ROOT / f"tests/fixtures/games/{name}.yaml", set(knowledge.champions) if knowledge else None
    )
    return dataclasses.replace(found, my_role=role)


# ---------------------------------------------------------------- refresh and role rates


def test_lane_meta_refresh_learns_the_patch_and_role_rates():
    server = FakeOpgg()
    service = make_service(server)
    summary = service.refresh_lane_meta()
    assert summary.startswith("lane stats: ") and "for patch 16.19" in summary
    assert [c[0] for c in server.calls] == [opgg.LANE_META, opgg.GUIDE]  # guide: learn the patch
    rates = service.role_rates()
    assert rates["LeeSin"][Role.JUNGLE] == 0.96
    assert rates["Elise"] == {Role.JUNGLE: 0.77, Role.SUPPORT: 0.18}
    assert not service.lane_stats_stale()
    assert service.db.opgg_patch() == "16.19"


def test_role_inference_uses_opgg_rates_where_it_has_them():
    service = make_service(FakeOpgg())
    service.refresh_lane_meta()
    wiki = rates_from_wiki_positions(STATIC["champion_meta.csv"])
    rates = merged_rates(service.role_rates(), wiki)
    assert rates["Elise"] == {Role.JUNGLE: 0.77, Role.SUPPORT: 0.18}
    new = merged_rates({"LeeSin": {Role.JUNGLE: 0.96}}, {"Newchamp": {Role.MID: 1.0}})
    assert new == {"LeeSin": {Role.JUNGLE: 0.96}, "Newchamp": {Role.MID: 1.0}}  # wiki fallback
    guess = infer_roles(["Morgana", "Elise"], rates)
    assert guess.best == {Role.JUNGLE: "Elise", Role.SUPPORT: "Morgana"}


def test_a_tool_change_stops_stats_loudly():
    server = FakeOpgg()
    service = make_service(server)
    service.opgg = Opgg(server, min_interval_s=0)
    tools = [t for t in TOOLS if t["name"] != opgg.LANE_META]
    server.request = lambda m, p, r=server.request: (
        {"tools": tools} if m == "tools/list" else r(m, p)
    )
    with pytest.raises(OpggError, match="tools changed"):
        service.refresh_lane_meta()


# ---------------------------------------------------------------- during a draft


def test_prefetch_then_report_numbers(knowledge):
    server = FakeOpgg()
    service = make_service(server)
    service.refresh_lane_meta()
    g = game(knowledge=knowledge)
    service.prefetch(g)
    stats = service.for_game(g, budget_s=10)
    jg = stats.matchups[Role.JUNGLE]
    assert (jg.champ, jg.opp, jg.games) == ("LeeSin", "Elise", 3572)
    assert jg.raw_rate == pytest.approx(1700 / 3572)
    assert jg.display == "48% over 3,572 games" and jg.shown and jg.patch_label == ""
    assert jg.labels == Labels("even", "them", "even", jg.labels.tip)
    assert stats.notice == ""  # "no data for this pair" answers aren't outages
    asked = {
        (a["position"], a["my_champion"], a["opponent_champion"])
        for t, a in server.calls
        if t == opgg.GUIDE
    }
    assert ("jungle", "ELISE", "LEE_SIN") in asked  # my opponent's build into me
    assert ("adc", "JHIN", "SAMIRA") in asked and ("top", "GAREN", "MALPHITE") in asked
    before = len(server.calls)
    service.prefetch(g)
    service.wait(10)
    guides_again = [c for c in server.calls[before:] if c[1].get("my_champion") == "LEE_SIN"]
    assert guides_again == []  # fresh in the database: not fetched twice

    insights = analyze(g, knowledge, stats)
    text = flat(render_text(select(insights, evaluate(RULES, insights))))
    # 47.7% is a slight disadvantage, but no worse than both champions' overall strength
    # predicts (Lee Sin 49.2% vs Elise 51.0% in the jungle): weaker patch, not a counter.
    assert (
        "Elise isn't a special counter to Lee Sin (game win rate 48% over 3,572 games): 1 point "
        "worse than both champions' overall strength predicts, so Lee Sin is just weaker this "
        "patch."
    ) in text
    assert "Per OP.GG, the early lane is even and Elise gets more solo kills." in text
    assert insights.counterpick.label == "weak_patch" and insights.counterpick.source == "opgg"


def test_the_opponents_build_into_me(knowledge):
    service = make_service(FakeOpgg())
    service.refresh_lane_meta()
    g = dataclasses.replace(game(knowledge=knowledge), my_role=Role.JUNGLE)
    flipped = dataclasses.replace(
        g,
        ally={**g.ally, Role.JUNGLE: g.enemy[Role.JUNGLE]},
        enemy={**g.enemy, Role.JUNGLE: g.ally[Role.JUNGLE]},
    )
    service.prefetch(flipped)  # I'm Elise; the guide we have is Lee Sin's into Elise
    stats = service.for_game(flipped, budget_s=10)
    assert stats.builds[Role.JUNGLE] == ("Eclipse", "Sundered Sky", "Death's Dance")
    elise = stats.matchups[Role.JUNGLE]
    assert (elise.champ, elise.games) == ("Elise", 3572)  # from Lee Sin's table, flipped
    assert elise.raw_rate == pytest.approx(1872 / 3572)
    assert elise.labels.solo_kill_advantage == "us"
    insights = analyze(flipped, knowledge, stats)
    text = flat(render_text(select(insights, evaluate(RULES, insights))))
    assert "Lee Sin's usual build into Elise: Eclipse, Sundered Sky, Death's Dance." in text


def test_network_down_still_gives_a_report_with_one_notice(knowledge):
    """M8 done-when: with the network unplugged, a rules-only report and a one-line notice."""
    service = make_service(FakeOpgg(down=True))
    g = game(knowledge=knowledge)
    service.prefetch(g)
    stats = service.for_game(g, budget_s=10)
    assert not stats.any
    assert stats.notice.startswith("Stats unavailable (OP.GG unreachable")
    insights = analyze(g, knowledge, stats)
    report = select(insights, evaluate(RULES, insights))
    assert [w for w in report.warnings if w.startswith("Stats unavailable")] == [stats.notice]
    assert report.sections and " games" not in render_text(report).split("WARNINGS")[0]


def test_offline_service_uses_only_the_cache(knowledge):
    server = FakeOpgg()
    online = make_service(server)
    online.refresh_lane_meta()
    offline = make_service(None, db=online.db)
    g = game(knowledge=knowledge)
    offline.prefetch(g)  # no client: does nothing
    assert offline.for_game(g).matchups[Role.JUNGLE].games == 3572


# ---------------------------------------------------------------- old patches, thin samples


def fill(db: StatsDb, patch: str) -> None:
    guide = opgg.parse_guide(
        recorded("lane_matchup_guide_LeeSin_vs_Elise_jungle.json")["result"]["content"][0]["text"]
    )
    by_key = {int(r["key"]): r["champ_id"] for r in STATIC["champions.csv"]}
    db.put_guide(dataclasses.replace(guide, patch=patch), "LeeSin", "Elise", by_key, "2026-10-02")


def test_last_patch_only_is_labelled_and_down_weighted(knowledge):
    db = StatsDb(":memory:")
    fill(db, "16.18")
    stats = st.game_stats(db, game(knowledge=knowledge), st.StatsSettings())
    jg = stats.matchups[Role.JUNGLE]
    assert jg.games == 1786 and jg.patch_label == "26.18"
    assert jg.display.endswith("games (26.18)")


def test_changed_champion_ignores_last_patch(knowledge):
    db = StatsDb(":memory:")
    fill(db, "16.18")
    stats = st.game_stats(
        db, game(knowledge=knowledge), st.StatsSettings(), changed=frozenset({"Elise"})
    )
    assert Role.JUNGLE not in stats.matchups


def test_thin_samples_are_not_shown(knowledge):
    db = StatsDb(":memory:")
    fill(db, "16.19")
    stats = st.game_stats(db, game(knowledge=knowledge), st.StatsSettings(min_games_display=5000))
    jg = stats.matchups[Role.JUNGLE]
    assert not jg.shown and st.lane_advantage(jg) is None
    insights = analyze(game(knowledge=knowledge), knowledge, stats)
    text = flat(render_text(select(insights, evaluate(RULES, insights))))
    assert "Lee Sin vs Elise: even (no reliable numbers; going by champion notes)." in text
    assert " games" not in text.split("WARNINGS")[0]


# ---------------------------------------------------------------- stats decide the lane verdict


def matchup(role: Role, advantage: str, games: int = 4000) -> st.MatchupStat:
    return st.MatchupStat(
        role,
        "A",
        "B",
        games,
        0.5,
        0.5,
        0.5,
        0.0,
        games >= 500,
        "50%",
        "",
        Labels(advantage, "", "", ""),
    )


def test_lane_verdict_from_opgg_labels(knowledge):
    insights = analyze(game(knowledge=knowledge), knowledge)
    bot = insights.lanes[Lane.BOT]
    assert bot.verdict == "losing" and bot.source == "traits"
    agree = with_stats(
        bot,
        st.GameStats(
            {Role.BOT: matchup(Role.BOT, "them"), Role.SUPPORT: matchup(Role.SUPPORT, "even")}
        ),
    )
    assert (agree.verdict, agree.source, agree.disagrees) == ("losing", "stats", False)
    flip = with_stats(bot, st.GameStats({Role.BOT: matchup(Role.BOT, "us")}))
    assert flip.verdict == "winning" and flip.disagrees
    assert flip.reasons == ["OP.GG's matchup data gives Jhin/Lulu the early edge"]
    split = with_stats(
        bot,
        st.GameStats(
            {Role.BOT: matchup(Role.BOT, "us"), Role.SUPPORT: matchup(Role.SUPPORT, "them")}
        ),
    )
    assert split is bot  # the ADC and support labels disagree: keep the traits
    thin = with_stats(bot, st.GameStats({Role.BOT: matchup(Role.BOT, "us", games=100)}))
    assert thin is bot


def test_disagreements_are_queued_and_noted(knowledge):
    g = game(knowledge=knowledge)
    stats = st.GameStats({Role.BOT: matchup(Role.BOT, "us")}, scaling={"Jhin": -6.0})
    insights = analyze(g, knowledge, stats)
    found = stats_disagreements(insights)
    assert (
        "Jhin",
        "bot lane vs Samira/Nautilus: OP.GG lane advantage us, traits said losing",
    ) in found
    report = select(insights, evaluate(RULES, insights))
    assert any(
        w.startswith("Bot: OP.GG's matchup data says you win early") for w in report.warnings
    )


def test_stats_paths_in_rule_contexts(knowledge):
    g = game(knowledge=knowledge)
    stats = st.GameStats(
        {Role.TOP: dataclasses.replace(matchup(Role.TOP, "them"), rate=0.471, delta=-0.012)}
    )
    lane = next(
        c
        for c in contexts(analyze(g, knowledge, stats))
        if c.scope == "lane" and c.lane is Lane.TOP
    )
    assert lane.values["stats.matchup_wr"] == 47.1 and lane.values["stats.matchup_games"] == 4000
    assert lane.values["stats.matchup_delta"] == -1.2
    assert lane.values["stats.lane_advantage"] == "them"
    mid = next(
        c
        for c in contexts(analyze(g, knowledge, stats))
        if c.scope == "lane" and c.lane is Lane.MID
    )
    assert mid.values["stats.matchup_wr"] is None


# ---------------------------------------------------------------- scout watch


def test_watch_fetches_during_the_draft_and_reports_with_numbers(knowledge, tmp_path):
    from test_watcher import JUNGLER, loading_roster, make_watcher, replay

    watcher, messages, clock = make_watcher(knowledge, tmp_path)
    server = FakeOpgg()
    watcher.stats = make_service(server)
    watcher.review_queue = tmp_path / "review_queue.csv"
    replay(watcher, clock)
    watcher.process("GameStart", None, loading_roster(smite_on=JUNGLER))  # the report, at loading
    report = next(tmp_path.glob("*.md")).read_text(encoding="utf-8")
    assert server.calls, "prefetch made no calls"
    assert any(t == opgg.GUIDE for t, _ in server.calls)
    assert "Report" in report  # built; this draft's pairs have no recorded guide, so a notice
    assert "Some stats are missing" in report or "No stats yet" in report


def test_numbers_decide_the_early_phases_too(knowledge):
    """A shove lane: OP.GG gives Sivir/Seraphine the lane; the timeline used to say 'you'."""
    g = load_game(
        ROOT / "tests/fixtures/games/bot_shove.yaml", set(knowledge.champions)
    )
    stats = st.GameStats(
        {Role.BOT: matchup(Role.BOT, "them"), Role.SUPPORT: matchup(Role.SUPPORT, "them")}
    )
    ins = analyze(g, knowledge, stats)
    assert ins.lanes[Lane.BOT].verdict == "losing"
    phases = ins.timelines[Lane.BOT].phases
    assert (phases["l1_3"], phases["l3_6"]) == ("them", "them")
    assert phases["item1"] != "us"  # no "keep the early lead" for the side that lost it
    assert ins.skirmishes[Lane.BOT].winner != "us"
    text = flat(render_text(select(ins, evaluate(RULES, ins))))
    assert "levels 1-3: them, levels 3-6: them" in text
    assert ins.lanes[Lane.BOT].label == "survive"  # they push, and OP.GG says they win
    assert "Bot: Sivir/Seraphine push and win the fights" in text


def test_a_losing_lane_isnt_told_to_press(knowledge):
    """Same game: the plan said "Press your early advantage" beside a "Survive" lane. The early
    part is about the whole team, so the bot laners hear about their lane first."""
    g = load_game(
        ROOT / "tests/fixtures/games/bot_shove.yaml", set(knowledge.champions)
    )
    stats = st.GameStats(
        {Role.BOT: matchup(Role.BOT, "them"), Role.SUPPORT: matchup(Role.SUPPORT, "them")}
    )

    def plan(role: Role) -> str:
        ins = analyze(dataclasses.replace(g, my_role=role), knowledge, stats)
        section = next(s for s in select(ins, evaluate(RULES, ins)).sections
                       if s.key == "game_plan")  # fmt: skip
        return section.items[0].text

    assert plan(Role.JUNGLE).startswith("Press your early advantage")  # the team is stronger
    for role in (Role.SUPPORT, Role.BOT):
        assert plan(role).startswith("Hold your lane while the rest of the team uses its early")
