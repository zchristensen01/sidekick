"""Each account's champions and the Champions page's suggestions (M22). No network: the League
client is a fake, shaped like its answers (made-up ids)."""

from types import SimpleNamespace

import pytest
import yaml

from scout.accounts import (
    RECENT_MIN,
    Account,
    Accounts,
    file_name,
    logged_in,
    mastery_ideas,
    merged,
    platform_of,
    recent_counts,
    recent_games,
    recent_ideas,
)
from scout.app.main import App
from scout.config import load_config
from scout.lcu.client import CHAMPION_MASTERY, CURRENT_SUMMONER, RECENT_GAMES, LcuUnavailable
from scout.model.roles import Role
from scout.pool import PoolError, load_pool, save_pool

PLAYER = Account("puuid-player-00000000", "Player#NA1")
ALT = Account("puuid-alt-00000000000", "Alt#EUW")
BY_KEY = {64: "LeeSin", 141: "Kayn", 103: "Ahri", 75: "Nasus", 60: "Elise", 150: "Gnar"}
RATES = {"LeeSin": {Role.JUNGLE: 0.95}, "Kayn": {Role.JUNGLE: 0.97}, "Ahri": {Role.MID: 0.9},
         "Nasus": {Role.TOP: 0.8, Role.JUNGLE: 0.15}, "Elise": {Role.JUNGLE: 0.8},
         "Gnar": {Role.TOP: 0.9}}  # fmt: skip


def game(champ_key, lane="JUNGLE", role="NONE", map_id=11, mode="CLASSIC", kind="MATCHED_GAME"):
    """One game as the client's match history lists it: only my own row."""
    return {"gameId": 1, "mapId": map_id, "gameMode": mode, "gameType": kind,
            "participantIdentities": [{"participantId": 1, "player": {"puuid": PLAYER.puuid}}],
            "participants": [{"participantId": 1, "championId": champ_key,
                              "timeline": {"lane": lane, "role": role}}]}  # fmt: skip


# ---------------------------------------------------------------- accounts and their files


def test_logged_in_reads_the_current_summoner():
    raw = {"puuid": PLAYER.puuid, "gameName": "Player", "tagLine": "NA1", "summonerId": 7}
    assert logged_in(raw) == PLAYER
    assert logged_in({"puuid": "x" * 20, "displayName": "Old Name"}).riot_id == "Old Name"
    assert logged_in({"gameName": "Player"}) is None and logged_in(None) is None


def test_file_names_are_safe_and_unique():
    assert file_name("Player#NA1", set()) == "Player_NA1.yaml"
    # Windows ignores case
    assert file_name("Player#NA1", {"player_na1.yaml"}) == "Player_NA1_2.yaml"
    assert file_name("a/b\\c:d#TAG", set()) == "a_b_c_d_TAG.yaml"
    assert file_name("Café Crème#EUW", set()) == "Café_Crème_EUW.yaml"
    assert file_name("###", set()) == "account.yaml"


def test_each_account_starts_from_pool_yaml_then_keeps_its_own(tmp_path):
    accounts = Accounts(tmp_path / "pools")
    starting = lambda: {Role.JUNGLE: {"LeeSin": 5}}  # noqa: E731
    accounts.remember(PLAYER, starting)
    accounts.remember(ALT, starting)
    assert accounts.load(PLAYER)[Role.JUNGLE] == {"LeeSin": 5}  # both start from pool.yaml
    accounts.save(PLAYER, {Role.JUNGLE: {"LeeSin": 5, "Elise": 4}})
    accounts.save(ALT, {Role.MID: {"Ahri": 3}})
    accounts.remember(PLAYER, dict)  # a later login never resets the list
    assert accounts.load(PLAYER)[Role.JUNGLE] == {"LeeSin": 5, "Elise": 4}
    assert accounts.load(ALT)[Role.JUNGLE] == {} and accounts.load(ALT)[Role.MID] == {"Ahri": 3}
    assert accounts.path(PLAYER).name == "Player_NA1.yaml"
    assert accounts.path(ALT).name == "Alt_EUW.yaml"
    assert accounts.last() == PLAYER  # the one logged in last
    assert accounts.get(PLAYER.puuid) == PLAYER and accounts.get("nobody") is None


def test_a_riot_id_change_keeps_the_list(tmp_path):
    accounts = Accounts(tmp_path)
    accounts.remember(PLAYER, lambda: {Role.TOP: {"Gnar": 2}})
    renamed = Account(PLAYER.puuid, "Renamed#NA1")
    accounts.remember(renamed, dict)
    assert accounts.load(renamed)[Role.TOP] == {"Gnar": 2}
    assert accounts.get(PLAYER.puuid).riot_id == "Renamed#NA1"
    index = yaml.safe_load((tmp_path / "accounts.yaml").read_text(encoding="utf-8"))
    assert index["accounts"][PLAYER.puuid]["file"] == "Player_NA1.yaml"


def test_pool_yaml_is_read_only_for_a_new_account(tmp_path):
    accounts = Accounts(tmp_path)
    accounts.remember(PLAYER, lambda: {Role.TOP: {"Gnar": 2}})

    def broken():
        raise PoolError("pool.yaml isn't valid YAML")

    accounts.remember(PLAYER, broken)  # a known account never reads it: a broken file can't block
    assert accounts.load(PLAYER)[Role.TOP] == {"Gnar": 2}
    with pytest.raises(PoolError):
        accounts.remember(ALT, broken)


def test_declined_suggestions_are_kept_per_account_and_lane(tmp_path):
    accounts = Accounts(tmp_path)
    accounts.remember(PLAYER, dict)
    accounts.remember(ALT, dict)
    accounts.decline(PLAYER, Role.JUNGLE, "Kayn")
    accounts.decline(PLAYER, Role.JUNGLE, "Kayn")  # twice is once
    assert accounts.declined(PLAYER) == {(Role.JUNGLE, "Kayn")}
    assert accounts.declined(ALT) == set()


def test_every_pool_merges_at_the_best_rating(tmp_path):
    accounts = Accounts(tmp_path)
    accounts.remember(PLAYER, lambda: {Role.JUNGLE: {"LeeSin": 5}})
    accounts.remember(ALT, lambda: {Role.JUNGLE: {"LeeSin": 2, "Elise": 3}})
    every = merged([{Role.TOP: {"Gnar": 1}}, *accounts.every_pool()])
    assert every[Role.JUNGLE] == {"LeeSin": 5, "Elise": 3} and every[Role.TOP] == {"Gnar": 1}


# ---------------------------------------------------------------- suggestions


def test_recent_games_reads_either_shape():
    assert recent_games({"games": {"games": [game(64), "junk"]}}) == [game(64)]
    assert recent_games({"games": [game(64)]}) == [game(64)]
    assert recent_games({"error": "nope"}) is None and recent_games([]) is None


def test_platform_of_recent_games():
    games = [dict(game(64), platformId="EUW1"), dict(game(64), platformId="EUW1"),
             dict(game(64), platformId="NA1"), game(64)]  # fmt: skip
    assert platform_of(games) == "euw1"
    assert platform_of([game(64)]) is None and platform_of([]) is None


def test_recent_counts_by_lane_on_summoners_rift_only():
    games = [game(141), game(141, lane="NONE"),  # no lane: Kayn's main lane (jungle)
             game(103, lane="MIDDLE"), game(103, lane="MID"),
             game(75, lane="TOP"), game(75, lane="JUNGLE"),
             game(60, lane="BOTTOM", role="DUO_SUPPORT"), game(150, lane="BOTTOM", role="DUO"),
             game(64, map_id=12, mode="ARAM"), game(64, mode="URF"), game(64, kind="CUSTOM_GAME"),
             game(999)]  # fmt: skip
    counts, counted = recent_counts(games, PLAYER.puuid, BY_KEY, RATES)
    assert counted == 7  # not ARAM, URF, a custom game, an unknown champion or an unclear lane
    assert counts[(Role.JUNGLE, "Kayn")] == 2 and counts[(Role.MID, "Ahri")] == 2
    assert counts[(Role.TOP, "Nasus")] == 1 and counts[(Role.JUNGLE, "Nasus")] == 1
    assert counts[(Role.SUPPORT, "Elise")] == 1
    assert counts[(Role.BOT, "Gnar")] == 0  # bottom, unclear role, no bot or support rate
    two = game(141)
    two["participants"] = [*two["participants"], {"participantId": 2, "championId": 64}]
    assert recent_counts([two], PLAYER.puuid, BY_KEY, RATES)[1] == 1  # my row, by my puuid
    two["participantIdentities"] = [{"participantId": 2, "player": {"puuid": "someone-else"}}]
    assert recent_counts([two], PLAYER.puuid, BY_KEY, RATES)[1] == 0  # neither row is mine
    alone = dict(game(141), participantIdentities=[])  # this list is only ever my own games
    assert recent_counts([alone], PLAYER.puuid, BY_KEY, RATES)[1] == 1


def test_recent_ideas_need_more_than_three_games_in_a_lane():
    counts = {(Role.JUNGLE, "Kayn"): 5, (Role.MID, "Ahri"): RECENT_MIN - 1,
              (Role.JUNGLE, "LeeSin"): 9, (Role.TOP, "Nasus"): RECENT_MIN,
              (Role.JUNGLE, "Elise"): 4}  # fmt: skip
    pool = {Role.JUNGLE: {"LeeSin": 5}, Role.TOP: {}}
    ideas = recent_ideas(counts, pool, {(Role.JUNGLE, "Elise")})
    assert RECENT_MIN == 4  # "more than 3 times"
    assert ideas == [(Role.JUNGLE, "Kayn", 5), (Role.TOP, "Nasus", 4)]


def test_mastery_ideas_skip_listed_champions_and_name_a_lane():
    mastery = [("Gnar", 900), ("LeeSin", 800), ("Nasus", 700), ("Ahri", 600), ("Unknown", 500)]
    pool = {Role.JUNGLE: {"LeeSin": 5}}
    ideas = mastery_ideas(mastery, RATES, pool, {(Role.MID, "Ahri")})
    assert ideas == [(Role.TOP, "Gnar", 900), (Role.TOP, "Nasus", 700)]
    assert mastery_ideas(mastery, RATES, pool, set(), limit=1) == [(Role.TOP, "Gnar", 900)]


# ---------------------------------------------------------------- the app's Champions page


class FakeClient:
    """The League client's answers; `who` = None means it's closed."""

    def __init__(self):
        self.who: Account | None = PLAYER
        self.games = [game(60)] * 5 + [game(150, lane="TOP")] * 3
        self.mastery = [{"championId": 150, "championPoints": 90000},
                        {"championId": 64, "championPoints": 80000}]  # fmt: skip

    def get(self, path):
        if self.who is None:
            raise LcuUnavailable("League client not running")
        if path == CURRENT_SUMMONER:
            name, tag = self.who.riot_id.split("#")
            return {"puuid": self.who.puuid, "gameName": name, "tagLine": tag}
        if path == RECENT_GAMES:
            return {"games": {"games": self.games}}
        if path == CHAMPION_MASTERY:
            return self.mastery
        raise AssertionError(path)


@pytest.fixture
def app(scout_home):
    app = App(scout_home)
    client = FakeClient()
    picker = SimpleNamespace(pool={})
    watcher = SimpleNamespace(index=SimpleNamespace(by_key=BY_KEY), rates=RATES, picker=picker,
                              state="idle", riot=None, idle=lambda: True)  # fmt: skip
    app.session = SimpleNamespace(client=client, watcher=watcher)
    save_pool(scout_home.pool_file, {Role.JUNGLE: {"LeeSin": 5}})  # the list from before
    return app


def test_champions_page_follows_the_logged_in_account(app, scout_home):
    page = app.action("champions", {})
    assert page["account"] == {"key": PLAYER.puuid, "riot_id": "Player#NA1", "live": True}
    assert page["pool"]["jungle"] == [{"id": "LeeSin", "name": "Lee Sin", "stars": 5}]
    assert {"id": "Gnar", "name": "Gnar"} in page["champions"]
    jungle = {"jungle": [{"id": "LeeSin", "stars": 5}, {"id": "Elise", "stars": 4}]}
    saved = app.action("save_pool", {"account": PLAYER.puuid, "pool": jungle})
    assert saved == {"ok": True}
    assert app.session.watcher.picker.pool[Role.JUNGLE] == {"LeeSin": 5, "Elise": 4}  # in use
    assert load_pool(scout_home.pool_file)[Role.JUNGLE] == {"LeeSin": 5}  # pool.yaml untouched

    app.session.client.who = ALT  # log in to the other account
    alt = app.action("champions", {})
    assert alt["account"]["riot_id"] == "Alt#EUW"
    assert [c["id"] for c in alt["pool"]["jungle"]] == ["LeeSin"]  # starts from pool.yaml
    assert app._account_pool()[Role.JUNGLE] == {"LeeSin": 5}  # what the next draft uses

    app.session.client.who = None  # the client closes: the page shows the last account
    closed = app.action("champions", {})
    assert closed["account"] == {"key": ALT.puuid, "riot_id": "Alt#EUW", "live": False}
    app.session.client.who = PLAYER
    assert app._account_pool()[Role.JUNGLE] == {"LeeSin": 5, "Elise": 4}
    assert (scout_home.pools_dir / "Player_NA1.yaml").exists()


def test_saving_for_an_account_that_isnt_logged_in_leaves_picks_alone(app):
    app.action("champions", {})
    app.session.client.who = ALT
    app.action("champions", {})
    app.session.watcher.picker.pool = {"marker": True}
    gnar = {"top": [{"id": "Gnar", "stars": 2}]}
    ok = app.action("save_pool", {"account": PLAYER.puuid, "pool": gnar})
    assert ok == {"ok": True} and app.session.watcher.picker.pool == {"marker": True}
    assert "reopen" in app.action("save_pool", {"account": "gone", "pool": {}})["error"]


def test_suggestions_from_recent_games_and_saying_no(app):
    app.action("champions", {})
    got = app.action("suggestions", {})
    assert got["account"] == PLAYER.puuid and got["games"] == 8 and got["minimum"] == 4
    assert got["ideas"] == [{"role": "jungle", "id": "Elise", "name": "Elise", "games": 5}]
    answer = {"account": PLAYER.puuid, "role": "jungle", "id": "Elise"}  # no to Elise jungle
    assert app.action("decline", answer) == {"ok": True}
    assert app.action("suggestions", {})["ideas"] == []  # and Gnar top has only 3 games
    assert "error" in app.action("decline", dict(answer, role="lane"))
    app.session.client.who = None
    assert "Open the League client" in app.action("suggestions", {})["error"]


def test_the_account_and_region_come_from_the_client(app, scout_home, monkeypatch):
    monkeypatch.setattr(app, "_collect_status", lambda config: {})  # no stats database here
    app.session.client.games = [dict(g, platformId="EUW1") for g in app.session.client.games]
    account = app.action("settings", {})["account"]  # nothing typed anywhere
    assert account["logged_in"] == "Player#NA1" and account["live"] is True
    assert account["region"] == "EUW" and account["detected"] is True
    player = load_config(scout_home.config_file).player
    assert (player.platform, player.regional_route) == ("euw1", "europe")
    assert app.notice == "Region set to EUW from the League client."

    app.session.client.who = ALT  # another account, on a server Sidekick doesn't know
    app.session.client.games = [dict(g, platformId="XX9") for g in app.session.client.games]
    account = app.action("settings", {})["account"]
    assert account["logged_in"] == "Alt#EUW" and account["region"] == "EUW"  # left alone
    assert account["detected"] is False

    app.session.client.who = None
    account = app.action("settings", {})["account"]
    assert account["logged_in"] == "Alt#EUW" and account["live"] is False  # the last one


def test_most_played_suggests_only_champions_not_listed(app):
    got = app.action("pool_ideas", {})
    assert got["ideas"] == [{"role": "top", "id": "Gnar", "name": "Gnar", "points": 90000}]
