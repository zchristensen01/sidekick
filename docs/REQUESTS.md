# REQUESTS: everything the owner has asked for, and where it stands

Every request from the owner, taken from all their messages (2026-10-02 to 2026-10-03), so nothing gets
lost and any agent can pick up where the last one stopped. `TASKS.md` has the build order and
the checkboxes; this file is the ledger behind it.

**How to use it:** before starting work, read the open items. When you finish one, change its
status, say where it was done (milestone, file, or commit), and tick the matching box in
`TASKS.md`. When the owner asks for something new, add a row here first (next free id in that area).

**Statuses:** Done · Partly done (what's left is in Notes) · Open · Waiting on the owner · Answered
(a question, no build needed) · Superseded (replaced by a later request) · Declined (the owner
said no).

## A. Setup, accounts and sharing
| id | Request | Status | Where | Notes |
|---|---|---|---|---|
| A1 | Connect to the GitHub repo; pushing finished work is OK | Done | repo, memory note | Push after each tested milestone |
| A2 | Tell them what's needed from them (keys, setup) | Answered | README "Setup" | |
| A3 | Anthropic key: spend safely, a cheap but capable model | Done | M7, DECISIONS #39 | Haiku 4.5, 40 calls/day cap, usage log, about 1 cent a game |
| A4 | Where to get a Riot key; is it per account? | Answered | README "Getting a Riot API key" | One key covers all accounts |
| A5 | The 24-hour Riot dev key is annoying | Partly done | `scout key`; Settings, Account and Riot key (M14) | Paste, test and save in the app. Left: The owner registers a Personal API Key so it stops expiring |
| A6 | Two accounts: how is that handled? | Answered | chat 2026-10-02 | The app reads whichever account is logged in. Each account now keeps its own champions (A10) |
| A7 | Send the repo to a friend, with commands | Done | README "Running it on a friend's PC" | The repo is public: cloning and updating need no collaborator access (only pushing does) |
| A8 | Fix the friend's install problems | Answered | chat | Git not on PATH, Discord eating backslashes |
| A9 | Confirm blue/red side themselves instead of waiting | Done | DECISIONS #63 | Checked against Riot's match data |
| A11 | No Riot ID to type: the account should be known from the client login, and its data used for the reports and the AI writer (2026-10-03) | Done (2026-10-03) | M22, DECISIONS #99 | Settings shows who is logged in; the region comes from the server of your own recent games. The reports and the writer already worked from the champ select; the account's champions feed the pick options |
| A10 | Each account keeps its own champions: the app knows who is logged in, switches the list by itself, and saves through account switches; how are the files kept? (2026-10-03) | Done (2026-10-03) | M22, `scout/accounts.py`, DECISIONS #95 | `pools/`: one file per account, named after its Riot ID and keyed by its puuid (a name change keeps the list), plus `accounts.yaml`; a new account starts from a copy of pool.yaml; gitignored |
| A12 | What does the friend run to get the app working, and then never use the command line? (2026-10-03) | Done (2026-10-03) | README "Install" and "Running it on a friend's PC" | Once: two `winget` lines (Python, Git), then clone and `install.ps1`. After that only the app: it updates itself, refreshes its data, and keys and champions are set in it |
| A13 | Nothing of the owner's on GitHub, past or present: no keys, account or match data, name or Windows user folder; only code anyone can use, and each person's data (all their accounts) stays on their own PC (2026-10-03) | Done (2026-10-03) | M25, DECISIONS #110-112 | One clean first commit replaced the history; the test games and the OP.GG profile are made up; the owner's match data was deleted from the PC |
| A14 | How the owner and the friend remove the old install, for a fresh install (2026-10-03) | Open | M24 | README: removing the old version |

## B. The app: window, phases, exe, settings, looks
| id | Request | Status | Where | Notes |
|---|---|---|---|---|
| B1 | See the report summarized and easy to read, in its own window (second monitor) | Done | M6b, then M13 | |
| B2 | One command opens a window that says "waiting for a game" and follows games by itself | Done | M13 (`scout watch`) | Not yet tried by the owner in a real game |
| B3 | Better visuals: charts, color theme, text sizes, one page without scrolling, role-specific, a "what to ask your jungler" section, a "when to engage" section, drop what a role doesn't need | Partly done | M13, M14 | Champion pictures added (M14). Left: The owner's feedback after real games |
| B4 | Two phases: pick options in champ select (no LLM), the written report at the loading screen with duos, summoner spells and runes | Partly done | M9c, M13 | Done: picks, the loading report with duos and spells (the draft read was dropped, B28). Left: enemy runes (E11) |
| B5 | Don't produce a wrong first report before lanes are known; no two conflicting reports | Done | B28 | One report per game, at the loading screen |
| B6 | An exe that runs the app like a real program, no command line | Done (2026-10-03) | M14: `sidekick.exe`, Desktop and Start-menu shortcuts, install.ps1 | Left: The owner opens it from the shortcut in a real game |
| B7 | It should look good | Done, open to feedback | M13, M14 | Champion pictures, logo and icon, Settings page in the same theme. Role icons skipped: the gold lane labels read fine |
| B8 | An in-app Update button: check GitHub, pull, reinstall, refresh data, restart | Done (2026-10-03) | M14: Settings, Data and updates; `scout/app/update.py` | Reinstalls only when pyproject.toml changed; refuses rather than overwrite local edits. Left: first real update |
| B9 | A settings page: each lane, the champions you play there, a comfort rating beside each | Done (2026-10-03) | M14: Settings, Your champions; pool.yaml | 1-5 stars; a more comfortable champion ranks first unless another is more than 1 point of win rate per star better (DECISIONS #65) |
| B10 | Automated where it can be: an interface, not a programmer's command-line project | Done (2026-10-03) | M14 | First start makes the settings files and downloads the data; keys, pool, AI writer, refresh and updates are all in Settings |
| B13 | Scrollbars in the app's colors (2026-10-03) | Done (2026-10-03) | M22 | |
| B14 | An × at the top right of Settings instead of Close at the bottom left (2026-10-03) | Done (2026-10-03) | M22 | The Both teams panel got the same × |
| B15 | Remove the A- and A+ buttons (2026-10-03) | Done (2026-10-03) | M22 | The text is back at its default size |
| B16 | The champion search: pictures, a bigger list, no blank area when not scrolled far enough (2026-10-03) | Done (2026-10-03) | M22 | Sidekick's own list replaced the browser's (the blank area came from the browser's list) |
| B17 | Champions on its own page from a top-bar button (where A-/A+ were), saving as you go; no "Saved your champions (pool.yaml)" message at the top (2026-10-03) | Done (2026-10-03) | M22 | |
| B18 | Suggest champions played recently that aren't in the list (after more than 3 games), with yes or no (2026-10-03) | Done (2026-10-03) | M22, DECISIONS #96 | 4+ of the client's recent games in the same lane; a No is remembered per account and lane. Left: the owner checks it with their live client |
| B19 | "Suggest from my most-played": only champions not added yet, and the lane to add each to (2026-10-03) | Done (2026-10-03) | M22 | The lane is where the champion is played most (OP.GG) |
| B21 | A note on the Champions page to keep the comfort ratings accurate, since they help Sidekick (2026-10-03) | Done (2026-10-03) | M22 | Above the lists |
| B22 | The waiting message without a semicolon, and shorter (2026-10-03) | Done (2026-10-03) | M22 | "Open the League client to start." |
| B20 | Does Refresh data update everything, or will some things need research prompts? (2026-10-03) | Answered | chat 2026-10-03, PATCH_UPDATE.md "In short" | Refresh covers every automatic source, and match data collects by itself; patch notes and game facts need a prompt each patch (the top bar shows "Research due"), class definitions once; drafted notes a kit change flags need a review |
| B11 | The top of the app says when research is due after a new patch (2026-10-03) | Done | M21 | A "Research due" button in the top bar; `research/status.csv` records what was done per patch |
| B12 | An update button that pulls from GitHub when an update is available, mostly for a friend (2026-10-03) | Done | M14, M21 | The app checks GitHub at start and every 6 hours; an "Update available" button in the top bar leads to Update and restart |
| B23 | "Research due" must know when the research was done and go away (2026-10-03) | Done (2026-10-03) | M21, `research/status.csv` | It goes away as soon as results are applied (in the app or `scout import-research`), and on a friend's PC once the update with the owner's results arrives. Research reminders are on the owner's PC only (`owner: true`, B29) |
| B24 | Is everything else updated automatically, and how often? (2026-10-03) | Done (2026-10-03) | M21, PATCH_UPDATE.md "What updates by itself" | It wasn't: the data refresh needed the button or a scheduled task. Now the app refreshes every 6 hours while idle; updates are checked every 6 hours; match data is measured continuously while idle |
| B25 | A History button: see past games' reports and interact with their dashboard; saved for each person, never sent to GitHub, the owner's own included (2026-10-03) | Done (2026-10-03) | M23, `scout/report/past.py` | Each final screen is saved next to its report in `reports/` (gitignored), with the account and the post-game results; Back to now; a new champ select takes over |
| B28 | Never show the free draft read: straight from champ select to the LLM report the moment the loading screen shows summoner spells, roles and duos (2026-10-03) | Done (2026-10-03) | One report per game (TASKS) | "Picks locked" then "Writing your report"; the writer waits up to 15 s for the players' records and the duo check and writes them in. Rules version only with the AI writer off, or labelled when it fails |
| B29 | Only the owner downloads games; others shouldn't even have the option (2026-10-03) | Done (2026-10-03) | docs/MATCH_DATA.md | `owner: true` in config.yaml on the owner's PC only: match data, the backtest and research reminders there, hidden elsewhere. What the games teach ships in the code |
| B26 | A real installer: download one file, double-click, no commands; a proper program layout; safe; updates from the app (2026-10-03) | Open | M24 | Unsigned on purpose (no monthly signing fee): Windows asks once (More info, Run anyway) |
| B27 | The README for beginners: download, install, set up your champions, add the keys (2026-10-03) | Open | M24 | |

## C. What the report says
| id | Request | Status | Where | Notes |
|---|---|---|---|---|
| C1 | Works for every position, with relevant information for each | Done | ROLES.md, M5 to M9c | |
| C2 | Synergies with other lanes, duos, which lanes are strong or weak, where the jungler should path (e.g. a volatile bot lane that loses on paper) | Done | depth pass, M11 | |
| C3 | Know which enemy is the jungler, and whether they picked before you | Done | M4/M8 role odds, M9 pick order, M6 Smite at loading | |
| C4 | Base the report on the real jungler confirmed at loading (who has Smite) | Done | M6 | |
| C5 | Attack range, ranged vs melee, passives, and what they mean in a matchup | Done | range rules, Know your opponent, M15, M17 | |
| C6 | Never run for ARAM; only draft and ranked | Done | M4 | |
| C7 | Fix the Sivir/Seraphine game (shoved under tower all lane, report said we win) | Done | wave control, Priority x Fight lanes | Game saved as a test fixture |
| C8 | Only information relevant to my role (a support isn't told about the top's carry; the jungler hears about a top that can 1v2) | Done | M9c | |
| C9 | Explain what the enemy laner does (Sivir's passive); both enemies in bot lane | Done | "Know your opponent" (Riot's passive and tips) | Plain-word whole kits are C11 |
| C10 | Jungle: a summary of what every enemy does and who is most gankable (pushing, CC, mobility, against their matchup) | Done | gank ranking (Riot's mobility and control), Both teams panel | |
| C11 | Every enemy champion in simple words, no numbers (e.g. "Galio can taunt you in, dash into you to stun, and his ult drops him into a fight anywhere nearby"), in a team panel opened from the dashboard; lane opponents' kits on the main view | Done (2026-10-03) | M17: Both teams panel, Know your opponent | Riot's own short descriptions (we don't reword them) |
| C12 | Jungle invade decisions: invade or not by matchup, invade to ward, take a slow clearer's camps | Open | M15 (data), then rules | Needs clear-speed data: nothing reputable exists (research); measure from Riot match data (E9) |
| C13 | The LLM as a League pro: all the details, walk through the matchup, the smartest options, what the enemy will likely do | Partly done | M15, M16, M17 | It now gets every kit, Riot's tips, sourced ratings and mechanics, matchup numbers, game facts and player records, with a structured prompt; it may only use given facts. Left: The owner's read of real written reports |
| C14 | Lane swaps covered? | Answered | chat 2026-10-02 | Ally swaps yes; enemy roles confirmed at loading for the jungler, the rest re-guessed; nothing in game |
| C15 | Player stats: each player's win rate and average KDA on their champion, in a player section and in the LLM's input | Done (2026-10-03) | M16, `scout/player_cards.py` | At the loading screen; rank, games, win rate (5+ games), average K/D/A, recent results; hidden players skipped; no names shown or sent. The outside review says Riot's policy forbids showing other players' rank or win rate: a Settings switch turns it off (on by default, the owner's call). Left: a real game |

## D. Pick suggestions
| id | Request | Status | Where | Notes |
|---|---|---|---|---|
| D1 | Should we ask for a champ pool per role? It should know your position (autofill) | Done | M9b | Role from champ select; pool optional; mastery and easy-meta fallbacks |
| D2 | Suggest which of your champions is best against the enemy picks | Done | M9b | |
| D3 | The user sets roles and comfortable champions, but it still works for autofill and new picks | Done | M9b | Settings page is B9 |
| D4 | Where do I enter my pool? | Done | Settings, Your champions (pool.yaml); `scout pool` still works | |
| D5 | Know live, as the enemy picks, who's good against them (e.g. Rammus into AD) | Partly done | M9b matchup numbers; Riot's tips | Left: team-level fit (D6) |
| D6 | Picks based on the whole team so far: team lacking CC/AP/AD, ADC with the locked support, a knock-up jungler for a Yasuo mid, champions bad into a comp (Rammus into AP) | Mostly done (2026-10-03) | M18 | Synergy with every locked ally (OP.GG, DraftGap-style), damage mix, crowd control and frontline (Riot), knock-ups for a Yasuo (wiki + Riot). Left: "bad into their comp" needs cross-role matchup data (no source yet) |
| D8 | Do the bot / support pick options change as teammates pick? (2026-10-03) | Answered | chat 2026-10-03 | Yes once a teammate locks (OP.GG's duo numbers with each locked ally, plus the team's damage mix, crowd control and frontline: M18). Not while they only hover; using hovers (the client shows your own team's) is offered, not built |
| D7 | Use an LLM at the pick stage? | Answered | chat 2026-10-02 | Not needed: numbers and facts are faster and free; the LLM writes at loading |

## E. Data and sources
| id | Request | Status | Where | Notes |
|---|---|---|---|---|
| E1 | Up-to-date matchup and champion data; when champions spike; who's strong early | Partly done | M8, M15 | Scaling is OP.GG's game-length data now. Spikes and early kill pressure stay drafted until `research/power_spikes.md` and `research/early_game.md` are run |
| E2 | No conclusions of our own: only reputable sources; ask the owner for research when needed | Done (rule) | CLAUDE.md, DECISIONS #61 | Applies to all new work |
| E3 | Replace drafted data with sourced data everywhere possible, easy to refresh patch after patch | Done where a source exists (2026-10-03) | M15, `scout/data/sourced.py`, DECISIONS #70-74 | Crowd control, mobility, toughness: Riot. Knock-ups, stealth: the wiki. Needs-airborne: Riot's text. Scaling: OP.GG. Each value records its source; the rest wait on research prompts |
| E4 | A list of what an agent must re-fetch after each patch | Done | docs/PATCH_UPDATE.md | A checklist per patch |
| E5 | A doc of every data file and what in it needs updating or re-prompting per patch | Done | docs/PATCH_UPDATE.md | Same file as E4 |
| E6 | A folder of research prompts the owner can give other agents, with results dropped back in | Done (rewritten 2026-10-03) | `research/` (3 prompts since M19: patch notes, game facts, class definitions; written by `scout research`), `research/results/` | Each prompt carries its data (numbered champion list with roles, junglers, today's game facts), batches of 20, shared rules (sources, no ratings of the agent's own) and an exact reply format; Claude Code merges results with the owner's OK |
| E7 | Riot-cited game facts (objective and camp timers, role quests) | Done | `data/manual/game_facts.csv` | Riot's patch notes and the wiki, cited per line; in the jungler's Start and objectives and the writer's input |
| E8 | Use Riot's passive text and "how to play against" tips in the LLM's input | Done | `tips.csv`, builder | Opponents' whole kit and Riot's tips go to the writer |
| E9 | Jungle clear speed and level-3 gank strength | Partly done | M19: measured level 3 and 4 times per jungler | Left: invade rules that use them (C12), once there are enough games |
| E10 | Champion data for wave clear / early push and engage (no source found) | Partly done | M19 | Lane push measured (minutes 3-10 on the enemy half). Engage stays a drafted note (Riot's class definitions help explain it) |
| E11 | Enemy runes at the loading screen | Open | M19 | No agent needed: Riot's Spectator-V5 active-game data lists runes once the game is loading; to check in a real game |
| E12 | What happens to research results: where they go, how they reach the app and the LLM, how blanks are handled (2026-10-03) | Done (2026-10-03) | M19: `scout import-research`, Settings, Research results | Read by the table inside, checked, shown, applied on OK |
| E13 | Measure the numbers ourselves from Riot's match data instead of asking agents (2026-10-03, agreed) | Done (2026-10-03) | M19: `scout collect`, the app in the background | Figures per champion and role; coverage and an OP.GG cross-check. Left: let it collect |
| E14 | Data only for champion-role pairs actually played, in every role (no Jinx top wave clear); the jungle list from real junglers | Done (2026-10-03) | M19: `scout/analysis/role_pool.py` | 10%+ of the champion's games, every role |
| E19 | Know when a champion's numbers change after a patch (clear times etc.) and when research is due (2026-10-03) | Done | M19, M21 | "Research due" button; measured figures that moved beyond normal variation are flagged (Settings, `scout collect --status`, Both teams panel, the writer) |
| E18 | Live in-game numbers (your lane's gold and item lead, levels, CS) as the game goes, as a feature that can be turned off (2026-10-03) | Parked | | Possible: the game's own local data feed (Live Client Data API) has everyone's level, items, K/D/A and CS (exact gold only for you). Conflicts with hard rule 2 (pre-game only); the owner's call when to build it |
| E16 | Make the judgments really strong (2026-10-03) | In progress | M20 | Backtest every read on thousands of collected games, fit weights and cut-offs to outcomes, retire rules that don't beat a coin flip, show each read's track record. Built: per-game records and `scout backtest`; waiting on enough collected games |
| E17 | Research prompts only for what's actually needed; data accurate and complete; the LLM gets all the data (2026-10-03) | Partly done | M19, M20 | Figures with games and patch, patch-filtered, counted once, coverage and OP.GG cross-check: done. Reads with their tested accuracy: M20 |
| E15 | When there's no data (an off-meta pick, a blank), say so honestly, and let the AI reason how to play it, labelled as the AI's read (2026-10-03) | Done (2026-10-03) | M19 | The report says "No data"; the writer's own read starts "No data; AI read:" and is tagged on the page |
| E20 | Connect the research results; know when to refresh them and when sources publish something new (a new clear-times page); list every resource in the docs (2026-10-03) | Done (2026-10-03) | M21, PATCH_UPDATE.md, research/README.md, DATA.md | Results for 26.19 applied. Patch notes and game facts are due every patch (the app says so); clear times are measured from Riot's games each patch, so no outside page is needed. Hotfix detection was built (E22); sharing measured totals was declined (E23) |
| E21 | Research set up to be refreshed: prompts made automatically for what's needed, nothing patch-specific to fill in, sent to a new agent as they are (2026-10-03) | Done (2026-10-03) | M21, `scout/research.py` `regenerate` | The patch is filled in; rewritten after each refresh and each applied reply on the research PC; after a hotfix the patch notes prompt asks only about it |
| E22 | Detect mid-patch hotfixes automatically (2026-10-03: "a good idea") | Done (2026-10-03) | M21, `scout/data/patch_updates.py` | The LoL Wiki's patch page, each refresh; a new update makes the patch notes research due again |
| E23 | Share the measured match data with friends through git (proposal, 2026-10-03) | Declined | | the owner: match data stays private and out of git; another agent handles privacy |
| E24 | Can't we backfill the backtest with games from online? What are we backtesting that we can't get online? (2026-10-03) | Answered | chat 2026-10-03 | The games do come from online (Riot's match API); the backtest grades Sidekick's own calls, which nothing online has. The limit is the Riot key's rate (100 calls per 2 minutes, about 2.4 calls a game): about 1,000 games an hour at most, so a few thousand takes a few hours of collecting |
| E25 | Are the stored games good data, do they stop, how much space, are we getting everything useful from them? (2026-10-03) | Done (2026-10-03) | docs/MATCH_DATA.md | Checked: zero-sum figures balance, values are plausible. Now: 4,000 games per patch then pause, older patches dropped (about 15 MB at most), more figures per game and per matchup, the ladder tier kept |
| E26 | A post-game review of how the player did against the plan, per account (2026-10-03) | Open (future project) | docs/future/postgame-review/ | Not built on purpose; each game's data is kept now (`reports/<report>.review.json`) and the plan for the LLM's input is written down |

## F. The LLM writer
| id | Request | Status | Where | Notes |
|---|---|---|---|---|
| F1 | Cheap, capable model; protect their funds | Done | M7 | |
| F2 | As much context as possible, with clear structured prompts, so it's accurate | Done (2026-10-03) | M17, REPORT_AGENT.md | About 7,400 input tokens, about 1.3 cents a written report |
| F3 | A review document for an outside AI, plus a prompt | Done | docs/REVIEW_BRIEF.md | |

## G. The outside review (2026-10-02), item by item
| id | Item | Status | Where | Notes |
|---|---|---|---|---|
| G1 | Lane = Priority x Fight, with labels | Done | M9c | |
| G2 | Engage counts only if it can connect (access) | Done | M9c | |
| G3 | Bot lane as one 2v2 unit | Done | M9c | Push unit done; duo synergy from OP.GG |
| G4 | Volatility = how likely someone dies | Done | M9c | |
| G5 | No "cover levels 1-3" asks | Done | M9c | |
| G6 | Label the game win rate apart from the lane read | Done | M9c | |
| G7 | "Best gank options"; reword "little threat" | Done | M9c | |
| G8 | Summoner spells (Ignite/Exhaust kill lanes, Teleport, Cleanse, Heal/Barrier) | Partly done | M9c | Left: Cleanse vs point-and-click CC, Heal/Barrier rules (need sourced CC data, M15) |
| G9 | Map side | Done | M9c | Side-specific map facts wait for E7 |
| G10 | 2026 objectives and role quests | Done | E7 | |
| G11 | `early_push` trait | Done (measured) | M19 | |
| G12 | Jungle `clear` and `l3_gank` | Partly done | M19 | Clear speed measured; level-3 gank strength not yet |
| G13 | `sustain` 0-3; kit tags (stacking, execute, reset, % health) | Partly done | M15 | The wiki's mechanics (self heal, healer, execution, ...) reach the writer and the panel; no rules use them yet |
| G14 | Section order: a one-line plan first, counter-pick last, merge watch out and don't feed | Partly done | M13 dashboard | The dashboard opens with the plan; the text report keeps the old order |
| G15 | Post-game grading per prediction, then fit the weights | Partly done (2026-10-03) | M10, `scout/postgame/` | Grading by the review's table, history and accuracy files, automatic after each game. Left: fit the weights after 100-200 games |
| G16 | Register the product with Riot | Waiting on the owner | A5 | The Personal API Key application counts |
| G17 | No dodge-pushing wording | Done | M9 | Verdicts are worded as options |
| G18 | Query OP.GG at the player's own tier | Superseded | STATS.md | OP.GG's tools have no tier parameter |

## H. Process
| id | Request | Status | Where | Notes |
|---|---|---|---|---|
| H1 | Keep the tasks file current | Done (ongoing) | TASKS.md, this file | |
| H2 | Track every request so another agent can continue (this file) | Done | docs/REQUESTS.md | |
| H3 | Do research to build it properly | Done (ongoing) | research report 2026-10-02 | Findings in DATA.md and DECISIONS.md as they're used |
| H4 | Build as much as possible; finish phases completely, then the next ones | Done (ongoing) | TASKS.md | |
| H5 | Everything relevant in the docs; tasks, docs and README accurate and up to date (2026-10-03) | Done (2026-10-03) | TASKS.md, PATCH_UPDATE.md, DATA.md, README.md, research/README.md | Full pass on 2026-10-03 |
| H6 | Confirm every task and request is complete, connected and used; then the owner runs a verification prompt (2026-10-03) | Done (2026-10-03) | TASKS.md, this file | Unused code removed, docs checked against the code, the excluded-rules test uses `conflicts()` |

## Waiting on the owner (things only they can do)
- Close and reopen Sidekick once (2026-10-03): the open window still runs the code from when it
  started; the new version has History, the 6-hour data refresh, the hotfix check and the
  audit's fixes.
- Register a Riot Personal API Key (A5, G16); until then paste a fresh development key in
  Settings when it shows "rejected".
- Play real games with the Sidekick app (Desktop shortcut) and say what to change (B3): the
  report at the loading screen (how long "Writing your report" takes), the players strip, the
  post-game line, History.
- Rate your champions 1-5 on the Champions page (top bar); each account has its own list. With
  the League client open, check its suggestions from your recent games (B18).
- Decide on players' records at the loading screen: the outside review says Riot's policy
  forbids showing other players' rank or win rate; Settings, Account has the switch (C15).
- Research rounds: done for 26.19 (2026-10-03). At each new patch "Research due" appears: run
  `research/patch_notes.md` and `research/game_facts.md`, paste the replies into
  `research/results/`, apply them in Settings (`PATCH_UPDATE.md`, "How a research round
  works"). Then review the champions the patch notes queued (`scout review`): 17 for 26.19.
- Review the 15 drafted jungle matchup briefs (`data/manual/matchup_briefs.csv`) and the
  drafted champion notes (`scout review`).
- Mastery suggestions now work (69 champions read on 2026-10-03; your pool already had them).
