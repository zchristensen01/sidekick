"""`scout record`: scrubbing, deduplication, when a recording starts and ends, and the files."""

import copy
import itertools
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from lcu_fakes import fake_puuid, make_champ_select_session, make_gameflow_session

from scout.lcu.client import (
    CHAMP_SELECT_SESSION,
    GAME_VERSION,
    GAMEFLOW_PHASE,
    GAMEFLOW_SESSION,
    LcuUnavailable,
)
from scout.lcu.recorder import Recorder, find_unscrubbed, keep_only, run, scrub

NOW = datetime(2026, 10, 3, 21, 15, tzinfo=UTC)
RECORDED = sorted((Path(__file__).parent / "fixtures" / "champselect").glob("*.json"))


class FakeLcu:
    """A League client whose state the test sets between polls."""

    def __init__(self) -> None:
        self.phase = "Lobby"
        self.session: dict | None = None
        self.queue_id = 420
        self.roster_ready = True  # whether the game-start roster has filled in yet
        # The real format (checked on the live client 2026-10-02)
        self.version = (
            "16.19.8230722+branch.releases-16-19.code.public.content.release.anticheat.vanguard"
        )
        self.down = False

    def get(self, path: str):
        if self.down:
            raise LcuUnavailable("League client not running")
        if path == GAMEFLOW_SESSION:
            in_game = self.phase in ("GameStart", "InProgress")
            return make_gameflow_session(
                queue_id=self.queue_id, phase=self.phase, roster=in_game and self.roster_ready
            )
        return {
            GAMEFLOW_PHASE: self.phase,
            CHAMP_SELECT_SESSION: self.session,
            GAME_VERSION: self.version,
        }[path]


def make_recorder(lcu: FakeLcu, out_dir: Path, **kwargs) -> tuple[Recorder, list[str]]:
    messages: list[str] = []
    clock = itertools.count(100.0, 1.0)
    recorder = Recorder(
        lcu, out_dir, echo=messages.append, clock=lambda: next(clock), now=lambda: NOW, **kwargs
    )
    return recorder, messages


def poll(recorder: Recorder, lcu: FakeLcu, phase: str, session: dict | None = None):
    lcu.phase, lcu.session = phase, session
    return recorder.step()


# ---------------------------------------------------------------- scrubbing


def test_scrub_removes_every_identifier():
    session = make_champ_select_session()
    original = copy.deepcopy(session)
    assert {"chatDetails", "gameId", "myTeam[].puuid", "myTeam[].gameName"} <= set(
        find_unscrubbed(session)
    )
    clean, flagged = scrub(session)
    assert session == original  # the input isn't changed
    assert find_unscrubbed(clean) == []
    assert flagged == []  # every identifier was a known key
    assert "chatDetails" not in clean
    me = clean["myTeam"][1]
    assert (me["puuid"], me["gameName"], me["tagLine"], me["summonerId"]) == ("", "", "", 0)
    assert clean["gameId"] == 0


def test_scrub_keeps_the_draft():
    session = make_champ_select_session(enemy_champs=(122, 60, 0, 0, 0))
    clean, _ = scrub(session)
    for team in ("myTeam", "theirTeam"):
        for before, after in zip(session[team], clean[team], strict=True):
            for key in ("cellId", "championId", "assignedPosition", "spell1Id", "spell2Id"):
                assert after[key] == before[key]
    assert clean["actions"] == session["actions"]
    assert clean["timer"] == session["timer"]
    assert clean["localPlayerCellId"] == 1


def test_scrub_blanks_the_session_id_but_not_other_ids():
    session = make_champ_select_session()
    session["id"] = "0f8c2a5e-6b1d-4c3e-9a7f-2d4b6e8c0a1f"  # shape seen on the real client
    clean, flagged = scrub(session)
    assert clean["id"] == "" and flagged == []
    assert [a["id"] for a in clean["actions"][1]] == [10]  # action ids are kept


def test_scrub_blanks_unknown_token_like_values():
    session = make_champ_select_session()
    session["myTeam"][0]["someNewPlayerId"] = fake_puuid(9)
    clean, flagged = scrub(session)
    assert flagged == ["myTeam[].someNewPlayerId"]
    assert clean["myTeam"][0]["someNewPlayerId"] == ""


def test_keep_only():
    data = {"a": 1, "b": {"c": 2, "d": 3}, "e": 4}
    assert keep_only(data, {"a": True, "b": {"c": True}, "x": True}) == {"a": 1, "b": {"c": 2}}
    assert keep_only("not a dict", {"a": True}) == {}


# ---------------------------------------------------------------- recording


def test_records_a_champ_select_until_the_game_starts(tmp_path):
    lcu = FakeLcu()
    recorder, messages = make_recorder(lcu, tmp_path)
    assert poll(recorder, lcu, "Lobby") is None
    assert poll(recorder, lcu, "ChampSelect", None) is None  # session not ready yet
    poll(recorder, lcu, "ChampSelect", make_champ_select_session(phase="PLANNING", counter=1))
    # Only the timer and a skin changed: not a new snapshot.
    same = make_champ_select_session(phase="PLANNING", counter=2)
    same["myTeam"][0]["selectedSkinId"] = 86001
    poll(recorder, lcu, "ChampSelect", same)
    poll(recorder, lcu, "ChampSelect", make_champ_select_session(phase="BAN_PICK", counter=3))
    final = make_champ_select_session(phase="FINALIZATION", enemy_champs=(122, 60, 7, 51, 89))
    poll(recorder, lcu, "ChampSelect", final)
    path = poll(recorder, lcu, "GameStart")

    assert path == tmp_path / "2026-10-03_ranked_solo_jungle_champ64.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    assert find_unscrubbed(data) == []
    assert data["meta"] == {
        "recorded_at": "2026-10-03T21:15:00+00:00",
        "scout_version": "0.0.1",
        "game_version": "16.19.8230722",
        "queue_id": 420,
        "queue": "ranked_solo",
        "my_role": "jungle",
        "my_champion_id": 64,
        "outcome": "game_started",
        "end_phase": "GameStart",
        "snapshot_count": 3,
        "blanked_tokens": [],
    }
    assert [s["phase"] for s in data["snapshots"]] == ["PLANNING", "BAN_PICK", "FINALIZATION"]
    assert [s["elapsed_s"] for s in data["snapshots"]] == [1.0, 3.0, 4.0]
    assert [p["championId"] for p in data["snapshots"][-1]["session"]["theirTeam"]] == [
        122, 60, 7, 51, 89
    ]  # fmt: skip
    assert data["gameflow"] == {
        "phase": "ChampSelect",
        "gameData": {
            "isCustomGame": False,
            "queue": {
                "id": 420, "type": "RANKED_SOLO_5x5", "gameMode": "CLASSIC", "mapId": 11,
                "isRanked": True, "description": "Ranked Solo/Duo",
            },
        },
        "map": {"id": 11},
        "gameDodge": {"phase": "None", "state": "Invalid"},
    }  # fmt: skip
    assert messages[0] == "Champion select started (ranked_solo). Recording..."
    assert messages[-1].startswith("Saved ")

    # The answer key for enemy roles: champions, positions, spells; no identities.
    game_start = data["game_start"]
    assert set(game_start) == {"teamOne", "teamTwo", "spells"}
    assert game_start["teamOne"][1] == {
        "championId": 64, "selectedPosition": "JUNGLE", "selectedRole": ""
    }  # fmt: skip
    assert [p["championId"] for p in game_start["teamTwo"]] == [122, 60, 7, 51, 89]
    assert {"championId": 60, "spell1Id": 4, "spell2Id": 11} in game_start["spells"]
    assert all(set(s) == {"championId", "spell1Id", "spell2Id"} for s in game_start["spells"])


def test_waits_for_the_roster_to_fill_in_at_game_start(tmp_path):
    lcu = FakeLcu()
    recorder, _ = make_recorder(lcu, tmp_path)
    poll(recorder, lcu, "ChampSelect", make_champ_select_session())
    lcu.roster_ready = False
    assert poll(recorder, lcu, "GameStart") is None  # still loading
    lcu.roster_ready = True
    path = poll(recorder, lcu, "GameStart")
    assert json.loads(path.read_text(encoding="utf-8"))["game_start"]["spells"]


@pytest.mark.parametrize("how", ["in_progress", "ctrl_c"])
def test_game_without_a_roster_is_still_saved_as_started(tmp_path, how):
    lcu = FakeLcu()
    lcu.roster_ready = False
    recorder, _ = make_recorder(lcu, tmp_path)
    poll(recorder, lcu, "ChampSelect", make_champ_select_session())
    assert poll(recorder, lcu, "GameStart") is None
    path = poll(recorder, lcu, "InProgress") if how == "in_progress" else recorder.stop()
    data = json.loads(path.read_text(encoding="utf-8"))
    assert path.name == "2026-10-03_ranked_solo_jungle_champ64.json"
    assert data["meta"]["outcome"] == "game_started"
    assert data["game_start"] is None


def test_dodge_is_saved_with_a_suffix(tmp_path):
    lcu = FakeLcu()
    recorder, _ = make_recorder(lcu, tmp_path)
    poll(recorder, lcu, "ChampSelect", make_champ_select_session())
    path = poll(recorder, lcu, "Matchmaking")
    assert path.name == "2026-10-03_ranked_solo_jungle_champ64_dodged.json"
    meta = json.loads(path.read_text(encoding="utf-8"))["meta"]
    assert (meta["outcome"], meta["end_phase"]) == ("dodged", "Matchmaking")


def test_a_new_champ_select_without_a_phase_change_starts_a_new_file(tmp_path):
    lcu = FakeLcu()
    recorder, _ = make_recorder(lcu, tmp_path)
    poll(recorder, lcu, "ChampSelect", make_champ_select_session(game_id=1))
    first = poll(recorder, lcu, "ChampSelect", make_champ_select_session(game_id=2, my_champ=60))
    assert first.name.endswith("champ64_dodged.json")
    second = poll(recorder, lcu, "InProgress")
    assert second.name == "2026-10-03_ranked_solo_jungle_champ60.json"


def test_other_queues_are_skipped_unless_asked(tmp_path):
    lcu = FakeLcu()
    lcu.queue_id = 450  # ARAM
    recorder, messages = make_recorder(lcu, tmp_path)
    poll(recorder, lcu, "ChampSelect", make_champ_select_session(queue_id=450))
    poll(recorder, lcu, "ChampSelect", make_champ_select_session(queue_id=450, counter=5))
    assert poll(recorder, lcu, "GameStart") is None
    assert len(messages) == 1 and "not a draft queue" in messages[0]

    recorder, _ = make_recorder(lcu, tmp_path, all_queues=True)
    poll(recorder, lcu, "ChampSelect", make_champ_select_session(queue_id=450))
    path = poll(recorder, lcu, "GameStart")
    assert path.name == "2026-10-03_queue450_jungle_champ64.json"


def test_closing_the_client_keeps_the_recording(tmp_path):
    lcu = FakeLcu()
    recorder, _ = make_recorder(lcu, tmp_path)
    poll(recorder, lcu, "ChampSelect", make_champ_select_session(phase="BAN_PICK"))
    lcu.down = True
    with pytest.raises(LcuUnavailable):
        recorder.step()
    lcu.down = False
    poll(recorder, lcu, "ChampSelect", make_champ_select_session(phase="FINALIZATION"))
    path = poll(recorder, lcu, "GameStart")
    assert json.loads(path.read_text(encoding="utf-8"))["meta"]["snapshot_count"] == 2


def test_stop_saves_a_partial_recording_once(tmp_path):
    lcu = FakeLcu()
    recorder, _ = make_recorder(lcu, tmp_path)
    assert recorder.stop() is None
    poll(recorder, lcu, "ChampSelect", make_champ_select_session())
    path = recorder.stop()
    assert path.name.endswith("_stopped.json")
    assert recorder.stop() is None


def test_files_are_never_overwritten(tmp_path):
    lcu = FakeLcu()
    recorder, _ = make_recorder(lcu, tmp_path)
    names = []
    for game_id in (1, 2):
        poll(recorder, lcu, "ChampSelect", make_champ_select_session(game_id=game_id))
        names.append(poll(recorder, lcu, "GameStart").name)
    assert names == [
        "2026-10-03_ranked_solo_jungle_champ64.json",
        "2026-10-03_ranked_solo_jungle_champ64_2.json",
    ]


def test_missing_game_version_is_fine(tmp_path):
    lcu = FakeLcu()
    lcu.version = None  # endpoint returned 404
    recorder, _ = make_recorder(lcu, tmp_path)
    poll(recorder, lcu, "ChampSelect", make_champ_select_session())
    path = poll(recorder, lcu, "GameStart")
    assert json.loads(path.read_text(encoding="utf-8"))["meta"]["game_version"] is None


def test_unscrubbed_recording_is_not_written_and_recording_goes_on(tmp_path, monkeypatch):
    lcu = FakeLcu()
    recorder, messages = make_recorder(lcu, tmp_path)
    monkeypatch.setattr("scout.lcu.recorder.find_unscrubbed", lambda data: ["meta.something"])
    poll(recorder, lcu, "ChampSelect", make_champ_select_session())
    assert poll(recorder, lcu, "GameStart") is None
    assert list(tmp_path.iterdir()) == []
    assert messages[-1].startswith("Not saved: unscrubbed values at meta.something")
    poll(recorder, lcu, "ChampSelect", make_champ_select_session(game_id=2))
    assert recorder.current is not None  # the next game still records


def test_run_waits_for_the_client_and_saves_on_ctrl_c(tmp_path):
    lcu = FakeLcu()
    lcu.down = True
    recorder, _ = make_recorder(lcu, tmp_path)
    messages: list[str] = []
    script = iter([
        lambda: setattr(lcu, "down", False),  # the client opens
        lambda: (setattr(lcu, "phase", "ChampSelect"),
                 setattr(lcu, "session", make_champ_select_session())),
        lambda: None,
    ])  # fmt: skip
    sleeps: list[float] = []

    def sleep(seconds: float) -> None:
        sleeps.append(seconds)
        step = next(script, None)
        if step is None:
            raise KeyboardInterrupt
        step()

    run(recorder, 1.0, echo=messages.append, sleep=sleep)
    assert messages == [
        "Waiting for the League client to open...",
        "Connected to the League client. Waiting for champion select.",
        "Stopping.",
    ]
    assert sleeps[0] == 3.0  # waits longer while the client is closed
    assert [p.name for p in tmp_path.iterdir()] == [
        "2026-10-03_ranked_solo_jungle_champ64_stopped.json"
    ]


# ---------------------------------------------------------------- real recorded fixtures


@pytest.mark.parametrize("path", RECORDED, ids=[p.name for p in RECORDED])
def test_recorded_fixtures_are_scrubbed_and_complete(path):
    data = json.loads(path.read_text(encoding="utf-8"))
    assert find_unscrubbed(data) == []
    # game_start was added after the first recording, so older files don't have it
    assert {"meta", "gameflow", "snapshots"} <= set(data) <= {
        "meta", "gameflow", "snapshots", "game_start"
    }  # fmt: skip
    assert data["meta"]["snapshot_count"] == len(data["snapshots"]) > 0
    for snapshot in data["snapshots"]:
        assert {"elapsed_s", "phase", "session"} <= set(snapshot)
        assert "myTeam" in snapshot["session"] and "localPlayerCellId" in snapshot["session"]
