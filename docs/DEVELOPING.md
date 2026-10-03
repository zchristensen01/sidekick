# Developing Sidekick

For people changing Sidekick. Players only need the installer: see the [README](../README.md).
Start with [`CLAUDE.md`](../CLAUDE.md); it indexes every design document in `docs/`.

## Setup (Windows)
Needs Python 3.11 or newer and Git.
```powershell
git clone https://github.com/zchristensen01/sidekick.git
cd sidekick
powershell -ExecutionPolicy Bypass -File tools\dev_setup.ps1
.venv\Scripts\Activate.ps1
scout doctor
pytest
ruff check .
```
`tools\dev_setup.ps1` makes a private Python environment (`.venv`) and installs Sidekick with
the test tools. Offline work (tests, `scout report`) runs anywhere, WSL included; commands that
talk to the League client (`watch`, `record`) need Windows Python next to the client.

## Where files go (DECISIONS #113)
- **The program's own files** are the repo folder: code, rules, the shared champion knowledge
  (`data/manual/`, hand-owned), the writer's prompt, the example settings.
- **Your own files** (settings, keys, champion lists, notes, reports, recordings, downloaded
  and measured data) are in `%LOCALAPPDATA%\Sidekick`, for a developer copy and the installed
  app alike. Nothing personal ever sits in the repo folder (CLAUDE.md hard rule 10).
- `SCOUT_HOME=<folder>` keeps everything in one folder instead (the tests do).
  `SIDEKICK_USER_DIR=<folder>` moves only your own files, for trying a build without touching
  your real ones.

## The owner's PC
`owner: true` in config.yaml marks the PC of whoever maintains Sidekick: it collects Riot's
match data, runs the backtest and shows research reminders (`docs/MATCH_DATA.md`). Everyone
else has `owner: false` (the default) and gets the results with each release. Research runs
from a developer copy: `research/` holds the prompts and replies.

## Commands
`scout` from the developer environment. The installed app has the same commands as
`sidekick-helper.exe` (it runs data refreshes with it), but players never need them.

| Command | What it does | Built in |
|---|---|---|
| `scout doctor` | Checks Python, config, keys (the Riot key with a live call; the Anthropic key's presence), data files, briefs, the client | M0 |
| `scout record [--all-queues]` | Saves scrubbed champ select sessions to your recordings folder (`--all-queues`: ARAM and customs too). Never into the repo: test data is made up (hard rule 10) | M1 |
| `scout refresh [--static] [--stats] [--pool] [--force] [--prune]` | Updates static data (a new patch), OP.GG's stats when older than a day, and the review queue; `--static` or `--stats` does only that part (`--stats` refreshes the stats even if fresh); `--pool` also fetches matchup tables for everyone's champions (the app runs it every 6 hours); `--force` rebuilds static data anyway; `--prune` deletes old versions' files. On the owner's PC it then reruns the backtest | M2, M8 |
| `scout review [champ]` | Walks unreviewed champion traits: accept, edit, or skip | M3 |
| `scout key` | Paste a new Riot API key into your `.env` (tested first; never shown) | M11 |
| `sidekick` | The app from a developer copy (no console) | M14 |
| `scout pool [--show]` | Your champions per role in `pool.yaml`, with your most-played champions from the client as suggestions. The app's Champions page keeps one list per account instead (`pools/`; a new account starts from pool.yaml) | M9b, M14, M22 |
| `scout shortcut` | Puts "Sidekick (developer)" on the Desktop and in the Start menu (never over the installed app's shortcuts) | M14 |
| `scout research` | Rewrites the research prompts in `research/` with the current champion list and game facts (after a new patch) | M15 |
| `scout import-research [--yes]` | Reads agents' replies in `research/results/`, shows what would change, applies on OK (the app has a button for it on the owner's PC) | M19 |
| `scout collect [--games N] [--status]` | Measures Emerald+ ranked games from Riot's match data (the app does it in the background on the owner's PC); `--status` shows coverage and the OP.GG cross-check | M19 |
| `scout draft-traits [<champ>] [--all-missing]` | Drafts a traits row for you to check (`--all-missing`: every champion without a row) | M3 |
| `scout report --file <game.yaml> [--role r] [--debug] [--write] [--fetch]` | Offline report for a saved or hand-written game (`--debug` shows each line's source; `--write` also has the LLM write it, about 1 cent; `--fetch` gets missing OP.GG stats first, free) | M5, M7, M8 |
| `scout demo [--role r] [--file <game.yaml>]` | Opens the app window and plays a saved game through its screens, so you can see it without the League client | M13 |
| `scout watch [--no-record] [--no-window] [--no-llm] [--no-stats]` | Opens the Sidekick app and also prints to the terminal (`--no-window`: terminal only) | M6, M7, M8, M13, M14 |
| `scout postgame [--file <report>.json] [--note/--no-note]` | Checks a report's predictions against what happened (the app does it after each game; default: the newest unchecked report), then offers to add a matchup note | M10 |
| `scout backtest [--games N] [--fetch]` | Grades every read on the games the collector stored, against always guessing the usual outcome; `--fetch` first gets OP.GG's matchup tables the games need | M20 |

## Releases (M24, DECISIONS #114-#117)
Players install `SidekickSetup.exe` and update from GitHub Releases; nobody needs Git or Python.
- **Automatic:** every push to `main` that changes the app (code, `data/manual/`, the writer's
  prompt, settings examples, dependencies, packaging) runs `.github/workflows/release.yml` on
  GitHub: tests and lint, then `packaging/build.py`, then a release `v<year>.<month>.<day>.<run>`
  with `SidekickSetup.exe` and `latest.json`. Docs-only pushes don't make a release. The
  Actions tab has "Run workflow" to make one by hand.
- **What the app checks:** `latest.json` from the newest release (version, what changed, the
  installer's address and SHA-256). It downloads the installer, checks the fingerprint, runs
  it quietly and reopens (`scout/app/update.py`). A developer copy updates with git instead.
- **Build locally:** `pip install -e ".[build]"`, install Inno Setup 6
  (`winget install -e --id JRSoftware.InnoSetup`), then
  `python packaging/build.py --version 2026.10.5.0`. `--no-installer` stops after the app
  folder (`dist/Sidekick`). Try it without touching your files:
  `$env:SIDEKICK_USER_DIR = "$env:TEMP\sidekick-trial"; dist\Sidekick\Sidekick.exe`.
- **Library versions** for releases are pinned in `packaging/constraints.txt`. To move them:
  upgrade in `.venv`, run `pytest` and a local build, then rewrite the file with
  `python -m pip freeze --exclude-editable` (keep its header).
- **Unsigned on purpose** (no monthly certificate fee): Windows asks once before the first run
  (the README walks players through it).

## Before every commit
- `pytest` (offline, always) and `ruff check .`.
- Nothing personal in what you commit (hard rule 10): no keys, real games, reports,
  recordings, names or user folders. Commits use the repo's noreply address (git config).
- Tick the task in `docs/TASKS.md`, add a line to `docs/CHANGELOG.md`, record design changes
  in `docs/DECISIONS.md`.
