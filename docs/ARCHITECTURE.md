# ARCHITECTURE

## Big picture
```
 League client (LCU, local, read-only)            Internet sources (scout refresh, cached)
           |                                        Data Dragon, CommunityDragon, LoL wiki,
     lcu/ watcher + recorder                        OP.GG MCP; Riot API (match data collector
           |                                        -> stats.sqlite; loading screen; post-game)
     lcu/champselect  -> GameState                      data/ refresh -> data/generated/
           |                                                   |
           |        model/ facts  <--- data/store <--- data/generated + data/manual
           v
     analysis/   insights: lane_state, lane_timeline, gankability, jungle_threat, jungle_plan,
                 priority, roam, cross_map, team_profile, threats, role inference         (tested Python)
           |
     rules/engine   -> fired rules (YAML, each with section, audience, priority)
     counterpick    -> counter-pick block
           |
     report/select  -> per-role sections, the top items of each (the writer fits the word budget)
     report/builder -> writer input JSON (REPORT_AGENT.md)
     report/writer  -> LLM returns structured JSON -> validator -> render (terminal + reports/)
                       (on failure: deterministic text from the selected items)
```
Key idea: **code decides, the LLM only writes.** Everything that judges the game (who wins a
lane, who to gank, how bad a counter is) is deterministic, tested Python plus YAML rules. The
LLM gets one JSON object of already-chosen points and turns it into readable text. When a
report is wrong, the rule ID or insight name points at the exact thing to fix.

## Layers and their contracts
| Layer | Package | Input | Output | Notes |
|---|---|---|---|---|
| Client | `scout/lcu/` | the running League client | raw session JSON, gameflow phase | GET only. See `LCU.md`. |
| Game model | `scout/lcu/champselect.py`, `scout/model/` | session JSON or a fixture YAML | `GameState` | Maps LCU positions and numeric champion keys at the edge. |
| Facts | `scout/data/store.py`, `scout/model/champ.py` | generated + manual data | `ChampFacts` per champion | Merges static data, traits and briefs, overrides, stats; marks missing/unreviewed. See `KNOWLEDGE.md`. |
| Analysis | `scout/analysis/` (`insights.py` runs it) | `GameState` + facts | `Insights` (with reasons) | Pure functions, no I/O. See `ROLES.md`. |
| Rules | `scout/rules/` | `Insights` contexts | fired rules | YAML conditions. See `RULES.md`. |
| Counter-pick | `scout/counterpick.py` | `GameState`, facts, stats | counter-pick block | See `COUNTERPICK.md`, `STATS.md`. |
| Selection | `scout/report/select.py` | fired rules, insights, my role | ordered sections of items | Per-role section order and item caps (`ROLES.md`). |
| Writer | `scout/report/` | writer input JSON | rendered text | See `REPORT_AGENT.md`. |
| Data refresh | `scout/data/` | internet sources | `data/generated/` | See `DATA.md`. |
| Post-game | `scout/postgame/` | saved report + Riot Match-V5 | prediction check results | M10. |

Rules of thumb:
- Analysis, rules, selection and builder never do I/O. They take data in and return data, so
  every one of them is tested offline with fixtures.
- Missing data never crashes the pipeline. A champion with no traits row gets `None` traits,
  conditions on `None` are false, and a warning goes into the report.
- Every external call has a timeout and a fallback. The report must still come out with the
  network unplugged (rules and traits only, with a one-line notice).

## Folder layout
```
sidekick/                    # repo root (GitHub: zchristensen01/sidekick)
  CLAUDE.md  README.md
  pyproject.toml             # package "scout": commands "scout" and "sidekick" (the app, no console)
  config.example.yaml        # the app copies it to your folder as config.yaml on first start
  .env.example               # likewise .env: RIOT_API_KEY, ANTHROPIC_API_KEY
  packaging/                 # the installed app (M24): PyInstaller spec, Inno Setup script,
                             # build.py, pinned library versions (docs/DEVELOPING.md, Releases)
  .github/workflows/release.yml  # tests, build and publish a release when the app changes
  tools/dev_setup.ps1        # a developer's .venv with the test tools (players use the installer)
  tools/make_icon.py         # draws scout/app/sidekick.ico and sidekick.png
  research/                  # prompts for facts with no automatic source (written by Sidekick),
                             # results/ (agents' replies; done/ once applied), status.csv
  docs/
  prototype/                 # v0 reference code, never imported
  scout/
    __main__.py              # `python -m scout` (a developer copy's app runs `python -m scout refresh`)
    cli.py                   # typer app: every `scout` command (README, Commands)
    config.py                # config.yaml + .env -> typed Config, validated; in-place value edits
    paths.py                 # every filesystem location: the program's files vs your own (M24)
    version.py               # the installed app's version (build.json); "dev" from source
    pool.py                  # pool.yaml: champions per lane with comfort stars (M14)
    accounts.py              # one pool per League account; suggestions from your games (M22)
    picks.py                 # pick suggestions in champ select (M9b)
    loading.py               # loading-screen checks: duos, one-tricks (M11)
    research.py              # writes the prompts in research/ (`scout research`)
    research_import.py       # reads agents' replies in research/results/, applies on OK (M19)
    reviewing.py             # `scout review`: walk the review queue, accept or edit traits rows
    llm.py                   # the LLM clients (Anthropic, Ollama) the writer and draft-traits use
    app/                     # the Sidekick app (M13, M14)
      main.py                # the app: first-run setup, session loop, background jobs, the page's actions (Settings, Champions, History); `sidekick`
      session.py             # builds the watcher, stats, writer and client (app and scout watch)
      window.py              # the pywebview window and the page's bridge
      dashboard.html         # every screen, Settings, Champions, History, Both teams (HTML/CSS/JS, no internet)
      update.py              # the Update button: releases (installed) or git (developer copy)
      portraits.py           # champion pictures from Data Dragon, cached
      shortcut.py            # a developer copy's shortcuts (the installer makes the app's)
      sidekick.ico  sidekick.png
    model/
      roles.py               # Role, Lane, Queue enums; LCU position and queue-id mapping
      game.py                # Pick, GameState
      gamefile.py            # hand-written game YAMLs (tests/fixtures/games/) -> GameState
      champ.py               # ChampFacts (static + traits + stats, with provenance)
    data/
      schemas.py             # column lists for every CSV, single source of truth
      store.py               # load/validate CSVs and the stats database
      patch.py               # Data Dragon version <-> patch label helpers
      ddragon.py  cdragon.py  wiki.py  opgg.py  riot.py   # one module per source
      briefs.py              # matchup briefs: parse, validate, append drafted rows, find stale ones
      draft.py               # `scout draft-traits`: the LLM drafts a traits row for review
      patch_updates.py       # mid-patch updates (hotfixes) from the wiki's patch page (M21)
      sourced.py             # Riot's ratings and the wiki's mechanics over the drafted traits (M15)
      stats_db.py            # stats.sqlite: OP.GG numbers per patch (M8), measured totals and game records (M19, M20)
      measure.py             # one game's figures per champion and role, from Riot's match and timeline (M19)
      collector.py           # walks Riot's Emerald+ ladder and measures new games (M19)
      stats_service.py       # fetch during a draft, refresh, look up per game (M8)
      fetch.py               # polite HTTP client with a per-version file cache
      static.py              # merge sources into the static CSVs, validate, diff for review
      refresh.py             # the scout refresh pipeline
      review.py              # review queue
    lcu/
      connection.py          # find the client (process args, then lockfile), pinned cert
      client.py              # read-only REST client (GET only)
      riotgames.pem          # Riot's certificate for the client's local port (pinned)
      events.py              # websocket subscription (WAMP), with polling fallback
      champselect.py         # session JSON -> GameState
      watcher.py             # gameflow state machine for scout watch
      recorder.py            # scout record: scrubbed session snapshots -> your recordings folder
    analysis/
      insights.py            # runs the analysis: lineup, lanes, ganks, threats, stats -> Insights
      role_inference.py  lanes.py  ganks.py  jungle.py  roam.py  team.py  threats.py  stats.py
      players.py             # each champion in the game: kit, ratings, measured figures (M17)
      measured.py            # measured figures, levels and changes since last patch (M19)
      role_pool.py           # which roles a champion is really played in (M19)
    rules/
      engine.py  context.py  league_rules.yaml
    counterpick.py
    report/
      select.py  builder.py  writer.py  validator.py  render.py
      view.py                # the dashboard's screens as plain dicts (M13)
      past.py                # past games for History: saved screens and post-game results (M23)
      window.py              # the old report window (tkinter), fallback without pywebview
    player_cards.py          # players' records at the loading screen (M16)
    postgame/                # M10
      claims.py              # what the final report predicted, saved next to it
      grade.py               # each claim against the Match-V5 match and timeline
      check.py               # fetch, grade, record, summarize
      history.py             # data/history/postgame.csv and rule_accuracy.csv
      backtest.py            # every call graded on the stored games; track records (M20)
  data/
    manual/                  # hand-owned, committed. Code never overwrites (append or scout review only)
  tests/
    fixtures/champselect/    # made-up sample sessions in the client's real format (hard rule 10)
    fixtures/games/          # hand-written game YAMLs
    fixtures/sources/        # recorded raw responses from each data source
    golden/                  # expected sections and fired rule IDs per game fixture

%LOCALAPPDATA%\Sidekick\     # each Windows user's own files (scout/paths.py); never in git.
                             # The installed app and a developer copy use the same folder.
  config.yaml  .env          # settings and keys (Settings writes them)
  pool.yaml  pools/          # champions per lane with comfort stars; one list per account (M22)
  matchup_notes.csv          # your own notes, shown as "Your notes"
  recordings/                # scrubbed champ select recordings (scout record, the app)
  reports/                   # each game's report, claims and History screen; debug/ logs
  data/
    generated/               # machine-owned: static data and OP.GG numbers (rebuilt by scout
                             # refresh); stats.sqlite also holds the collected match data (M19),
                             # which a refresh can't rebuild
    cache/                   # raw API responses, champion pictures, update downloads
    history/                 # post-game results (append-only, M10) and backtest.csv (M20)

%LOCALAPPDATA%\Programs\Sidekick\   # the installed app (SidekickSetup.exe; updates replace it)
  Sidekick.exe               # the app window
  sidekick-helper.exe        # the same `scout` commands with a console, for the hidden refresh
  unins000.exe
  _internal/                 # Python and libraries, scout/, data/manual/, docs/REPORT_AGENT.md,
                             # the example settings, build.json
```

## Core types
```python
class Role(StrEnum):
    TOP, JUNGLE, MID, BOT, SUPPORT  # values "top", "jungle", ...


class Lane(StrEnum):
    TOP, MID, BOT


class Queue(StrEnum):
    RANKED_SOLO, RANKED_FLEX, NORMAL_DRAFT, CLASH, OTHER


@dataclass(frozen=True)
class Pick:
    champ_id: str  # Data Dragon id, e.g. "LeeSin", "MonkeyKing" (Wukong)
    role: Role
    role_confidence: float  # 1.0 for allies; inferred for enemies
    pick_turn: int | None  # index of the draft turn this champion was locked in
    spells: tuple[str, ...]  # summoner spells ("flash", "smite"), once known


@dataclass
class GameState:
    ddragon_version: str  # e.g. "16.19.1"; patch labels come from data/patch.py
    queue: Queue
    my_role: Role
    ally: dict[Role, Pick]
    enemy: dict[Role, Pick]
    enemy_role_alternatives: list[RoleAssignment]  # other plausible enemy assignments
    notes: list[str]  # e.g. "role swap detected: Elise has Smite"
    bans: list[str]
    enemy_role_odds: dict[Role, list[tuple[str, float]]]  # per role, likeliest champion first
    side: str  # blue | red (our team's map side) | "" unknown
```
`Pick.role_confidence` for an enemy is the probability that champion really plays that role
(summed over every assignment), not the probability of the whole assignment. Built by
`scout/lcu/champselect.py` (live) or `scout/model/gamefile.py` (hand-written YAML).
- **Champion ids**: Data Dragon ids everywhere internally ("Chogath", "MonkeyKing"). Display
  names only at render time. The LCU's numeric `championId` maps through the `key` column of
  `champions.csv`.
- **Patch**: store the raw Data Dragon version. In-game patch labels are Data Dragon major + 10
  (16.19.1 is patch 26.19). Riot hasn't documented this, so it lives in one function
  (`data/patch.py`) that's easy to change.

## The app's background jobs (`scout/app/main.py`)
| Job | When | What |
|---|---|---|
| Session | always | follows the League client: champ select, loading screen, game end (`lcu/watcher.py`) |
| Collector | every 30 s, only while idle | measures new Emerald+ games with its own share of the Riot key's rate limit (M19) |
| Update check | 20 s after start, then every 6 hours, only while idle | the newest release's latest.json (installed app) or `git fetch` (developer copy); "Update available" in the top bar (M21, M24) |
| Data refresh | checks every 5 minutes; runs when the last one is 6+ hours old and you're idle | `scout refresh --pool` in a hidden child process (`sidekick-helper.exe` when installed; M21, M24); on the research PC it also checks the wiki for hotfixes and rewrites the research prompts |
| Research due | worked out each minute | `research/status.csv` against the current patch; shown on the owner's PC (`owner: true`) |

"Idle" means the client isn't in champ select, the loading screen or a game (`Watcher.idle`,
even for a game Sidekick isn't following), and for the collector and the refresh, no other job
(refresh, update) running.

## Runtime: Windows
- Players run the installed app (`SidekickSetup.exe`, built by `packaging/`): its own Python
  inside, no admin rights, updates from GitHub Releases. A developer copy runs from the repo
  with `.venv` (`docs/DEVELOPING.md`). Both keep personal files in `%LOCALAPPDATA%\Sidekick`.
- The app runs on Windows, next to the League client: `scout watch`, `scout record` and
  anything else that talks to the client must run under Windows Python (3.11+).
- Offline work (tests, `scout report --file`, `scout refresh`) runs anywhere, including WSL.
- If you develop in WSL: in the default NAT networking mode, WSL can't reach the client's
  `127.0.0.1` port. Either run live commands with Windows Python, or set
  `networkingMode=mirrored` in `%UserProfile%\.wslconfig` and restart WSL.
- Use `pathlib` everywhere; never build paths with string concatenation or hard-coded slashes.
- `.gitattributes` forces LF line endings so the repo behaves the same on both sides.

## LLM writer
- Provider is configurable: Anthropic API (default) or a local Ollama model.
- System prompt = the PROMPT part of `docs/REPORT_AGENT.md`, loaded at runtime.
- One call per report, structured JSON output, validated, one retry, then the deterministic
  fallback. Details and model notes in `REPORT_AGENT.md`.

## Config
`config.example.yaml` documents every key. `scout/config.py` loads it into typed dataclasses,
checks values (roles, numbers in range, counter-pick bands in order, champion lists are lists
of ids) and fails with a clear message. Secrets come from `.env`, or from environment
variables of the same name.

## Dependencies
Runtime: `typer` (CLI), `httpx` (HTTP; OP.GG's MCP server is spoken over plain HTTP, no MCP
library), `websockets` (LCU events), `psutil` (find the client process), `pyyaml`,
`python-dotenv`, `anthropic` (writer), `pywebview` (the app window, Windows only).
Dev: `pytest`, `ruff`. Build: `pyinstaller`, plus Inno Setup 6 (not a Python package). No pandas: tables are small, and `csv` + dataclasses are easier to read.
The stats database is SQLite via the standard library (`sqlite3`).

## Testing strategy
- No network in tests, ever. Sources are tested against `tests/fixtures/sources/`, the client
  against made-up sample sessions in `tests/fixtures/champselect/` (the client's real format).
- Rules are tested two ways: small synthetic contexts per rule (fires / doesn't fire), and
  golden full games per role (expected sections and rule IDs).
- A contradiction test asserts that rules linked by `excludes` never fire together on the game
  fixtures (`scout/rules/engine.py` `conflicts`); it's a test, not a runtime check.
- A read-only test asserts the LCU client has no write methods.
