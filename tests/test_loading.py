"""Loading-screen addendum (M11): likely duos, one-tricks, hidden players, the Riot API client.
A fake Riot API with synthetic matches; no network. Identifiers never reach the output."""

import json
from types import SimpleNamespace

import httpx
import pytest
from lcu_fakes import ENEMY_CHAMPS, fake_puuid, make_gameflow_session

from scout.data.riot import RiotApi, RiotError
from scout.loading import Addendum, Enemy, check, enemies_at_loading, likely_duos, one_trick
from scout.model.roles import Role

NAMES = {122: "Darius", 60: "Elise", 7: "LeBlanc", 51: "Caitlyn", 89: "Leona"}


class FakeRiot:
    """Elise (cell 6) and LeBlanc (cell 7) queue together; Caitlyn (8) shares games with them
    but on the other team; Darius (5) is a one-trick."""

    def __init__(self, fail: bool = False) -> None:
        self.fail = fail
        self.calls: list[str] = []
        p = {cell: fake_puuid(cell) for cell in range(5, 10)}
        self.history = {
            p[5]: ["m9"],
            p[6]: ["m1", "m2", "m3", "m4"],
            p[7]: ["m1", "m2", "m3"],
            p[8]: ["m1", "m2", "m5"],
            p[9]: ["m6"],
        }
        team = {
            "m1": {p[6]: 100, p[7]: 100, p[8]: 200},
            "m2": {p[6]: 100, p[7]: 100, p[8]: 200},
            "m3": {p[6]: 200, p[7]: 200},
        }
        self.matches = {
            m: {"info": {"participants": [{"puuid": u, "teamId": t} for u, t in who.items()]}}
            for m, who in team.items()
        }
        self.mastery = {p[5]: [(122, 900_000), (86, 120_000)], p[6]: [(60, 200_000), (64, 150_000)]}

    def account_puuid(self, game_name, tag_line):
        self.calls.append("account")
        return game_name  # the fakes use the client id as the Riot ID game name

    def match_ids(self, puuid, count=20):
        self.calls.append("ids")
        if self.fail:
            raise RiotError("Riot API key rejected (RIOT_API_KEY in .env: expired or wrong?)")
        return self.history.get(puuid, [])

    def match(self, match_id):
        self.calls.append("match")
        return self.matches.get(match_id, {})

    def top_mastery(self, puuid, count=3):
        self.calls.append("mastery")
        return self.mastery.get(puuid, [])


def enemies(hide_cell: int | None = None):
    gameflow = make_gameflow_session(phase="GameStart", roster=True)
    for player in gameflow["gameData"]["teamTwo"]:
        if hide_cell is not None and player["puuid"] == fake_puuid(hide_cell):
            player["puuid"] = ""  # streamer mode / hidden
    return enemies_at_loading(gameflow, list(ENEMY_CHAMPS), NAMES, {60: Role.JUNGLE})


def test_the_enemy_team_is_found_by_champion():
    found, hidden = enemies()
    assert [e.name for e in found] == ["Darius", "Elise", "LeBlanc", "Caitlyn", "Leona"]
    assert hidden == 0 and found[1].role is Role.JUNGLE
    assert enemies_at_loading({"gameData": {}}, list(ENEMY_CHAMPS), NAMES, {}) == ([], 0)


def test_duos_and_one_tricks():
    found, hidden = enemies()
    result = check(FakeRiot(), found, hidden)
    assert result.duos == (("Elise", "LeBlanc"),)  # Caitlyn shared games on the other team
    assert result.one_tricks == ("Darius",)
    text = "\n".join(result.lines())
    assert "Their Elise and LeBlanc have played several recent games together" in text
    assert "Their Darius player has far more games on Darius" in text
    assert "fake" not in text.lower() and "puuid" not in text  # no identifiers


def test_hidden_players_are_skipped_not_guessed():
    found, hidden = enemies(hide_cell=7)  # LeBlanc hidden
    assert hidden == 1 and "LeBlanc" not in [e.name for e in found]
    result = check(FakeRiot(), found, hidden)
    assert result.duos == ()  # never inferred from Elise's history
    assert any("1 enemy player(s) are hidden" in line for line in result.lines())


def test_api_failure_is_one_line():
    found, hidden = enemies()
    lines = check(FakeRiot(fail=True), found, hidden).lines()
    assert lines == [
        "Loading screen check skipped: Riot API key rejected (RIOT_API_KEY in .env: "
        "expired or wrong?)."
    ]
    assert Addendum((), (), 0, 5).lines() == [
        "Loading screen: no likely duos or one-tricks among the 5 visible enemies."
    ]


def test_client_ids_become_web_api_ids():
    from scout.loading import resolve

    found, hidden = enemies()
    riot = FakeRiot()
    names = {e.puuid: (f"api-{e.puuid}", "NA1") for e in found[:4]}  # the 5th has no Riot ID
    riot.account_puuid = lambda name, tag: name
    resolved, unresolved = resolve(found, names.get, riot)
    assert [e.puuid for e in resolved] == [f"api-{e.puuid}" for e in found[:4]]
    assert unresolved == 1 and resolved[0].riot_id == (f"api-{found[0].puuid}", "NA1")


def test_one_trick_thresholds():
    assert one_trick([(1, 1_200_000), (2, 900_000)], 1)  # a lot of points
    assert one_trick([(1, 300_000), (2, 90_000)], 1)  # three times the next
    assert not one_trick([(1, 300_000), (2, 150_000)], 1)
    assert not one_trick([(2, 900_000), (1, 100)], 1)  # not their top champion
    assert not one_trick([], 1)


def test_duo_needs_two_games_on_the_same_team():
    a, b = Enemy(1, "A", None, "pa"), Enemy(2, "B", None, "pb")
    histories = {"pa": ["x", "y"], "pb": ["x", "y"]}
    assert likely_duos([a, b], histories, lambda m, p, q: True) == [("A", "B")]
    assert likely_duos([a, b], histories, lambda m, p, q: m == "x") == []
    assert likely_duos([a, b], {"pa": ["x"], "pb": ["x"]}, lambda m, p, q: True) == []


# ---------------------------------------------------------------- the Riot API client


def riot_with(handler, **kwargs) -> RiotApi:
    http = httpx.Client(transport=httpx.MockTransport(handler))
    return RiotApi("RGAPI-test", "na1", "americas", http=http, **kwargs)


def test_riot_requests():
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(
            (
                request.method,
                request.url.host,
                request.url.path,
                dict(request.url.params),
                request.headers.get("x-riot-token"),
            )
        )
        if request.url.path.endswith("/ids"):
            return httpx.Response(200, json=["NA1_1", "NA1_2"])
        if "/champion-masteries/" in request.url.path:
            return httpx.Response(200, json=[{"championId": 122, "championPoints": 5}])
        return httpx.Response(404, json={})

    riot = riot_with(handler)
    assert riot.match_ids("abc", 20) == ["NA1_1", "NA1_2"]
    assert riot.top_mastery("abc") == [(122, 5)]
    assert riot.match("NA1_404") == {}
    assert {m for m, *_ in seen} == {"GET"}
    assert seen[0][1:] == (
        "americas.api.riotgames.com",
        "/lol/match/v5/matches/by-puuid/abc/ids",
        {"type": "ranked", "count": "20"},
        "RGAPI-test",
    )
    assert seen[1][1] == "na1.api.riotgames.com"


@pytest.mark.parametrize(
    ("status", "message"),
    [(401, "key rejected"), (403, "key rejected"), (429, "rate limit"), (500, "HTTP 500")],
)
def test_riot_errors(status, message):
    riot = riot_with(lambda request: httpx.Response(status, json={}))
    with pytest.raises(RiotError, match=message):
        riot.match_ids("abc")


def test_riot_rate_limit_waits_then_gives_up():
    now, slept = [0.0], []

    def sleep(seconds: float) -> None:
        slept.append(seconds)
        now[0] += seconds

    riot = riot_with(lambda r: httpx.Response(200, json=[]), clock=lambda: now[0], sleep=sleep)
    for _ in range(21):  # the 21st call in one second waits for the window
        riot.match_ids("abc")
    assert slept and slept[0] == pytest.approx(1.0)
    impatient = riot_with(
        lambda r: httpx.Response(200, json=[]),
        clock=lambda: 0.0,
        sleep=lambda s: None,
        max_wait_s=0.5,
    )
    with pytest.raises(RiotError, match="too many calls"):
        for _ in range(21):
            impatient.match_ids("abc")


# ---------------------------------------------------------------- scout watch


def test_watch_adds_the_loading_screen_lines(knowledge, tmp_path):
    from test_watcher import RECORDING, loading_roster, make_watcher, replay

    watcher, messages, clock = make_watcher(knowledge, tmp_path)
    watcher.write_in_background = False
    enemies_keys = [p["championId"] for p in RECORDING["snapshots"][-1]["session"]["theirTeam"]]
    riot = FakeRiot()
    p = {key: fake_puuid(i) for i, key in enumerate(enemies_keys)}
    riot.history = {p[enemies_keys[0]]: ["a", "b"], p[enemies_keys[1]]: ["a", "b"]}
    riot.matches = {
        m: {"info": {"participants": [{"puuid": p[k], "teamId": 100} for k in enemies_keys[:2]]}}
        for m in ("a", "b")
    }
    riot.mastery = {}
    watcher.riot = riot
    watcher.client = SimpleNamespace(
        get=lambda path: {"gameName": path.rsplit("/", 1)[-1], "tagLine": "NA1"}
    )
    shown = []
    watcher.on_report = lambda title, text: shown.append(text)
    replay(watcher, clock)
    roster = loading_roster(smite_on=154)
    for player, key in zip(roster["gameData"]["teamTwo"], enemies_keys, strict=True):
        player["puuid"] = p[key]
    watcher.process("GameStart", None, roster)
    first, second = (knowledge.facts(watcher.index.by_key[k]).name for k in enemies_keys[:2])
    line = f"Their {first} and {second} have played several recent games together"
    assert any(line in m for m in messages)
    assert "LOADING SCREEN" in shown[-1] and line in shown[-1]
    saved = next(tmp_path.glob("*.md")).read_text(encoding="utf-8")
    assert "## Loading screen" in saved and line in saved
    assert json.dumps(p[enemies_keys[0]]) not in saved  # no identifiers in the file
    calls = len(riot.calls)
    watcher.process("GameStart", None, roster)
    assert len(riot.calls) == calls  # once per game


def test_key_check_tells_expired_from_working():
    ok = riot_with(lambda r: httpx.Response(200, json={"id": "NA1"}))
    ok.check()
    expired = riot_with(lambda r: httpx.Response(403, json={}))
    with pytest.raises(RiotError, match="development keys last 24 hours"):
        expired.check()


def test_env_writer_replaces_only_that_line():
    from scout.config import with_env_value

    text = "# keys\nRIOT_API_KEY=old\nANTHROPIC_API_KEY=keep\n"
    assert with_env_value(text, "RIOT_API_KEY", "RGAPI-new") == (
        "# keys\nRIOT_API_KEY=RGAPI-new\nANTHROPIC_API_KEY=keep\n"
    )
    assert with_env_value("A=1\n", "RIOT_API_KEY", "x") == "A=1\nRIOT_API_KEY=x\n"


def test_scout_key_command(scout_home, monkeypatch):
    from typer.testing import CliRunner

    import scout.cli

    checked = []
    monkeypatch.setattr(scout.cli.RiotApi, "check", lambda self: checked.append(self.key))
    runner = CliRunner()
    bad = runner.invoke(scout.cli.app, ["key"], input="not-a-key\n")
    assert bad.exit_code == 1 and "start with RGAPI-" in bad.output
    good = runner.invoke(scout.cli.app, ["key"], input="RGAPI-test-123\n")
    assert good.exit_code == 0, good.output
    assert "RGAPI-test-123" not in good.output  # never echoed
    assert "RIOT_API_KEY=RGAPI-test-123" in scout_home.env_file.read_text(encoding="utf-8")
    assert checked == ["RGAPI-test-123"]
