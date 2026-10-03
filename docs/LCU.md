# LCU: reading champion select from the League client

The LCU (League Client Update API) is the League client's local REST + WebSocket API. Riot calls
it "not officially supported": no docs, no change notices. Riot also plans a new client
"after 2026", which will likely break it. So: keep all of it inside `scout/lcu/`, read only what
we need, and record real sessions so changes show up as failing fixture tests.

**Read-only, always.** Only `GET` requests and event subscriptions. `scout/lcu/client.py` has a
single `get()` method and a test asserts there's nothing else. No accept, pick, ban, runes,
chat, or anything that changes client state.

Facts below were checked against a patch 26.16 swagger dump and community tools active in 2026
(sources at the end). Field names marked [verify] must be confirmed on a recorded session before
code depends on them.

## 1. Finding and connecting to the client (`lcu/connection.py`)
1. **Process arguments (preferred).** Find the `LeagueClientUx.exe` process with `psutil` and
   read `--app-port=<port>` and `--remoting-auth-token=<token>` from its command line. This works
   wherever League is installed. Don't use WMIC: it's removed in Windows 11 24H2.
2. **Lockfile (fallback).** `<install dir>\lockfile`, default `C:\Riot Games\League of Legends\lockfile`
   (configurable). Format: `LeagueClient:<pid>:<port>:<password>:https`. It's deleted when the
   client exits and can be left stale after a crash (connection refused).
3. **Auth.** HTTPS basic auth, user `riot`, password = the token, base `https://127.0.0.1:<port>`.
4. **Certificate.** Pin Riot's root CA (`riotgames.pem`, published at
   https://static.developer.riotgames.com/docs/lol/riotgames.pem, valid to 2043) and ship it in
   `scout/lcu/`. Checked on the live client (2026-10-02, 16.19): its certificate is
   `CN=rclient`, SAN `DNS:localhost, IP:127.0.0.1`, SHA-256, signed by the pinned root, so the
   chain **and** the hostname `127.0.0.1` verify. One check is off: Python 3.13's
   `VERIFY_X509_STRICT`, which rejects it with "Missing Authority Key Identifier" (it names its
   issuer by name and serial, not key id).
5. **Reconnect** when a request fails: the port and token change every client restart.
6. **Vanguard** (Riot's anti-cheat) doesn't block LCU apps. Riot blocks *game memory* reading
   for unknown apps from 2026-10-06; we never do that.

## 2. Endpoints we use (all GET)
| Endpoint | Why |
|---|---|
| `/lol-gameflow/v1/gameflow-phase` | Where we are: `None, Lobby, Matchmaking, ReadyCheck, ChampSelect, GameStart, InProgress, WaitingForStats, PreEndOfGame, EndOfGame, ...` |
| `/lol-gameflow/v1/session` | Queue id (`gameData.queue.id`), dodge state; at game start, the roster (champions, positions, spells) that confirms enemy roles in the final report and that the recorder keeps as the answer key, the game id for the post-game check (M10), and the loading-screen player list: each visible player's `puuid` (enemies for the duo / one-trick check, M11; allies and enemies for players' records, M16), read in memory for the Riot API and OP.GG calls and never stored; an empty `puuid` = hidden, skipped |
| `/lol-champ-select/v1/session` | The draft. Returns 404 `"No active delegate"` outside champ select |
| `/lol-patch/v1/game-version` | The client's game version, saved in recorded fixtures (M1). Returns e.g. `"16.19.8230722+branch.releases-16-19..."`; we keep the part before `+` |
| `/lol-summoner/v1/current-summoner` | Who is logged in (`puuid`, `gameName`, `tagLine`): each account keeps its own champions (M22, `scout/accounts.py`). Only ever the local player |
| `/lol-match-history/v1/products/lol/current-summoner/matches` | The logged-in player's own recent games (the client's default page; it lists only their own row per game), for the Champions page's suggestions and your region (M22): `games.games[]` with `mapId`, `gameMode`, `gameType`, `platformId` (the server, e.g. `NA1`), and `participants[].championId` and `timeline.lane`/`role` in Riot's match-v4 values. Not yet checked against a live client: if the shape differs, the page says it couldn't read the games and the log names the fields it saw |
| `/lol-summoner/v2/summoners/puuid/{puuid}` | At the loading screen only: the Riot ID (`gameName`, `tagLine`) of each visible ally and enemy, from their client id, so the duo / one-trick check (enemies, M11) and players' records (everyone but me, M16) can use Riot's and OP.GG's APIs (the client's ids aren't the web API's). Kept in memory, never stored or sent to the LLM; hidden players have no id and are skipped. A template (`TEMPLATES`), not a fixed path |
| `/lol-champion-mastery/v1/local-player/champion-mastery` | the owner's own champion mastery (`championId`, `championPoints`, `lastPlayTime`, ...), for `scout pool`, pick suggestions when a role has no pool (M9b), and the Champions page's most-played ideas (M22). Checked 2026-10-02; mid-game it returned a single entry, so it's read again at each champ select |
Add endpoints only when a milestone needs them, and list them here. Code can only read the paths
in `ENDPOINTS`, or a `TEMPLATES` path filled with one plain id (`scout/lcu/client.py`); a test
checks each one is listed in this table.

## 3. The champ select session
Top level: `actions`, `bans`, `myTeam`, `theirTeam`, `localPlayerCellId`, `timer`, `trades`,
`pickOrderSwaps`, `positionSwaps`, `benchChampions`, `queueId` (new in 26.x), `gameId`,
`isSpectating`, `isCustomGame`, `chatDetails`, and more.

Player entries (`myTeam[]`, `theirTeam[]`): `cellId`, `team`, `championId`, `championPickIntent`
(hover), `assignedPosition` (`top|jungle|middle|bottom|utility|""`), `spell1Id`, `spell2Id`,
`puuid`, `gameName`, `tagLine`, `nameVisibilityType`, `isAutofilled`, ...

What we can and can't see:
- **Enemies**: `championId` appears only once they lock. No hovers, `assignedPosition` is `""`,
  spells are `0`, ids are blank. **Nothing reveals enemy roles**, so they're inferred.
- **Allies**: positions, hovers, locked champions and **summoner spells** are visible. A Smite on
  a non-jungle ally signals a role swap.
- **Names**: in Ranked Solo/Duo, non-party allies show as "Ally 1-5" and enemies are never
  shown. We don't use names at all in champ select (`POLICY.md`).

`actions` is a list of **turns**; each turn is a list of actions taken in parallel. Each action:
`id`, `actorCellId`, `championId`, `type`, `completed`, `isInProgress`, `isAllyAction`,
`pickTurn`. Types include `pick`, `ban`, `ten_bans_reveal`, and others (`vote`,
`phase_transition`, ...). **Unknown types must be ignored, not crash.** `championId` can be `0`.

`timer.phase`: `PLANNING`, `BAN_PICK`, `FINALIZATION`, `GAME_STARTING`, or `""`.
Time left in phase = `adjustedTimeLeftInPhase + internalNowInEpochMs - now`. Patch 26.1
shortened champ select timers, so finalization is short: the report must be fast.

**Seen in real recordings** (ranked solo, patch 16.19; the sample drafts in
`tests/fixtures/champselect/` keep the format with made-up champions and times):
- Turn layout: `[10 bans]`, `[ten_bans_reveal]` (actor cell `-1`), then picks 1-2-2-2-2-1.
  Enemy pick actions show the champion once completed.
- `pickTurn` is `0` on every action and player: useless. Use the turn index.
- The `bans` object is empty (`numBans: 0`): bans only appear as `ban` actions.
- **Cells are pick slots; players move between them.** A pick-order swap moves the two players
  to each other's cells, and each cell's `assignedPosition` changes with them. For the local
  player, `localPlayerCellId` changes (seen live: cell 9 to cell 7 mid-draft).
- Allies' hovers (`championPickIntent`) are visible; enemies' are `0`.
- `trades`, `pickOrderSwaps`, `positionSwaps`: lists of `{cellId, id, state}` with states
  `AVAILABLE`, `BUSY`, `RECEIVED`, `INVALID`. Emptied at `GAME_STARTING`.
- Player fields not listed above: `isAutofilled`, `playerAlias`, `pickMode`. Top-level `id` is
  the session's own id (a long token; the recorder blanks it).
- Dodges, champion trades: not seen yet.

## 4. Turning a session into a GameState (`lcu/champselect.py`)
1. **Queue gate.** Continue only for queue ids 400, 420, 440, 700 (draft modes with positions).
   Swiftplay (480) has no champ select; ARAM, Arena and customs are skipped with a one-line message.
2. **My team** is `myTeam`, located by `localPlayerCellId`. Don't assume cells 0-4: your team
   can be cells 5-9. Read `localPlayerCellId` from the **latest** session: it changes when you
   swap pick order.
3. **Who plays what**: take champions from the `myTeam`/`theirTeam` arrays, not from actions.
   Trades during finalization change the arrays.
4. **Pick order**: for each locked champion, find the `pick` action with that `championId` and
   use its **turn index** (outer list index). Compare turns, not cells or action ids. Enemy and
   ally picks are never in the same turn, so "opponent picked after me" =
   `opp_turn > my_turn`. [verify: whether a trade rewrites the action's `championId`]
5. **Bans** come from `ban` actions (the `bans` object can be empty).
6. **My role**: final `assignedPosition` of my cell (role swaps during champ select change it).
7. **Ally role swaps**: if a non-jungle ally has Smite and the assigned jungler doesn't, swap
   them and add a note.
8. **Enemy roles**: `analysis/role_inference.py` (see `STATS.md` for role rates).
9. **Champion ids**: numeric `championId` -> Data Dragon id via `champions.csv` `key`. An
   unknown key (a brand-new champion before `scout refresh`) becomes a placeholder with a
   warning, not a crash.

## 5. Events: WebSocket with polling fallback (`lcu/events.py`)
- Connect to `wss://127.0.0.1:<port>/` with the same auth and certificate. Protocol is WAMP 1.0:
  send `[5, "OnJsonApiEvent_lol-champ-select_v1_session"]` to subscribe; events arrive as
  `[8, "<event name>", {"data": ..., "eventType": "Create|Update|Delete", "uri": "..."}]`.
- Do a GET first: subscribing doesn't send the current state.
- Subscribe to specific events, not the catch-all `OnJsonApiEvent` (it duplicates events and
  floods megabytes). Ignore empty or non-JSON frames.
- Polling every `client.poll_seconds` (default 1 s) is the fallback and is fine for v1.
- **How we use it** (`scout/lcu/events.py`): events only wake the watcher early; the state is
  always read with GETs, so there is one code path whether the socket works or not. Checked
  live 2026-10-02: the socket connects with the pinned certificate and the same basic auth.
  Subscribed: gameflow phase, gameflow session, champ select session.

## 6. `scout watch` state machine (`lcu/watcher.py`, built in M6)
```
Idle --(phase ChampSelect)--> Drafting
Drafting: as picks lock, queue stats pre-fetches (M8); until I lock, update pick options (M9b).
          No report yet.
Drafting --(timer.phase FINALIZATION or GAME_STARTING, and all ten picks locked)--> Final
Final:    no report (2026-10-03: one report per game, never a draft read). The app shows
          "Picks locked: your report comes at the loading screen". Trades and swaps keep
          updating the draft, which the report at loading uses; stats keep pre-fetching.
Drafting/Final --(phase GameStart, InProgress or any later game phase)--> Loading if the draft
          was complete (all ten picks); otherwise straight to InGame, with no report.
Loading:  read the gameflow session each poll until its roster has summoner spells. Then
          confirm or correct enemy roles, add everyone's spells, start the players' records
          (M16) and the likely-duo / one-trick check (M11), and build the report (saved with
          its claims for the post-game check). The app shows "Writing your report" while the
          writer waits (up to 15 s) for the records and the duo check, then writes it all in
          (the duo lines as a "Loading screen" section); the written report is the one report
          shown --> InGame. With the AI writer off, the rules version is shown at once; if the
          writer fails, the rules version is shown, labelled. If the phase leaves GameStart
          before the roster shows, the report is built with the guessed roles ("Final report
          (roles guessed)") --> InGame.
InGame:   nothing new is computed from the game. Work started from pre-game data can land
          shortly after it starts: the written report, the players' records and the duo lines
          (both re-render a report already shown).
          While the phase is still GameStart, stats that were loading when the final report was
          built re-render it once, still as the final report ("Final report (stats arrived)");
          the LLM writes it again only if its input changed (the same input reuses the written
          text).
InGame --(first of WaitingForStats, PreEndOfGame, EndOfGame)--> post-game check (M10, in the
          background, if a final report was saved) --> Idle
Loading/InGame --(phase None, Lobby or another non-game phase)--> Idle, no post-game check
Drafting/Final --(phase leaves ChampSelect for a non-game phase, or a new champ select)--> Idle:
          dodge, discard.
```
- **Background work waits for the game** (`Watcher.idle()`, `BUSY_PHASES`): the app's
  match-data collector (M19), its 6-hourly data refresh and its update check run only while the watcher is idle
  and the client's phase isn't `ChampSelect`, `GameStart`, `InProgress` or `Reconnect`, even for
  a game the watcher isn't following (Swiftplay has no champ select; the app may open
  mid-game). A collector run stops before its next game as soon as that changes. Installing an
  update is refused until then, and a settings reload waits too. They resume once the game is
  over (`WaitingForStats` on).
- Every champ select is also recorded (the watcher hands its reads to the recorder), unless
  `scout watch --no-record`.
- Reports print in the terminal and save to `reports/<date>_<time>_<role>_<champ>.md`; a
  re-render overwrites the same file, and a dodge deletes it.
- Non-draft queues (ARAM, Arena, Swiftplay, customs, ...) print one line and get no report.
- A bad read is logged to `reports/debug/watch_errors.log` and the watch carries on; a
  certificate problem stops it with a message.

## 7. Recording fixtures (`scout record`, `lcu/recorder.py`)
Built first (M1) to collect real drafts. Recordings stay on the PC that made them (your
recordings folder); tests use made-up samples in the same format (CLAUDE.md hard rule 10).
- Save each distinct session snapshot from champ select start to the end, plus part of the
  gameflow session, to `<your Sidekick folder>/recordings/<date>_<queue>_<myrole>_champ<id>.json` as
  `{"meta": {...}, "gameflow": {...}, "snapshots": [{"elapsed_s", "phase", "session"}, ...]}`.
  The champion is its numeric id until static data exists (M2).
- **Deduplicated**: a change only in `counter`, the timer's countdown fields, or skins isn't a
  new snapshot. Draft-queue champ selects only (400, 420, 440, 700) unless `--all-queues`.
- **Ends** when the phase leaves `ChampSelect`: `game_started` (GameStart, InProgress, ...),
  `dodged` (any other phase, or a new `gameId` appears), or `stopped` (Ctrl+C). Files from
  dodges and stops get a `_dodged` / `_stopped` suffix. Closing the client mid-draft doesn't end
  the recording.
- **Scrub before writing** (`scout/lcu/recorder.py`): delete `chatDetails` (it holds a real chat
  token), and blank `puuid`, `summonerId`, `obfuscatedPuuid`, `obfuscatedSummonerId`,
  `gameName`, `tagLine`, `gameId`, `internalName`, `summonerInternalName`, `summonerName`
  wherever they appear. Safety net: any other string of 32+ token-like characters is blanked
  and listed in `meta.blanked_tokens`, so a new identifier field can't slip through.
- **Gameflow session: allowlist, not scrub.** It holds server addresses, dodger ids and, from
  the loading screen on, every player's identity. Only `phase`, `gameData.isCustomGame`,
  `gameData.queue.{id,type,gameMode,mapId,isRanked,description}`, `map.id` and
  `gameDodge.{phase,state}` are kept.
- **Game-start roster** (`game_start` in the file): once the phase reaches `GameStart` or
  `InProgress`, the recorder reads the gameflow session again and keeps, per player, only
  `championId`, `selectedPosition`, `selectedRole` (from `gameData.teamOne`/`teamTwo`) and
  `championId`, `spell1Id`, `spell2Id` (from `gameData.playerChampionSelections`). It waits
  for the roster to fill in during loading, but saves without it (`null`) at `InProgress`.
  This is the answer key for enemy role guesses (`ROLES.md`). [verify on the first recorded
  game: which of these fields the client fills in for enemies]
- A test asserts every recorded fixture contains none of the scrubbed values.
- Recording is passive and read-only like everything else.

## Sources
- Patch 26.16 LCU swagger: https://github.com/KebsCS/lcu-and-riotclient-api
- Connecting and WebSocket basics: https://hextechdocs.dev/getting-started-with-the-lcu-api/ and
  https://hextechdocs.dev/getting-started-with-the-lcu-websocket/
- WMIC removal: https://github.com/Pupix/lcu-connector/issues/40
- Riot cert and LCU support stance: https://developer.riotgames.com/docs/lol
- Vanguard FAQ: https://www.riotgames.com/en/DevRel/vanguard-faq
- Queue ids: https://static.developer.riotgames.com/docs/lol/queues.json
