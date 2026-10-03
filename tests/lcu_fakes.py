"""Fake League client payloads for tests.

Shaped like real LCU responses (docs/LCU.md section 3), with made-up identifiers in every field
the recorder must scrub. Real recorded sessions live in tests/fixtures/champselect/.
"""

from typing import Any

POSITIONS = ("top", "jungle", "middle", "bottom", "utility")


def fake_puuid(n: int) -> str:
    return f"fakepuuid{n}".ljust(78, "p")  # real puuids are 78 characters


def _player(cell: int, position: str, champ: int, *, ally: bool) -> dict[str, Any]:
    return {
        "assignedPosition": position if ally else "",
        "cellId": cell,
        "championId": champ,
        "championPickIntent": 0,
        "gameName": f"Fake Player {cell}" if ally else "",
        "internalName": "",
        "isHumanoid": False,
        "nameVisibilityType": "VISIBLE" if ally else "HIDDEN",
        "obfuscatedPuuid": f"fakeobf{cell}".ljust(40, "o") if ally else "",
        "obfuscatedSummonerId": 900 + cell if ally else 0,
        "playerType": "PLAYER",
        "puuid": fake_puuid(cell) if ally else "",
        "selectedSkinId": champ * 1000,
        "spell1Id": 4 if ally else 0,
        "spell2Id": (11 if position == "jungle" else 14) if ally else 0,
        "summonerId": 1000 + cell if ally else 0,
        "tagLine": "NA1" if ally else "",
        "team": 1 if ally else 2,
        "wardSkinId": -1,
    }


def make_champ_select_session(
    *,
    game_id: int = 5_000_000_001,
    phase: str = "BAN_PICK",
    my_champ: int = 64,
    enemy_champs: tuple[int, ...] = (0, 0, 0, 0, 0),
    counter: int = 1,
    queue_id: int = 420,
) -> dict[str, Any]:
    """A champ select session; I'm cell 1 (jungle) on the blue side."""
    ally_champs = (86, my_champ, 103, 202, 117)
    my_team = [_player(i, POSITIONS[i], ally_champs[i], ally=True) for i in range(5)]
    their_team = [_player(5 + i, "", enemy_champs[i], ally=False) for i in range(5)]

    def action(n: int, cell: int, champ: int, kind: str) -> dict[str, Any]:
        return {
            "actorCellId": cell, "championId": champ, "completed": champ != 0, "id": n,
            "isAllyAction": cell < 5, "isInProgress": False, "pickTurn": 1, "type": kind,
        }  # fmt: skip

    return {
        # Real layout (seen in the first recording): bans, then picks 1-2-2-2-2-1.
        "actions": [
            [action(i, i, 0, "ban") for i in range(10)],
            [action(10, 0, ally_champs[0], "pick")],
            [action(11, 5, enemy_champs[0], "pick"), action(12, 6, enemy_champs[1], "pick")],
            [action(13, 1, ally_champs[1], "pick"), action(14, 2, ally_champs[2], "pick")],
            [action(15, 7, enemy_champs[2], "pick"), action(16, 8, enemy_champs[3], "pick")],
            [action(17, 3, ally_champs[3], "pick"), action(18, 4, ally_champs[4], "pick")],
            [action(19, 9, enemy_champs[4], "pick")],
        ],
        "allowBattleBoost": False,
        "allowDuplicatePicks": False,
        "allowLockedEvents": False,
        "allowRerolling": False,
        "allowSkinSelection": True,
        "bans": {"myTeamBans": [], "numBans": 10, "theirTeamBans": []},
        "benchChampions": [],
        "benchEnabled": False,
        "boostableSkinCount": 1,
        "chatDetails": {
            "mucJwtDto": {
                "channelClaim": "",
                "domain": "champ-select",
                "targetRegion": "na1",
                "jwt": "eyJhbGciOiJIUzI1NiJ9.ZmFrZS1jaGF0LXRva2Vu.ZmFrZS1zaWduYXR1cmU",
            },
            "multiUserChatId": "fake-chat-id",
            "multiUserChatPassword": "fake-chat-password",
        },  # fmt: skip
        "counter": counter,
        "gameId": game_id,
        "hasSimultaneousBans": True,
        "hasSimultaneousPicks": False,
        "isCustomGame": False,
        "isSpectating": False,
        "localPlayerCellId": 1,
        "lockedEventIndex": -1,
        "myTeam": my_team,
        "pickOrderSwaps": [],
        "positionSwaps": [],
        "queueId": queue_id,
        "recoveryCounter": 0,
        "rerollsRemaining": 0,
        "skipChampionSelect": False,
        "theirTeam": their_team,
        "timer": {
            "adjustedTimeLeftInPhase": 27000 - counter,
            "internalNowInEpochMs": 1_790_000_000_000 + counter,
            "isInfinite": False,
            "phase": phase,
            "totalTimeInPhase": 30000,
        },
        "trades": [],
    }


ALLY_CHAMPS = (86, 64, 103, 202, 117)
ENEMY_CHAMPS = (122, 60, 7, 51, 89)  # 60 (Elise) has Smite: the enemy jungler


def _roster(champs: tuple[int, ...], *, ally: bool, first_cell: int) -> list[dict[str, Any]]:
    return [
        {
            "championId": champ, "lastSelectedSkinIndex": 0, "profileIconId": 4567,
            "puuid": fake_puuid(first_cell + i), "selectedPosition": POSITIONS[i].upper() if ally
            else "", "selectedRole": "", "summonerId": 1000 + first_cell + i,
            "summonerInternalName": f"fakeplayer{first_cell + i}",
            "summonerName": f"Fake Player {first_cell + i}", "teamOwner": False,
            "teamParticipantId": 1 if ally else 2,
        }
        for i, champ in enumerate(champs)
    ]  # fmt: skip


def _spells(champs: tuple[int, ...], first_cell: int) -> list[dict[str, Any]]:
    spells = ((4, 12), (4, 11), (4, 14), (4, 7), (4, 3))  # in POSITIONS order; 11 = Smite
    return [
        {"championId": champ, "selectedSkinIndex": 0, "spell1Id": spells[i][0],
         "spell2Id": spells[i][1], "puuid": fake_puuid(first_cell + i),
         "summonerInternalName": f"fakeplayer{first_cell + i}"}
        for i, champ in enumerate(champs)
    ]  # fmt: skip


def make_gameflow_session(
    *, queue_id: int = 420, phase: str = "ChampSelect", roster: bool = False
) -> dict[str, Any]:
    """A gameflow session, including the identifying parts the recorder must not keep.

    roster=True: as at game start, with every player's champion, position and spells.
    """
    return {
        "gameClient": {
            "observerServerIp": "203.0.113.7", "observerServerPort": 8080, "running": False,
            "serverIp": "203.0.113.8", "serverPort": 5100, "visible": False,
        },
        "gameData": {
            "gameId": 5_000_000_001,
            "gameName": "",
            "isCustomGame": False,
            "password": "",
            "playerChampionSelections": (
                _spells(ALLY_CHAMPS, 0) + _spells(ENEMY_CHAMPS, 5) if roster else []
            ),
            "queue": {
                "id": queue_id, "type": "RANKED_SOLO_5x5", "gameMode": "CLASSIC", "mapId": 11,
                "isRanked": True, "description": "Ranked Solo/Duo", "name": "Ranked Solo/Duo",
                "category": "PvP",
            },
            "spectatorsAllowed": False,
            "teamOne": _roster(ALLY_CHAMPS, ally=True, first_cell=0) if roster else [],
            "teamTwo": _roster(ENEMY_CHAMPS, ally=False, first_cell=5) if roster else [],
        },
        "gameDodge": {"dodgeIds": [1003], "phase": "None", "state": "Invalid"},
        "map": {"id": 11, "name": "Summoner's Rift", "assets": {"icon": "lol-game-data/x.png"}},
        "phase": phase,
    }  # fmt: skip
