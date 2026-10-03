"""Measured data (M19): figures from Riot's match data, counted once, the collector's ladder
walk, the written level rule, coverage and the OP.GG cross-check, and the figures reaching the
analysis and the writer. A recorded, scrubbed real game and fakes; no network."""

import dataclasses
import json
from datetime import UTC, datetime
from pathlib import Path

from scout.analysis import stats as st
from scout.analysis.insights import analyze
from scout.analysis.measured import MIN_GAMES, Figures, coverage, cross_check, figures_for
from scout.data.collector import Collector
from scout.data.measure import measure, patch_of
from scout.data.riot import RiotError
from scout.data.stats_db import StatsDb
from scout.model.gamefile import load_game
from scout.model.roles import Role
from scout.report.builder import build_input
from scout.report.select import select

ROOT = Path(__file__).resolve().parent.parent
FIXTURE = ROOT / "tests" / "fixtures" / "postgame"
NOW = datetime(2026, 10, 4, 12, 0, tzinfo=UTC)
FINISHED = frozenset({3078, 6655, 3031, 6653, 3157, 3068, 2504, 3001, 3071, 3065})


def recorded():
    return (json.loads((FIXTURE / "match.json").read_text(encoding="utf-8")),
            json.loads((FIXTURE / "timeline.json").read_text(encoding="utf-8")))  # fmt: skip


def by_key(knowledge):
    return {f.key: c for c, f in knowledge.champions.items()}


def test_one_game_measured(knowledge):
    match, timeline = recorded()
    measured = measure(match, timeline, by_key(knowledge), FINISHED)
    players = {(p.champ_id, p.role): p.figures for p in measured}
    assert len(players) == 10 and patch_of(match) == "16.19"
    karma, neeko = players[("Karma", Role.MID)], players[("Neeko", Role.MID)]
    assert karma["gold_diff_10"] == 1058 and neeko["gold_diff_10"] == -1058  # mirrored
    assert karma["win"] == 1 and neeko["win"] == 0
    assert karma["level3_s"] == 122.0 or round(karma["level3_s"]) == 122
    assert 0 <= karma["push_3_10"] <= 1 and "push_3_10" not in players[("Ambessa", Role.JUNGLE)]
    assert karma["roam_takedowns_14"] == 3 and karma["takedowns_14"] == 7
    assert "roam_takedowns_14" not in players[("Jax", Role.JUNGLE)]
    short = {**match, "info": {**match["info"], "gameDuration": 600}}
    assert measure(short, timeline, by_key(knowledge), FINISHED) == []  # too short to count


def test_a_game_counts_once():
    db = StatsDb(":memory:")
    p = [type("P", (), {"champ_id": "Mel", "role": Role.MID, "figures": {"win": 1.0}})()]
    assert db.add_game("h1", "16.19", p, "t") is True
    assert db.add_game("h1", "16.19", p, "t") is False
    assert db.measured("16.19")[("Mel", Role.MID)]["win"] == (1, 1.0, 0.0)
    assert db.collected_games("16.19") == 1 and db.seen("h1")


class FakeRiot:
    """Two ladder pages; three games per player; one game from an old patch."""

    def __init__(self, fail_after: int | None = None) -> None:
        self.calls, self.fail_after = [], fail_after
        self.match_data, self.timeline_data = recorded()

    def _count(self, what):
        self.calls.append(what)
        if self.fail_after is not None and len(self.calls) > self.fail_after:
            raise RiotError("Riot API key rejected")

    def ladder(self, tier, division, page):
        self._count(("ladder", tier, division, page))
        return [f"p{page}a", f"p{page}b"] if page <= 2 else []

    def solo_ids(self, puuid, count, since):
        self._count(("ids", puuid))
        return [f"NA1_{puuid}_{i}" for i in range(count)]

    def match(self, match_id):
        self._count(("match", match_id))
        if match_id.endswith("_2"):
            return {"info": {**self.match_data["info"], "gameVersion": "15.1.1.1"}}
        return self.match_data

    def timeline(self, match_id):
        self._count(("timeline", match_id))
        return self.timeline_data


def test_the_collector_walks_the_ladder_and_counts_each_game_once(knowledge):
    db = StatsDb(":memory:")
    riot = FakeRiot()
    c = Collector(riot, db, by_key(knowledge), FINISHED, ("16.19", "16.18"), now=lambda: NOW,
                  shuffle=lambda players: None)  # fmt: skip
    first = c.run(games=3)
    assert first.added == 3 and first.old_patch == 1 and first.by_patch == {"16.19": 3}
    assert ("ladder", "CHALLENGER", "I", 1) in riot.calls
    again = Collector(riot, db, by_key(knowledge), FINISHED, ("16.19",), now=lambda: NOW,
                      shuffle=lambda players: None).run(games=1)  # fmt: skip
    assert again.added == 1 and ("ladder", "GRANDMASTER", "I", 1) in riot.calls  # next tier
    assert db.collected_games("16.19") == 4
    stored = repr(db.measured("16.19"))
    assert "p1a" not in stored and "NA1_" not in stored  # no player or game ids kept
    broken = Collector(FakeRiot(fail_after=1), StatsDb(":memory:"), by_key(knowledge), FINISHED,
                       ("16.19",), now=lambda: NOW).run(games=5)  # fmt: skip
    assert broken.added == 0 and "rejected" in broken.error


def table(n: int = MIN_GAMES):
    """Ten junglers and ten mids with spread-out figures, plus one off-role pick."""
    rows = {}
    for i, champ in enumerate(["Elise", "LeeSin", "Amumu", "Vi", "XinZhao", "JarvanIV", "Kayn",
                               "Nocturne", "Hecarim", "Rammus"]):  # fmt: skip
        rows[(champ, Role.JUNGLE)] = {"win": (n, 0.5, 0.5), "level4_s": (n, 190.0 + i * 5, 4.0),
                                      "gold_diff_10": (n, 100.0 - i * 20, 50.0)}  # fmt: skip
    for i, champ in enumerate(["Ahri", "Zed", "Mel", "Hwei", "Vex", "Galio", "Lux", "Syndra",
                               "Viktor", "Orianna"]):  # fmt: skip
        rows[(champ, Role.MID)] = {"win": (n, 0.5, 0.5), "push_3_10": (n, 0.3 + i * 0.03, 0.1),
                                   "roam_takedowns_14": (n, 0.5 + i * 0.1, 0.5)}  # fmt: skip
    rows[("Jinx", Role.MID)] = {"win": (n, 0.4, 0.5), "push_3_10": (n, 0.9, 0.1)}
    return rows


SHARES = {c: {Role.JUNGLE: 0.9} for c in ["Elise", "LeeSin", "Amumu", "Vi", "XinZhao", "JarvanIV",
                                         "Kayn", "Nocturne", "Hecarim", "Rammus"]}  # fmt: skip
SHARES |= {c: {Role.MID: 0.9} for c in ["Ahri", "Zed", "Mel", "Hwei", "Vex", "Galio", "Lux",
                                        "Syndra", "Viktor", "Orianna"]}  # fmt: skip
SHARES["Jinx"] = {Role.BOT: 0.95, Role.MID: 0.03}


def test_levels_follow_the_written_rule():
    t = table()
    fast = figures_for(t, "Elise", Role.JUNGLE, "16.19", SHARES)
    slow = figures_for(t, "Rammus", Role.JUNGLE, "16.19", SHARES)
    assert fast.levels["clear"] == 3 and slow.levels["clear"] == 0  # level 4 soonest = fastest
    assert any(line.startswith("jungle clear: among the fastest (top quarter)")
               for line in fast.lines())  # fmt: skip
    assert fast.levels["early"] == 3 and slow.levels["early"] == 0
    orianna = figures_for(t, "Orianna", Role.MID, "16.19", SHARES)
    assert orianna.levels["waveclear"] == 3  # Jinx mid (off-role) isn't in the ranking
    assert "clear" not in orianna.levels  # a clear is a jungler's
    assert figures_for(table(MIN_GAMES - 1), "Elise", Role.JUNGLE, "16.19", SHARES) is None
    assert any("level 4 at 3:10" in line for line in fast.lines())
    assert fast.source() == f"Riot match data, Emerald+, patch 16.19, {MIN_GAMES:,} games"


def test_coverage_and_the_opgg_cross_check():
    have, wanted, missing = coverage(table(), SHARES)
    assert (have, wanted) == (20, 21) and missing == ["Jinx bot"]
    rows = cross_check(table(), {("Ahri", Role.MID): (1000, 600), ("Zed", Role.MID): (1000, 500)})
    assert rows[0][:2] == ("Ahri", Role.MID) and round(rows[0][3], 2) == 0.6  # biggest gap first


def test_measured_figures_reach_the_lane_model_and_the_writer(knowledge):
    g = load_game(ROOT / "tests/fixtures/games/samira_naut.yaml", set(knowledge.champions))
    figures = Figures(812, {"gold_diff_10": 140.0, "gold_diff_15": 260.0, "win": 0.53},
                      {"early": 3, "waveclear": 1, "roam": 2}, "16.19")  # fmt: skip
    stats = st.GameStats(measured={("Ahri", Role.MID): figures})
    ins = analyze(dataclasses.replace(g, my_role=Role.MID), knowledge, stats)
    ahri = ins.lineup.us[Role.MID]
    assert (ahri.early, ahri.waveclear, ahri.roam) == (3, 1, 2)
    assert ahri.source_of("early") == "riot-measured"
    payload = build_input(select(ins, []), ins, knowledge, 120)
    measured = payload["facts"]["Ahri"]["measured"]
    assert measured["source"] == "Riot match data, Emerald+, patch 16.19, 812 games"
    assert "gold vs lane opponent: +140 at 10 minutes, +260 at 15" in measured["figures"]



def test_owners_own_row_keeps_its_values_over_measured_levels(knowledge):
    """A row the owner wrote (source=owner) beats every source (TRAITS.md); the measured figures are
    still quoted (the audit's catch, 2026-10-03)."""
    g = load_game(ROOT / "tests/fixtures/games/samira_naut.yaml", set(knowledge.champions))
    figures = Figures(812, {"gold_diff_10": 140.0, "win": 0.53},
                      {"early": 3, "waveclear": 1, "roam": 2}, "16.19")  # fmt: skip
    stats = st.GameStats(measured={("Ahri", Role.MID): figures})
    traits = dict(knowledge.traits)
    key = next(k for k in traits if k[0] == "Ahri")
    traits[key] = dataclasses.replace(traits[key], source="owner", early=1, waveclear=2, roam=0,
                                      sources=(("all", "owner"),))  # as loading marks it
    mine = dataclasses.replace(knowledge, traits=traits)
    ahri = analyze(dataclasses.replace(g, my_role=Role.MID), mine, stats).lineup.us[Role.MID]
    assert (ahri.early, ahri.waveclear, ahri.roam) == (1, 2, 0)
    assert ahri.measured  # the figures still travel to the writer


def test_measured_figures_count_by_riots_patch_even_without_opgg_numbers(knowledge):
    """They're stored under Riot's patch (the game's version), so they count while OP.GG has no
    numbers yet or still serves last patch (the audit's catch, 2026-10-03)."""
    db = StatsDb(":memory:")
    rows = [("16.19", "Ahri", "mid", "win", 60, 33.0, 33.0),
            ("16.19", "Ahri", "mid", "gold_diff_10", 60, 6000.0, 700000.0)]  # fmt: skip
    db._db.executemany("INSERT INTO measured VALUES (?,?,?,?,?,?,?)", rows)
    g = load_game(ROOT / "tests/fixtures/games/samira_naut.yaml", set(knowledge.champions))
    stats = st.game_stats(db, g, st.StatsSettings())
    assert not stats.matchups  # no OP.GG numbers at all
    assert stats.measured[("Ahri", Role.MID)].games == 60

def test_changes_since_last_patch_ignore_noise():
    from scout.analysis.measured import changes

    now = {("Lillia", Role.JUNGLE): {"win": (400, 0.5, 0.5), "level4_s": (400, 200.0, 10.0),
                                     "gold_diff_10": (400, 21.0, 300.0)},
           ("Kayn", Role.JUNGLE): {"win": (30, 0.5, 0.5), "level4_s": (30, 180.0, 10.0)}}
    before = {("Lillia", Role.JUNGLE): {"win": (400, 0.5, 0.5), "level4_s": (400, 209.0, 10.0),
                                        "gold_diff_10": (400, 20.0, 300.0)},
              ("Kayn", Role.JUNGLE): {"win": (300, 0.5, 0.5), "level4_s": (300, 220.0, 10.0)}}
    found = changes(now, before, "16.18")
    # the gold move is within noise; Kayn has too few games this patch
    assert [(c.champ, c.metric) for c in found] == [("Lillia", "level4_s")]
    assert found[0].text() == "reaches level 4 at 3:20, 9 seconds sooner than patch 16.18 (3:29)"
