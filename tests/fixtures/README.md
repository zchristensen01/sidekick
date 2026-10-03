# Test fixtures

Tests never touch the network (CLAUDE.md hard rule 7). Everything they need is here.

| Folder | What | Made by |
|---|---|---|
| `sources/` | Small real responses from each data source (Data Dragon, CommunityDragon, wiki, OP.GG, Riot). Parsers are built against these. See `sources/README.md`. | Captured 2026-10-02; re-capture when a source changes shape |
| `champselect/` | Sample champ select sessions in the client's real format. Champions, clock times and skins are made up; no names, ids or tokens | Shaped like `scout record` output (M1); never anyone's real games |
| `static/<version>/` | A copy of three generated tables (`champions.csv`, `champion_meta.csv`, `summoner_spells.csv`) so tests can map real champion ids and positions offline, plus a frozen copy of `champion_traits.csv` for the golden tests | Copied from `data/generated/static/` after `scout refresh`, and from `data/manual/` (traits); re-copy on purpose, then update the golden files |
| `games/` | Hand-written games for offline reports and golden tests | By hand, or saved from a game description |
| `../golden/` | Expected sections and fired rule IDs per game and role | By hand, updated on purpose |

## Game fixture format (`games/<name>.yaml`)
```yaml
name: samira_naut                 # matches the file name
description: >                    # what this game is meant to test
  ...
ddragon_version: "16.19.1"
queue: ranked_solo                # normal_draft | ranked_solo | ranked_flex | clash
my_role: jungle                   # default role for `scout report`; --role overrides
ally:  {top: Garen, jungle: LeeSin, mid: Ahri, bot: Jhin, support: Lulu}
enemy: {top: Malphite, jungle: Elise, mid: Yasuo, bot: Samira, support: Nautilus}
pick_turns: {}                    # optional: champ_id -> draft turn index (counter-pick tests)
enemy_role_confidence: {}         # optional: role -> confidence (default 1.0)
```
Champion ids are Data Dragon ids (`MonkeyKing` for Wukong, `Chogath` for Cho'Gath).

## Golden file format (`../golden/<game>.<role>.yaml`), from M5
```yaml
game: samira_naut
role: jungle
sections: [gank_first, lanes_in_trouble, enemy_jungler, start_objectives, watch_out, dont_feed, game_plan]
fired: [BOT-KILL-LANE-THEM, JG-ENEMY-GANKER, SYN-AIRBORNE]   # must appear in this role's report
not_fired: [LANE-WINNING]                                      # must not appear
```
`sections` must match exactly, in order. Goldens use the frozen traits in `static/<version>/`.

## Recorded champ select format, from M1
`scout record` names files `<date>_<queue>_<role>_champ<id>.json` and saves them in your own
data folder, never in the repo. The samples here are named `sample_<n>_<queue>_<role>.json`.
```json
{"meta": {"recorded_at": "2026-10-03T21:15:00+00:00", "scout_version": "0.0.1",
          "game_version": "16.19.715.1234", "queue_id": 420, "queue": "ranked_solo",
          "my_role": "jungle", "my_champion_id": 64, "outcome": "game_started",
          "end_phase": "GameStart", "snapshot_count": 12, "blanked_tokens": []},
 "gameflow": {"phase": "ChampSelect", "gameData": {"queue": {"id": 420, ...}, ...}, ...},
 "snapshots": [ {"elapsed_s": 0.0, "phase": "PLANNING", "session": {...}}, ... ],
 "game_start": {"teamOne": [{"championId": 86, "selectedPosition": "TOP", "selectedRole": ""}, ...],
                "teamTwo": [...],
                "spells": [{"championId": 60, "spell1Id": 4, "spell2Id": 11}, ...]}}
```
`outcome` is `game_started`, `dodged` or `stopped` (the last two also end the file name).
`game_start` is the roster the game showed at loading (the answer key for enemy roles), or
`null` if the game didn't start or the roster never filled in.
Scrubbed per `docs/LCU.md` section 7; `tests/test_lcu_recorder.py` checks every file here.
Fake sessions for unit tests are built in `tests/lcu_fakes.py`.
