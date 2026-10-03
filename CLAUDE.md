# Sidekick (lol-scout): instructions for Claude Code

Read this file first, every session. Then read `docs/REQUESTS.md` (everything the owner has asked
for, with status) and `docs/TASKS.md` (build order and checkboxes), then the doc for your task.

## What this is
A personal, Windows-only Python app (package and CLI: `scout`) that produces a **pre-game
scouting report** for League of Legends. It reads champion select from the local League client,
works out lane matchups, counter-picks, gank targets, jungle threat, enemy combos, and who must
not get fed, then has an LLM write a short report **for whichever role the player is playing**.
Players get filled, so all five roles must work.

Personal use (a friend installs it from the public repo; not released). Repo: github.com/zchristensen01/sidekick (public: anyone can read it, so keys and personal
files stay gitignored).

## Docs (read the one you need)
| Doc | Read when |
|---|---|
| `docs/SPEC.md` | What to build, scope, acceptance criteria |
| `docs/ROLES.md` | Per-role report sections, shared insights, role rule packs |
| `docs/ARCHITECTURE.md` | Layers, folder layout, core types, Windows runtime, config |
| `docs/LCU.md` | Talking to the League client: connection, session fields, watch state machine, recording |
| `docs/DATA.md` | Every data source, file schemas, the stats database, refresh and update strategy |
| `docs/STATS.md` | How win rates are judged: sample size, shrinkage, patch blending, stats vs traits |
| `docs/TRAITS.md` | The hand-owned traits file, rubric, seeding, review |
| `docs/KNOWLEDGE.md` | What the report knows: ability text, champion and matchup briefs, items, timelines, jungle plans |
| `docs/RULES.md` | Rule format, scopes and paths, validation, tests, tuning |
| `docs/COUNTERPICK.md` | Counter-pick detection and "how to play into it" |
| `docs/REPORT_AGENT.md` | The LLM writer: input/output contract, validator, system prompt |
| `docs/POLICY.md` | What Riot allows. Read before any feature touching other players or the client |
| `docs/DECISIONS.md` | Why things are the way they are. Read before changing a design decision |
| `docs/PATCH_UPDATE.md` | Every data file, its source, how it's refreshed; the new-patch checklist |
| `docs/DEVELOPING.md` | Developer setup, every `scout` command, releases and the installer |
| `docs/MATCH_DATA.md` | The games the owner's PC collects: what's kept, what each gives, when it stops |
| `docs/future/` | Future projects, each with what it should do (the post-game review) |
| `research/` | Prompts for facts with no automatic source; results go in `research/results/` |
| `docs/REQUESTS.md` | Every request the owner has made, with status. Add new requests here first |
| `docs/TASKS.md` | Ordered milestones. Work top to bottom and tick boxes |
| `docs/REVIEW_BRIEF.md` | Self-contained summary of what the report considers (for outside reviews) |
| `prototype/` | Working v0 code. Port the ideas; never import from it |

## Hard rules (never break these)
1. **League client access is read-only.** Only `GET` requests and event subscriptions against
   the LCU. Never `POST`/`PATCH`/`PUT`/`DELETE`: no auto-accept, pick, ban, runes, nothing.
2. **Pre-game only.** No in-game overlays, timers, or live "do X now" advice. Advice is phrased
   as options with reasons (`POLICY.md`).
3. **Don't invent League facts, and draw no conclusions of our own** (2026-10-03). No
   hard-coded cooldowns, item names, damage numbers, spell ids, or champion claims in code or
   prompts. Facts come from `data/`, each from a named source (Riot, the LoL Wiki, OP.GG, Riot's
   patch notes). If no reputable source exists, leave it blank, add it to the review queue, and
   add a research prompt for the owner to run (`scout/research.py` writes the prompts in `research/`;
   don't edit those files by hand).
4. **`data/generated/` is machine-owned** (in each user's Sidekick folder, `%LOCALAPPDATA%\Sidekick`):
   rebuilt by `scout refresh`, never hand-edited.
   **`data/manual/` is hand-owned**: never overwritten by code. Only append, or edit through
   `scout review` with confirmation.
5. **Secrets** (Riot API key, Anthropic key) live in `.env`, never in code or git.
6. **Discover external tool names at runtime.** OP.GG's MCP tool names have changed before. List
   tools on connect and fail loudly if an expected tool or parameter is missing.
7. **No network in unit tests.** Use recorded fixtures in `tests/fixtures/`.
8. **Never identify hidden players.** No names or lookups of other players in champ select;
   skip anyone hidden by streamer mode; scrub identifiers from recorded fixtures.
9. Work in small, testable steps in the order of `docs/TASKS.md`. Tick the boxes and add a line
   to `docs/CHANGELOG.md` when a task is done. Record design changes in `docs/DECISIONS.md`.
10. **Nothing personal in git** (owner, 2026-10-03). No keys, account data, real games, reports,
   recordings, names or user folders in the repo, ever: each person's data lives in their own
   data folder on their PC. Test data is made up in the real formats (`DECISIONS.md` #110-111).
   Commits use GitHub's noreply address.

## Running it
- Live commands (`scout watch`, `scout record`) must run under **Windows** Python 3.11+, next to
  the League client. Offline commands and `pytest` run anywhere.
- From WSL in the default NAT networking mode, the client's local port is unreachable: use
  Windows Python for live work.
- Players install `SidekickSetup.exe` (`README.md`); developers: `docs/DEVELOPING.md` (setup,
  every command, how releases are built). `scout doctor` checks the setup.
- Each user's files (settings, keys, champion lists, reports, data) are in
  `%LOCALAPPDATA%\Sidekick`, for the installed app and a developer copy alike (`scout/paths.py`).

## Commands
```
scout doctor                 # check Python, config, keys, data, client reachability
scout refresh                # update static data and stats, update the review queue
scout watch                  # open the app with a terminal: pick options, then one report at loading
scout report --file tests/fixtures/games/<x>.yaml [--role jungle]   # offline report
scout review                 # walk the review queue, edit/confirm champion traits
scout draft-traits <champ>   # LLM drafts a traits row (reviewed=n) for the owner to check
scout record                 # save scrubbed champ select sessions (in your own data folder)
scout postgame               # check the newest unchecked report against what happened (M10)
scout backtest               # grade every read on the stored collected games (M20)
scout collect [--status]     # measure Emerald+ games from Riot's match data (M19)
scout import-research        # read agents' replies in research/results/, apply on OK
scout research               # rewrite the research prompts for what's due (the app does it too)
scout pool [--show]          # pool.yaml champions per role (the app keeps one list per account)
scout demo [--role r]        # play a saved game through the app's screens, no client needed
scout key                    # paste a new Riot API key into .env (tested first)
scout shortcut               # Desktop and Start-menu shortcuts for the app
pytest                       # all tests, offline
ruff check .                 # lint
```

## When the owner sends you something, do this
| The owner sends | You do |
|---|---|
| "This report was wrong" + the report | Find the cited rule IDs, insights and facts. Decide whether the **trait data**, the **insight formula**, the **rule condition**, or the **rule text** is wrong. Fix the smallest thing. Add a made-up fixture in `tests/fixtures/games/` that reproduces the case (not the real game: hard rule 10) and a golden file asserting the corrected result. Log it in `docs/CHANGELOG.md`. |
| A new rule idea ("vs X you should...") | Add it to `scout/rules/league_rules.yaml` with a new ID, the right `section` and `audience`, existing paths, and a `tests` block. If it needs a new path, add it in `scout/rules/context.py` and document it in `docs/RULES.md`. |
| "Champ X's traits are off" | Edit that row in `data/manual/champion_traits.csv` (the owner is the source of truth). Set `reviewed=y`, `reviewed_patch` to the current version, `source=owner`. |
| A matchup note ("Lee vs Elise: ...") | Append a row to the owner's own `matchup_notes.csv` in `%LOCALAPPDATA%\Sidekick` (shown as "Your notes"). It stays on their PC, never in git. |
| "This matchup advice is off" | Fix the row in `data/manual/matchup_briefs.csv` (or the champion's `key_note`/`ult_note`/`spike_note` if the problem is the champion, not the matchup). Set `reviewed=y`. |
| Patch notes (pasted text or a link) | List the champions with kit changes, add them to the review queue with the reason, and **propose** trait edits. Don't apply edits without their OK. |
| A champ select JSON or a game description | Run `scout report` on it. If a test needs it, make a made-up fixture from it (champions swapped, no dates or times; hard rule 10), never the real game. |
| "Data looks stale" / "new patch" | Run `scout refresh`, then summarize what changed and what's in the review queue. |
| A vague idea | Write a short proposal in chat first (what, where in the code, which docs change). Build after they agree. |

## Style
- Python 3.11+, type hints, dataclasses, `ruff` + `pytest`. `pathlib` for every path.
- Prefer boring, readable code over clever code. The owner will read it.
- Explanations to the owner: short, direct, plain language. Define League or API jargon the first time.
