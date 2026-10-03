"""Pick suggestions (M9b, docs/COUNTERPICK.md): opponent locked, blind, empty pool (autofill),
off-pool lock, comfort tiebreaks, `scout watch` and `scout pool`. Recorded OP.GG data only."""

import dataclasses
from pathlib import Path

import pytest
from test_stats import STATIC, FakeOpgg, make_service

from scout.analysis.stats import Lookup
from scout.config import load_config
from scout.model.gamefile import load_game
from scout.model.roles import Role
from scout.picks import (
    Candidate,
    Option,
    Picker,
    _rank,
    mastery_by_role,
    parse_mastery,
    render,
)
from scout.pool import load_pool, save_pool

ROOT = Path(__file__).resolve().parent.parent
POOL = {Role.JUNGLE: ("LeeSin", "Elise", "Amumu")}


@pytest.fixture(scope="module")
def service():
    s = make_service(FakeOpgg())
    s.refresh_lane_meta()  # lane stats + Lee Sin's full jungle matchup table
    return s


def picker(knowledge, service, pool=POOL, mastery=()) -> Picker:
    return Picker(
        knowledge=knowledge,
        pool=pool,
        meta_rows=STATIC["champion_meta.csv"],
        mastery=mastery,
        role_rates=service.role_rates(),
        lookup=lambda: Lookup(service.db, "16.19.1", service.settings),
    )


def drafting(knowledge, my_role=Role.JUNGLE, enemy_locked=True):
    """samira_naut before I lock: my role is empty; the enemy in my role locked or not."""
    game = load_game(ROOT / "tests/fixtures/games/samira_naut.yaml", set(knowledge.champions))
    ally = {r: p for r, p in game.ally.items() if r is not my_role}
    enemy = (
        game.enemy if enemy_locked else {r: p for r, p in game.enemy.items() if r is not my_role}
    )
    return dataclasses.replace(game, my_role=my_role, ally=ally, enemy=enemy)


def test_opponent_locked(knowledge, service):
    s = picker(knowledge, service).suggest(drafting(knowledge))
    assert s.opponent == "Elise"
    assert [o.name for o in s.options] == ["Lee Sin", "Amumu"]  # Elise is taken by them
    text = render(s)
    assert text.startswith("Pick options for jungle into Elise\n")
    assert "- Lee Sin: slight disadvantage into Elise (48% over 3,572 games); your main" in text
    assert "- Amumu: no reliable numbers into Elise" in text
    assert "Options, not orders" in text


def test_blind_pick_ranks_by_safety(knowledge, service):
    s = picker(knowledge, service).suggest(drafting(knowledge, enemy_locked=False))
    assert s.opponent == ""
    lee = next(o for o in s.options if o.name == "Lee Sin")
    hard, checked = lee.blind
    assert checked >= 5 and 0 <= hard <= checked
    text = render(s)
    assert text.startswith("Pick options for jungle (their jungle isn't locked yet)")
    assert "- Lee Sin: " in text and " blind (49% over " in text  # games shown (STATS.md)
    assert " games; hard-countered by " in text


def test_autofill_uses_mastery_then_easy_strong_champions(knowledge, service):
    game = drafting(knowledge, my_role=Role.TOP, enemy_locked=False)
    rates = service.role_rates()
    by_role = mastery_by_role([("Garen", 90000), ("Nautilus", 50000)], rates)
    assert by_role[Role.TOP][:1] == ["Garen"] and "Nautilus" in by_role[Role.SUPPORT]
    taken = dataclasses.replace(game, ally={**game.ally}, enemy={})
    s = picker(knowledge, service, pool={}, mastery=[("Garen", 90000)]).suggest(taken)
    sources = [o.candidate.source for o in s.options]
    assert "mastery" in sources and len(sources) >= 2  # one most-played, topped up: options
    assert "you play it a lot" in render(s) and "these are your most-played" in s.note

    s = picker(knowledge, service, pool={}).suggest(game)
    assert s.options and all(o.candidate.source == "meta" for o in s.options)
    easy = {r["champ_id"] for r in STATIC["champion_meta.csv"] if r["difficulty"] == "1"}
    assert all(o.candidate.champ in easy for o in s.options)
    assert "outside your pool" in render(s)
    assert s.note == "No pool or history for top: strong, easy champions this patch."


def test_nothing_known_says_so(knowledge):
    empty = Picker(knowledge=knowledge, pool={})
    s = empty.suggest(drafting(knowledge))
    assert s.options == () and "No champion pool for jungle" in s.note
    assert "- Nothing to suggest yet." in render(s)


def test_comfort_breaks_near_ties():
    def option(champ, comfort, rate):
        return Option(Candidate(champ, "pool", comfort), champ, "even", rate, "")

    ranked = _rank(
        [option("A", 2, 0.505), option("B", 0, 0.500), option("C", 1, 0.480), option("D", 3, None)]
    )
    assert [o.name for o in ranked] == ["B", "A", "C", "D"]  # B within 1 point of A, and comfier


def test_team_fit_reason(knowledge, service):
    game = drafting(knowledge, my_role=Role.MID)  # allies Garen, Lee Sin, Jhin, Lulu
    s = picker(knowledge, service, pool={Role.MID: ("Ahri", "Yasuo")}).suggest(game)
    ahri = next(o for o in s.options if o.name == "Ahri")
    assert ahri.reason == "adds magic damage to a mostly physical team"


def test_mastery_from_the_client():
    raw = [{"championId": 64, "championPoints": 1200}, {"championId": 9999}, "junk"]
    assert parse_mastery(raw, {64: "LeeSin"}) == [("LeeSin", 1200)]
    assert parse_mastery(None, {64: "LeeSin"}) == []


def test_watch_shows_options_until_i_lock(knowledge, tmp_path, service):
    from test_watcher import JUNGLER, loading_roster, make_watcher, replay

    watcher, messages, clock = make_watcher(knowledge, tmp_path)
    watcher.picker = picker(knowledge, service, pool={Role.JUNGLE: ("LeeSin", "Amumu")})
    shown = []
    watcher.on_report = lambda title, text: shown.append(title)
    replay(watcher, clock)
    assert shown[0] == "Pick options (jungle)"
    assert all(t.startswith("Pick options") for t in shown)  # no report in champ select
    blocks = [m for m in messages if m.startswith("Pick options for jungle")]
    assert len(blocks) >= 2  # they update as the draft goes on
    assert "(their jungle isn't locked yet)" in blocks[0]
    assert blocks[-1].startswith("Pick options for jungle into Gragas (a guess")
    watcher.process("GameStart", None, loading_roster(smite_on=JUNGLER))  # the report, at loading
    report = next(tmp_path.glob("*.md")).read_text(encoding="utf-8")
    assert "Jax isn't in your jungle pool (the Champions button adds it)." in report


def test_scout_pool_command(scout_home, monkeypatch):
    from typer.testing import CliRunner

    import scout.cli

    monkeypatch.setattr(scout.cli, "discover", lambda path: None)  # no League client in tests
    save_pool(scout_home.pool_file, {Role.JUNGLE: {"LeeSin": 3, "Elise": 3, "Amumu": 3}})
    runner = CliRunner()
    shown = runner.invoke(scout.cli.app, ["pool", "--show"])
    assert shown.exit_code == 0, shown.output
    assert "jungle   Lee Sin, Elise, Amumu" in shown.output
    # top: keep; jungle: replace; mid, bot: keep; support: type two; then confirm
    answers = "\nLee Sin, elise\n\n\nNautilus, Gnar\ny\n"
    result = runner.invoke(scout.cli.app, ["pool"], input=answers)
    assert result.exit_code == 0, result.output
    assert "Saved (new champions are rated 3 of 5" in result.output
    pool = load_pool(scout_home.pool_file)  # pool.yaml now; config.yaml is untouched
    assert pool[Role.JUNGLE] == {"LeeSin": 3, "Elise": 3}
    assert pool[Role.SUPPORT] == {"Nautilus": 3, "Gnar": 3}
    assert load_config(scout_home.config_file).player.champ_pool[Role.SUPPORT] == ()
    bad = runner.invoke(scout.cli.app, ["pool"], input="\nNotAChamp\n\n\n\n")
    assert "Not champions: NotAChamp; kept the old list." in bad.output
