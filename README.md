# Sidekick

A personal League of Legends **pre-game scouting report**. When champion select ends, it reads
the draft from your League client and shows a short report for the role you're playing: how your
lane goes at each stage, whether you got counter-picked and how to play into it, what both
junglers mean for you, ults and roamers that can join your fights, enemy combos, who must not get
fed, and a one-line game plan.

Read-only and pre-game only: it never changes anything in the client and shows nothing during
the game. Personal use (a friend can install it from this repo; see below). The package and
command are called `scout`.

**Status:** the Sidekick app follows your League client by itself: pick options while you
draft, then one report at the loading screen, as soon as it shows everyone's summoner spells,
written by Claude Haiku (about 1 cent a game) with the roles, spells, players and likely duos in
it. Nothing is shown as a report before that. Progress: [`docs/TASKS.md`](docs/TASKS.md);
everything asked for and where it stands: [`docs/REQUESTS.md`](docs/REQUESTS.md).

## Using it
Open **Sidekick** from the Desktop or the Start menu and leave it open while you play (a second
monitor works well; it remembers where you put it). It waits for the League client and a game
on its own. ARAM and other modes are skipped. Reports are saved to `reports/`.

**History** (top right) lists your past games on this PC, newest first: when, which of your
accounts, the matchup, and how many of the report's calls came true after the game. Open one to
see its whole dashboard again (Both teams too), with the post-game results under it. It's kept
in `reports/` on your PC only, never sent to GitHub.

**Champions** (top right) is your list: the champions you play in each lane with 1-5 comfort
stars, saved as you change it. Pick suggestions use it. Each League account keeps its own list
(in `pools/`), and the page follows whoever is logged in to the client. It suggests champions
from your own games: ones you played 4+ times in a lane recently (Add or No), and "Suggest from
my most-played" (your champion mastery).

Everything else is in **Settings** (top right):
- **Account and Riot key**: who is logged in and your region, both read from the League
  client (nothing to type); paste a Riot API key (tested before it's saved); and "Players at
  the loading screen", each visible player's OP.GG record on their champion (rank, games, win
  rate, average K/D/A; never names), on or off (`docs/POLICY.md`).
- **AI report writer**: on or off, today's cost, and the Anthropic key.
- **Data and updates**: refresh the data, **Check for updates** (gets the newest version from
  GitHub, restarts, refreshes the data), the match data collector, research (reminders, the
  research folder, applying results), shortcuts, and the reports and log folders.

**It keeps itself current** while it's open: it checks GitHub for a new version at start and
every 6 hours ("Update available" in the top bar), refreshes its data every 6 hours (a new
patch, OP.GG's numbers) when you're not in a game, and measures Riot's match data in the
background. What updates when, and every source: [`docs/PATCH_UPDATE.md`](docs/PATCH_UPDATE.md).

`scout watch` in a terminal opens the same app and also prints what it's doing. If something
goes wrong, `reports/debug/app.log` says what.

## Install (Windows)
Needs Windows, the League client, Python 3.11 or newer and Git (for updates). The command line
is needed once, for these steps; after that it's only the Sidekick app.

1. Open **PowerShell** (Start menu, type PowerShell) and install Python and Git (skip either if
   it's already installed):
   ```powershell
   winget install -e --id Python.Python.3.13
   winget install -e --id Git.Git
   ```
   (Or from the websites: [Python](https://www.python.org/downloads/), ticking "Add python.exe
   to PATH", and [Git](https://git-scm.com/download/win).)
2. **Close PowerShell and open a new one** (so it sees Python and Git), then:
   ```powershell
   git clone https://github.com/zchristensen01/sidekick.git $HOME\Sidekick
   cd $HOME\Sidekick
   powershell -ExecutionPolicy Bypass -File install.ps1
   ```
   That makes a private Python environment (`.venv`), installs Sidekick, adds the Desktop and
   Start-menu shortcuts and opens it. On first start it makes its settings files
   (`config.yaml`, `.env`, `pool.yaml`, all private) and downloads the champion data (about a
   minute).
3. From then on, open **Sidekick** from the Desktop or Start menu. Updates come from the app's
   "Update available" button; run `install.ps1` again only if an update says so.

For development (tests, lint), also: `.venv\Scripts\python -m pip install -e ".[dev]"`, then
`.venv\Scripts\Activate.ps1`, `scout doctor`, `pytest`.

Keys (both optional; paste them in Settings):
- `ANTHROPIC_API_KEY`: the written report at the loading screen calls Claude through the
  Anthropic API (console.anthropic.com, pay as you go, about 1 cent a game, capped per day).
  Without it, or with the AI writer off, the report is the rules version (same facts, as a
  list).
- `RIOT_API_KEY`: a free personal key from Riot. It lets the app measure Riot's match data in
  the background (gold at 10, lane push, level timings, jungle clears, per champion and role),
  check each report against your game afterwards (post-game), and spot enemy one-tricks at the
  loading screen. Without it, everything else works: pick options, OP.GG's numbers, the
  report.

### Getting a Riot API key
1. Go to https://developer.riotgames.com and log in with your Riot account.
2. Click **Register Product**, choose **Personal API Key**.
3. Describe it, e.g. "Sidekick: a personal pre-game scouting report. Reads my own League client
   (read-only). Uses League-EXP-V4 and Match-V5 to measure aggregate champion statistics from
   ranked games in the background (no player data stored), Match-V5 and Champion-Mastery-V4 at
   the loading screen, and Match-V5 for my own games afterwards. Not distributed."
   (`docs/POLICY.md` has the details if they ask.)
4. When it's approved, paste it in Settings, Account and Riot key (or run `scout key`). Until
   then, the development key on your dashboard works for 24 hours at a time: when Settings
   shows it as rejected, click "Regenerate API Key" on the dashboard and paste the new one. One
   key covers all your accounts.

There's no Riot login: the app reads the League client that's already logged in on your PC.

## Commands
| Command | What it does | Built in |
|---|---|---|
| `scout doctor` | Checks Python, config, keys (the Riot key with a live call; the Anthropic key's presence), data files, briefs, the client | M0 |
| `scout record [--all-queues]` | Saves scrubbed champ select sessions as test fixtures (`--all-queues`: ARAM and customs too) | M1 |
| `scout refresh [--static] [--stats] [--pool] [--force] [--prune]` | Updates static data (a new patch), OP.GG's stats when older than a day, and the review queue; `--static` or `--stats` does only that part (`--stats` refreshes the stats even if fresh); `--pool` also fetches matchup tables for everyone's champions (the app runs it every 6 hours); `--force` rebuilds static data anyway; `--prune` deletes old versions' files. Then reruns the backtest | M2, M8 |
| `scout review [champ]` | Walks unreviewed champion traits: accept, edit, or skip | M3 |
| `scout key` | Paste a new Riot API key into `.env` (tested first; never shown) | M11 |
| `sidekick` | The app (no console): what the Desktop shortcut opens | M14 |
| `scout pool [--show]` | Your champions per role in `pool.yaml`, with your most-played champions from the client as suggestions. The app's Champions page keeps one list per account instead (`pools/`; a new account starts from pool.yaml) | M9b, M14, M22 |
| `scout shortcut` | Puts Sidekick on the Desktop and in the Start menu | M14 |
| `scout research` | Rewrites the research prompts in `research/` with the current champion list and game facts (after a new patch) | M15 |
| `scout import-research [--yes]` | Reads agents' replies in `research/results/`, shows what would change, applies on OK (the app has a button for it) | M19 |
| `scout collect [--games N] [--status]` | Measures Emerald+ ranked games from Riot's match data (the app does it in the background); `--status` shows coverage and the OP.GG cross-check | M19 |
| `scout draft-traits [<champ>] [--all-missing]` | Drafts a traits row for you to check (`--all-missing`: every champion without a row) | M3 |
| `scout report --file <game.yaml> [--role r] [--debug] [--write] [--fetch]` | Offline report for a saved or hand-written game (`--debug` shows each line's source; `--write` also has the LLM write it, about 1 cent; `--fetch` gets missing OP.GG stats first, free) | M5, M7, M8 |
| `scout demo [--role r] [--file <game.yaml>]` | Opens the app window and plays a saved game through its screens, so you can see it without the League client | M13 |
| `scout watch [--no-record] [--no-window] [--no-llm] [--no-stats]` | Opens the Sidekick app and also prints to the terminal (`--no-window`: terminal only). Waits for the client and a game, shows pick options for your role until you lock, then one report at the loading screen (written by the AI if it's on) | M6, M7, M8, M13, M14 |
| `scout postgame [--file reports/<report>.json] [--note/--no-note]` | Checks a report's predictions against what happened (the app does it after each game; default: the newest unchecked report), then offers to add a matchup note; results in `data/history/` | M10 |
| `scout backtest [--games N] [--fetch]` | Grades every read on the games the collector stored, against always guessing the usual outcome; results in `data/history/backtest.csv`. `--fetch` first gets OP.GG's matchup tables the games need (otherwise no network); `scout refresh` reruns it | M20 |

## Developing
- `pytest` (offline, always) and `ruff check .` before every commit.
- Start with [`CLAUDE.md`](CLAUDE.md); it indexes every doc in [`docs/`](docs/).
- Commands that talk to the League client (`watch`, `record`) need Windows Python. Offline work
  runs anywhere, including WSL.

## Running it on a friend's PC
The repo is public, so a friend doesn't need to be a collaborator. They follow the Install steps
above once (two `winget` lines, then three lines to clone and install), and from then on only
use the app: it updates itself from GitHub ("Update available", one click), refreshes its own
data, and everything they set is in the app (Champions; Settings for keys and the AI writer).
Being a collaborator only matters for pushing changes; if the repo is ever made private, add
them as a collaborator first, or their copy stops updating.

What they get, and what's shared:
- Their own settings, keys and champion lists (`.env`, `config.yaml`, `pool.yaml`, `pools/`,
  `reports/`, `data/generated/`, `data/history/` stay out of git), so they start clean.
- Everything in `data/manual/` (game facts, class definitions, champion notes, matchup briefs)
  and the research results come with each update. Research is the owner's job: their app has
  research reminders off, so "Research due" never shows for them.
- Without keys: pick options, OP.GG's numbers and the report's rules version. With
  their own Riot key: measured match data on their PC, the post-game check, one-tricks. With
  their own Anthropic key: the written report (about 1 cent a game).
- If an update ever stops with "changes files you've edited here", they ask the owner; it only
  happens if they applied research results themselves.

## Refresh while the app is closed (optional)
The app refreshes its data every 6 hours while it's open, so this is only for a PC that's on
without the app open. In PowerShell, once:
```powershell
schtasks /Create /SC DAILY /ST 05:00 /TN "Sidekick refresh" /TR "$HOME\Sidekick\.venv\Scripts\scout.exe refresh --pool"
```
(`$HOME\Sidekick` is where the install steps put it; use your own Sidekick folder if it's
elsewhere.)
It runs at 5 AM if the PC is on (OP.GG is free; no API cost). Check it with
`schtasks /Query /TN "Sidekick refresh"`, remove it with `schtasks /Delete /TN "Sidekick refresh"`.
Results go to `data/generated/REFRESH_LOG.md`.
