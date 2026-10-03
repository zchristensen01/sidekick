"""The app's screens (M13): the data the dashboard draws, and the window bridge. No window opens."""

import dataclasses
import json
from pathlib import Path
from types import SimpleNamespace

from scout.analysis.insights import analyze
from scout.app.window import Bridge, Settings, on_screen
from scout.model.gamefile import load_game
from scout.model.roles import Role
from scout.picks import Picker
from scout.report.select import select
from scout.report.validator import parse
from scout.report.view import picks_view, report_view, status_view
from scout.rules.engine import evaluate, load_rules

ROOT = Path(__file__).resolve().parent.parent
RULES = load_rules(ROOT / "scout/rules/league_rules.yaml")


def screens(knowledge, role):
    game = load_game(
        ROOT / "tests/fixtures/games/bot_shove.yaml", set(knowledge.champions)
    )
    ins = analyze(dataclasses.replace(game, my_role=role), knowledge)
    return ins, select(ins, evaluate(RULES, ins))


def test_a_laners_report_screen(knowledge):
    ins, report = screens(knowledge, Role.SUPPORT)
    v = report_view(report, ins, phase="draft")
    json.dumps(v)
    assert v["screen"] == "report" and v["phase"] == "draft" and not v["written"]
    assert v["header"]["side"] == "red" and v["header"]["champion"] == "Braum"
    lane = v["lane"]
    assert lane["label"] == "pushed" and lane["label_text"] == "Pushed in"
    assert lane["push_diff"] == -2.0 and lane["prio"] == "them"  # they push (no stats here)
    assert [o["name"] for o in v["opponents"]] == ["Sivir", "Seraphine"]
    assert v["opponents"][0]["spells"] == ["barrier", "flash"]
    assert v["lanes"] is None  # the lanes-at-a-glance card is the jungler's
    keys = [s["key"] for s in v["sections"]]
    assert "your_lane" not in keys and "jungle" in keys  # own cards are drawn separately
    assert v["team"]["them"]["magic"] >= 1


def test_the_junglers_report_screen(knowledge):
    ins, report = screens(knowledge, Role.JUNGLE)
    v = report_view(report, ins, phase="final", addendum=["a loading-screen line"])
    assert v["lane"] is None and [r["lane"] for r in v["lanes"]["rows"]] == ["top", "mid", "bot"]
    assert {r["gank_rank"] for r in v["lanes"]["rows"]} == {1, 2, 3}
    assert v["opponents"][0]["name"] == "Kayn" and v["addendum"] == ["a loading-screen line"]


def test_the_written_version_replaces_the_lines(knowledge):
    ins, report = screens(knowledge, Role.SUPPORT)
    written = parse(
        {
            "sections": [
                {
                    "key": "game_plan",
                    "lines": [{"text": "Short plan.", "sources": ["insight:game_plan"]}],
                }
            ]
        }
    )
    v = report_view(report, ins, written, "final")
    assert v["written"] and v["plan"] == "Short plan."


def test_the_pick_screen(knowledge):
    game = load_game(
        ROOT / "tests/fixtures/games/bot_shove.yaml", set(knowledge.champions)
    )
    drafting = dataclasses.replace(
        game, my_role=Role.JUNGLE, ally={r: p for r, p in game.ally.items() if r is not Role.JUNGLE}
    )
    picker = Picker(knowledge=knowledge, pool={Role.JUNGLE: ("LeeSin", "Amumu")})
    v = picks_view(picker.suggest(drafting), drafting, {"Kayn": "Kayn"})
    json.dumps(v)
    assert v["screen"] == "picks" and [o["name"] for o in v["options"]] == ["Lee Sin", "Amumu"]
    assert v["options"][0]["main"] and v["draft"]["me"] == "jungle"
    jungle = next(s for s in v["draft"]["ally"] if s["role"] == "jungle")
    assert jungle["name"] is None  # not locked yet


def test_status_screen():
    assert status_view("waiting_game", "Connected.") == {
        "screen": "status",
        "state": "waiting_game",
        "message": "Connected.",
    }


def test_bridge_hands_each_screen_once():
    bridge = Bridge()
    first = bridge.poll(-1)
    assert first["view"] is None and first["version"] == 0
    bridge.show({"screen": "status"})
    bridge.status("hello")
    got = bridge.poll(0)
    assert got["view"] == {"screen": "status"} and got["message"] == "hello"
    assert bridge.poll(got["version"])["view"] is None  # nothing new


def test_window_settings(tmp_path):
    path = tmp_path / "app.json"
    s = Settings(path)
    assert s.data["width"] == 1280
    s.data.update(x=2000, y=50)
    s.save()
    assert Settings(path).data["x"] == 2000
    path.write_text('{"x": 5, "scale": 1.3}', encoding="utf-8")  # the old text size is dropped
    assert "scale" not in Settings(path).data
    path.write_text("not json", encoding="utf-8")
    assert Settings(path).data["x"] is None
    screen = SimpleNamespace(x=0, y=0, width=1920, height=1080)
    second = SimpleNamespace(x=1920, y=0, width=1920, height=1080)
    assert on_screen(2000, 50, 1280, [screen, second]) and not on_screen(2000, 50, 1280, [screen])
    assert not on_screen(None, None, 1280, [screen])


def test_both_teams_panel_and_opponent_kits(knowledge):
    """M17: every champion in Riot's and the wiki's words; lane opponents' kit on the main
    view (both enemies in bot lane), shortened to Riot's first sentence, never reworded."""
    from scout.report.view import first_sentence

    rows = (
        {"champ_id": "Sivir", "slot": "Q", "name": "Boomerang Blade",
         "description": "Sivir hurls her crossblade. It returns to her.", "cooldowns": ""},
        {"champ_id": "Sivir", "slot": "P", "name": "Fleet of Foot",
         "description": "Sivir gains Move Speed.", "cooldowns": ""},
    )  # fmt: skip
    k = dataclasses.replace(knowledge, abilities={"Sivir": rows},
                            tips={("Sivir", "enemy"): ("Dodge the blade.",)})  # fmt: skip
    ins, report = screens(k, Role.SUPPORT)
    v = report_view(report, ins, phase="final")
    sivir = next(o for o in v["opponents"] if o["name"] == "Sivir")
    assert sivir["kit"] == [{"slot": "Q", "name": "Boomerang Blade",
                             "text": "Sivir hurls her crossblade."}]  # fmt: skip
    kits = {x["name"]: x for x in v["kits"]}
    assert len(kits) == 10 and {x["side"] for x in kits.values()} == {"us", "them"}
    assert [a["slot"] for a in kits["Sivir"]["abilities"]] == ["Q", "P"]
    assert kits["Sivir"]["tips"] == ["Dodge the blade."] and kits["Sivir"]["tips_kind"] == "against"
    assert {"name": "Mobility", "level": "low"} in kits["Sivir"]["ratings"]  # Riot's word
    assert first_sentence("No full stop here") == "No full stop here"


def test_the_writer_gets_every_champion(knowledge):
    from scout.report.builder import build_input

    ins, report = screens(knowledge, Role.SUPPORT)
    payload = build_input(report, ins, knowledge, 120)
    assert len(payload["facts"]) == 10  # not only the champions an item mentions
    enemies = [f for f in payload["facts"].values() if f["side"] == "enemy"]
    assert all("riot_tips_against" in f for f in enemies)
    assert all("riot_ratings" in f and "wiki_mechanics" in f for f in payload["facts"].values())
