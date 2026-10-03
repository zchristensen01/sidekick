"""Players at the loading screen (M16): OP.GG profiles turned into records on each player's
champion, hidden players skipped, no identifiers anywhere. Recorded OP.GG answer; no network."""

import json
from pathlib import Path
from types import SimpleNamespace

from lcu_fakes import fake_puuid, make_gameflow_session

from scout.data.opgg import ChampRecord, OpggError, Profile, parse_profile
from scout.lcu.watcher import with_players
from scout.model.roles import Role
from scout.player_cards import PlayerCard, Seat, card, gather, seats_at_loading

SOURCES = Path(__file__).parent / "fixtures" / "sources"
BY_KEY = {86: "Garen", 64: "LeeSin", 103: "Ahri", 202: "Jhin", 117: "Lulu", 122: "Darius",
          60: "Elise", 7: "Leblanc", 51: "Caitlyn", 89: "Leona", 75: "Nasus"}  # fmt: skip
NAMES = {c: c for c in BY_KEY.values()} | {"Leblanc": "LeBlanc"}


def recorded() -> Profile:
    message = json.loads((SOURCES / "opgg" / "summoner_profile.json").read_text(encoding="utf-8"))
    return parse_profile(message["result"]["content"][0]["text"])


def test_profile_from_opgg():
    p = recorded()
    assert (p.tier, p.division, p.lp, p.solo_wins, p.solo_losses) == ("PLATINUM", 3, 41, 64, 58)
    assert p.season[75] == ChampRecord(75, 31, 17, 212, 180, 301)  # Nasus: totals, not averages
    assert p.recent[86].games == 6 and sum(r.games for r in p.recent.values()) == 16


def test_a_card_says_it_plainly():
    c = card(Seat("them", 75, "Nasus", "Nasus", Role.TOP, "x"), recorded())
    assert c.rank == "Platinum 3"
    assert c.line() == ("Their Nasus player (Platinum 3): 31 ranked games on Nasus this season, "
                        "55% won; 6.8 / 5.8 / 9.7 average kills / deaths / assists; won 8 of "
                        "their last 16 games.")  # fmt: skip
    few = PlayerCard("us", Role.MID, "Ahri", "Ahri", "Silver 1", ChampRecord(103, 3, 2, 9, 6, 12))
    assert few.champion_text() == "3 ranked games on Ahri this season"  # no % under 5 games
    assert few.view()["win_rate"] is None and few.who == "Your Ahri player"
    new = card(Seat("them", 89, "Leona", "Leona", Role.SUPPORT, "x"), recorded())
    assert "no ranked games on Leona this season" in new.line()
    apex = Profile("MASTER", 1, 120, 10, 5, {}, {})
    assert card(Seat("them", 89, "Leona", "Leona", None, "x"), apex).rank == "Master 120 LP"


def test_seats_at_loading():
    gameflow = make_gameflow_session(phase="GameStart", roster=True)
    gameflow["gameData"]["teamTwo"][2]["puuid"] = ""  # LeBlanc in streamer mode
    roles = {"Elise": Role.JUNGLE, "Jhin": Role.BOT}
    seats = seats_at_loading(gameflow, [86, 64, 103, 202, 117], BY_KEY, NAMES, roles, my_key=64)
    assert len(seats) == 9 and "LeeSin" not in [s.champ_id for s in seats]  # not me
    assert [s.side for s in seats] == ["us"] * 4 + ["them"] * 5
    assert seats[2].role is Role.BOT and seats[5].role is Role.JUNGLE
    assert next(s for s in seats if s.champ_id == "Leblanc").puuid == ""
    assert seats_at_loading({"gameData": {}}, [86], BY_KEY, NAMES, {}, None) == []


def test_gather_skips_hidden_and_survives_errors():
    seats = [Seat("them", 75, "Nasus", "Nasus", Role.TOP, fake_puuid(1)),
             Seat("them", 7, "Leblanc", "LeBlanc", Role.MID, ""),
             Seat("them", 60, "Elise", "Elise", Role.JUNGLE, fake_puuid(2)),
             Seat("us", 202, "Jhin", "Jhin", Role.BOT, fake_puuid(3))]  # fmt: skip
    asked = []

    def riot_id(puuid):
        return None if puuid == fake_puuid(2) else ("Someone", "NA1")

    def profile(name, tag):
        asked.append((name, tag))
        if len(asked) > 1:
            raise OpggError("lol_get_summoner_profile failed: summoner not found")
        return recorded()

    cards = gather(seats, riot_id, profile)
    assert [c.champ_id for c in cards] == ["Nasus", "Leblanc", "Elise", "Jhin"]
    assert cards[0].season and cards[0].season.games == 31
    assert cards[1].note == cards[2].note == "hidden by the game, not checked"
    assert cards[3].note == "not found on OP.GG"
    text = json.dumps([c.view() for c in cards])
    assert "Someone" not in text and fake_puuid(1) not in text  # no identifiers


def test_the_writer_gets_a_players_section_without_names():
    hidden = PlayerCard("them", Role.MID, "Leblanc", "LeBlanc", note="hidden by the game")
    cards = [card(Seat("them", 75, "Nasus", "Nasus", Role.TOP, "x"), recorded()), hidden]
    payload = with_players({"sections": [{"key": "game_plan", "items": []}]}, cards)
    keys = [s["key"] for s in payload["sections"]]
    assert keys == ["game_plan", "players"]
    items = payload["sections"][1]["items"]
    assert [i["source"] for i in items] == ["player:them:top"]  # the hidden one isn't an item
    assert all("id" not in r and "text" not in r for r in payload["players"])
    assert payload["players"][0]["average_kda"] == "6.8 / 5.8 / 9.7"


def test_watch_fetches_players_at_loading_and_waits_to_write(knowledge, tmp_path):
    from test_stats import FakeOpgg, make_service
    from test_watcher import RECORDING, loading_roster, make_watcher, replay

    watcher, messages, clock = make_watcher(knowledge, tmp_path)
    watcher.write_in_background = False
    service = make_service(FakeOpgg())
    service.opgg.profile = lambda name, tag, region: recorded()
    watcher.stats, watcher.opgg_region = service, "NA"
    written = []
    watcher.writer = SimpleNamespace(write=lambda payload: written.append(payload)
                                     or SimpleNamespace(written=None, note="test", cached=False,
                                                        calls=0))  # fmt: skip
    watcher.client = SimpleNamespace(get=lambda path: {"gameName": "Someone", "tagLine": "NA1"})
    views = []
    watcher.on_view = views.append
    replay(watcher, clock)
    roster = loading_roster(smite_on=154)
    for i, player in enumerate(roster["gameData"]["teamOne"] + roster["gameData"]["teamTwo"]):
        player["puuid"] = fake_puuid(i)
    watcher.process("GameStart", None, roster)
    assert written and any(s["key"] == "players" for s in written[-1]["sections"])
    them = [p for p in written[-1]["players"] if p["side"] == "them"]
    assert len(them) == 5
    assert views[-1]["players"] and views[-1]["phase"] == "final"
    saved = next(tmp_path.glob("*.md")).read_text(encoding="utf-8")
    assert "player (Platinum 3)" in saved and "Someone" not in saved
    assert all(fake_puuid(i) not in saved for i in range(10))
    service.close()
    assert len(RECORDING["snapshots"]) > 0
