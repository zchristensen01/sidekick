# TASKS (work top to bottom; tick boxes as you go)

Each milestone ends with something the owner can run. Don't start the next one until the current
one's "Done when" passes. When a task is done: tick it, and add a line to `CHANGELOG.md`.

Order logic: record real champ selects first (so every game played becomes a fixture), get a
live report working for every role on rules alone (**test version at M6**), then add the LLM
writer, stats, and the rest. Sizes are rough focused-work estimates with Claude Code.

## Where things stand (2026-10-03)
- **Every request the owner has made, with status:** `docs/REQUESTS.md`. Read it first.
- **Usable now:** the Sidekick app (Desktop shortcut; `scout watch` opens the same app with a
  terminal): pick options while you draft, then one report at the loading screen, written by
  Claude Haiku with the roles, spells, players and likely duos in it, the Both teams panel,
  players at loading, the post-game check, the Champions page (one list per account), all five
  roles. It keeps itself current: GitHub updates (checked every 6 hours), a data refresh every
  6 hours while idle, and Riot's match data measured in the background (Riot key added
  2026-10-03; 241 games stored by 10:20 that day).
- **Research:** the patch notes, game facts and class definitions prompts were run and applied
  for patch 26.19 (2026-10-03). The next round is due at patch 26.20 ("Research due" shows for
  the owner). The process and every source: `PATCH_UPDATE.md`.
- **In progress:** M20, backtesting every call. The pieces are built (records, `scout
  backtest`, track records to the writer); it needs a few thousand stored games before fitting
  weights and retiring rules means anything.
- **Waiting on the owner:** real games with the app (feedback, post-game history), the Personal API
  Key (the development key expires every 24 hours), rating champions, reviewing drafted notes
  and briefs. The list: `REQUESTS.md`, "Waiting on the owner".
- **Known gaps:** matchup briefs exist only for the jungle pool (15 drafts to review); engage,
  spikes and style are drafted notes until reviewed; measured figures need 50+ games per
  champion and role; enemy runes at loading (Spectator-V5) not built; off-meta drafts (two
  off-role picks) fool the role guess until the loading screen fixes it.

## M0. Docs and scaffold (done 2026-10-02)
- [x] Planning docs rewritten for all five roles; new `ROLES.md`, `LCU.md`, `STATS.md`,
      `TRAITS.md`, `KNOWLEDGE.md`, `POLICY.md`, `DECISIONS.md`
- [x] `pyproject.toml`, `ruff`, `pytest`, package skeleton per `ARCHITECTURE.md`
- [x] `config.py` loader with validation; `.env` loading; `paths.py`
- [x] Core types: `model/roles.py`, `model/game.py`; `data/patch.py`; `data/schemas.py`
- [x] CLI skeleton (`scout --help` lists every command; `scout doctor` checks the setup)
- [x] Rules copied to `scout/rules/league_rules.yaml` (format upgrade happens in M5)
- [x] Recorded source samples in `tests/fixtures/sources/`
- [x] Verified on Windows Python and WSL: `pytest`, `ruff check`, `scout --help`

**Done when:** `pytest` passes and `scout --help` lists the commands, on Windows.

## M1. Client connection and recorder (S: about 1 day + games)
- [x] `lcu/connection.py`: find the client via `psutil` process args, lockfile fallback, pinned
      `riotgames.pem`, reconnect on failure
- [x] `lcu/client.py`: `get()` only; test that no write methods exist
- [x] `lcu/recorder.py` + `scout record`: poll gameflow, save deduplicated session snapshots,
      scrub per `LCU.md` section 7; test that fixtures contain no scrubbed fields
- [x] `scout doctor` reports whether the client is reachable
- [x] Recorder also saves the game-start roster (champions, positions, spells; no identities)
      as the answer key for enemy role guesses (`ROLES.md`)
- [x] Live check on the real client: certificate, `scout doctor`, endpoints (2026-10-02, in
      lobby; clears the [verify] marks in `LCU.md` sections 1-2)

**Done when:** 3 real champ selects (any draft queue) are recorded, scrubbed, and committed.
From here on, run `scout watch` (it records too) every game.

## M2. Static data (done 2026-10-02)
- [x] `data/ddragon.py`: versions, champion list (id, key, name), abilities (`championFull.json`),
      `summoner.json` spell ids, `item.json` names; raw responses cached per version
- [x] `data/cdragon.py`: range type, damage type, Riot playstyle ratings, tactical info
- [x] `data/wiki.py`: Riot class (`role`), positions, last-changed patch, range (cross-check)
- [x] Build `static/<version>/champions.csv`, `abilities.csv`, `champion_meta.csv`,
      `summoner_spells.csv`, `items.csv`; write `PATCH` and `manifest.json`
- [x] Diff against the previous version -> `review_queue.csv`; apply `champion_overrides.csv`
- [x] `scout refresh --static` + `data/generated/REFRESH_LOG.md`
- [x] Parsers tested against `tests/fixtures/sources/`

`opgg_name` in `champion_meta.csv` stays empty until M8 (OP.GG client).

**Done when:** a clean `scout refresh --static` produces every file for every champion, every
LCU `key` maps to one champion, cross-source disagreements (e.g. range) are logged, and a second
run with no new version does nothing.

## M3. Champion knowledge for every champion (done 2026-10-02; review is ongoing)
- [x] `store.py` validation per `TRAITS.md` (scales, tags, spikes, text fields, primary key)
- [x] Convert the 23 prototype rows (`source=prototype`, `reviewed=n` until new columns are filled)
- [x] Draft scores and briefs (`key_note`, `ult_note`, `spike_note`) for every champion from
      Riot's ability text: first pass by Claude Code in a session (no API cost), same validation
- [x] `scout draft-traits <champ>` and `--all-missing` for new champions later (structured output,
      appended `reviewed=n`)
- [x] `scout review`: walk the queue (recent games, then pool, then rest), accept/edit/skip

**Done when:** every champion has a valid traits row with briefs (drafted or reviewed).

## M4. Game model and enemy roles (built 2026-10-02; answer-key check waits on a new recording)
- [x] `lcu/champselect.py`: session JSON -> `GameState` per `LCU.md` section 4 (queue gate,
      pick turns, trades, role swaps, ally Smite check, unknown champion keys)
- [x] Game fixture YAML loader (`tests/fixtures/games/`), used by `scout report --file`
- [x] `analysis/role_inference.py` per `ROLES.md` (Enemy roles and pick order): all 120
      assignments, product of role rates with a floor, confidence and alternatives, per-role
      probabilities ("their jungler"), partial teams; role rates from wiki positions until M8
- [x] Pick turns for every locked champion, incl. trades and pick-order swaps (`ROLES.md`,
      `LCU.md` section 3 "Seen in the first real recording"); check on recordings
- [x] Test: role guesses vs the `game_start` answer key in every recording (skips recordings
      made before the answer key existed; the first one with it will exercise it)

**Done when:** every recorded champ select parses to a `GameState`, and enemy roles match the
`game_start` answer key in all of them (or are flagged as low confidence).

## M5. Analysis and rules for every role (done 2026-10-02)
- [x] `analysis/`: lane state, lane timeline, gankability, jungle threat, jungle plan,
      priority, roam, cross-map threats, team profile (incl. damage split and comp type),
      threats / feed ranking (`ROLES.md`, `KNOWLEDGE.md`)
- [x] `rules/engine.py` + `rules/context.py`: scopes, paths, ops, null handling, load-time
      validation (`RULES.md`)
- [x] Convert `league_rules.yaml` to the new format (section, audience, priority, tests,
      excludes); add the role packs from `ROLES.md`
- [x] `report/select.py`: per-role sections, priorities, word budget
- [x] Deterministic renderer (this is also the LLM fallback)
- [x] Tests: per-rule fire/not, 2+ golden games per role, contradictions
- [x] `scout report --file <game.yaml> --role <role>`

- [x] Attack range and move speed in the static data; range gap per lane and range rules for
      mid and bot, form-changers flagged (added after M6, the owner's request)
- [x] Depth pass (the owner's review): "at a glance" view of all three lanes for every role,
      a suggested jungle route (start side, first gank, where their jungler goes), early
      2v2/3v3 fights per lane with both junglers (river, dragon side, top side), top's job
      later and the support's fight job when no rule covers them, bot's dive threat

Counter-pick items wait for M9. Insight formulas are the starting ones from `ROLES.md`; tune them
with post-game data (M10).

**Done when:** `scout report --file tests/fixtures/games/samira_naut.yaml --role <r>` gives a
sensible report for all five roles, and all rule and golden tests pass.

## M6. Live watch: TEST VERSION (S-M: about 1 day + games)
- [x] `lcu/events.py`: WebSocket subscription with polling fallback
- [x] `lcu/watcher.py`: state machine (`LCU.md` section 6): report at finalization, re-render on
      trades, discard on dodge, stop in game, record every session
- [x] Report printed in the terminal and saved to `reports/`
- [x] Loading-screen role confirmation (`ROLES.md`): when the game-start roster shows who has
      Smite (and positions, if the client fills them in), confirm or correct the enemy roles
      and re-render the report once, marked "confirmed". Then stop.

**Done when:** 5 real champ selects produce a report in under 10 s with no crash, for at least
2 different roles. **This is the test version.** (Built 2026-10-02; waiting on real games.)

## M6b. Report window (built 2026-10-02)
- [x] A small window of its own (drag it to a second monitor) that shows the report: opens or
      refreshes when the report is ready, updates on trades and at loading-screen
      confirmation, shows the pick suggestions while drafting once M9b exists. Static during
      the game: no timers, no live prompts (`POLICY.md`). Terminal output stays available.

**Done when:** a live champ select shows the report in the window, on either monitor.

## M7. LLM writer (built 2026-10-02; the owner to read real reports)
- [x] Cost safety (the owner's request): Claude Haiku 4.5 by default; a daily call cap
      (`llm.max_calls_per_day`, default 40) after which the free rules report is used; capped
      output tokens; no new call when the draft is unchanged; every call logged with tokens
      and estimated cost to `reports/debug/llm_usage.csv`; `scout doctor` shows today's use
- [x] `report/builder.py` -> input JSON per `REPORT_AGENT.md` (pre-formatted numbers, the
      ability text (passives included) of the abilities the items mention, attack ranges)
- [x] `report/writer.py`: Anthropic (structured output) and Ollama providers
- [x] `report/validator.py` + one retry + deterministic fallback; debug log of failures
- [x] `render.py`: clean view, `--debug` view with sources

Checked with real calls (2026-10-02): one game x five roles all pass the validator after
the prompt got line limits (13 calls, about $0.11 in total, during development).

**Done when:** 5 fixture games per role pass the validator, and the owner reads them.

## M8. Stats from OP.GG (done 2026-10-02)
- [x] `data/opgg.py`: MCP client (Streamable HTTP), `list_tools` check that fails loudly,
      throttle, per-patch cache, timeouts
- [x] Parsers built against `tests/fixtures/sources/opgg/` (output is compact text, not JSON)
- [x] `stats.sqlite` store per `DATA.md` (champion stats, role rates, matchups, guides,
      synergies, game-length rates, fetch log)
- [x] Role inference switches to real role rates
- [x] `analysis/stats.py`: expected result, shrinkage, previous-patch blending, display strings
      (`STATS.md`)
- [x] Draft-time prefetch in `scout watch` + on-demand fetch with a time budget
- [x] `matchup_builds` + expected items for my lane, names from `items.csv`
- [x] `stats.*` paths in rule contexts; `stats_disagree` review rows
- [x] `scout refresh` nightly mode; Windows Task Scheduler instructions in `README.md`

Checked live (2026-10-02): `scout refresh --stats` (269 champion-roles for patch 16.19, about
8 s) and `scout report --fetch` on a saved game (Lee Sin vs Elise: 48% over 3,572 games, Elise's
usual build into Lee Sin). Network down: tested with a fake OP.GG that can't be reached.

**Done when:** a report shows real matchup numbers with sample sizes, and with the network
unplugged it still produces a rules-only report with a one-line notice.

## M9. Counter-pick and matchup briefs (built 2026-10-02; acceptance check waits on the owner)
- [x] `counterpick.py` per `COUNTERPICK.md`
- [x] `counterpick` scope and rules
- [x] Fixtures for each band, specific vs weak-patch, pick order, role uncertainty
- [x] `matchup_briefs.csv` per `KNOWLEDGE.md`: drafting (pool x common opponents first, right
      after M8, in a Claude Code session), inputs incl. both kits' ability text, traits, attack
      ranges and OP.GG matchup data; a validator that rejects drafts contradicting the data,
      `brief_stale` review rows, use in reports
- [ ] the owner reviews the 15 drafted briefs (jungle: Lee Sin, Elise, Amumu vs each one's 5
      most-played opponents); more opponents and other roles' pools later

**Done when:** all counter-pick fixtures pass, and 20 hand-labelled real champ selects agree
with the owner in at least 16.

## M9b. Pick suggestions (done 2026-10-02)
- [x] `scout pool`: suggest your most-played champions per role from your own champion mastery
      (one more read-only LCU endpoint, added to `LCU.md`), confirm or edit, save to config
- [x] `scout/picks.py` per `COUNTERPICK.md` (Pick suggestions): rank the pool for my assigned
      role against locked enemies (or blind safety), comfort as tiebreaker, 2-3 options with
      reasons; autofill fallbacks
- [x] Shown while drafting by `scout watch` (terminal and window); updates as enemies lock
- [x] Tests: opponent locked, blind pick, empty pool (autofill), off-pool lock

Checked: `scout pool --show` live; the replayed recording shows options updating from blind to
"into <their jungler>" as the draft goes. Open: the client's mastery list had only one champion during
your games (probably refreshed at login), so check `scout pool` after a fresh login; the new
`anti_auto` tag (strong into auto-attackers) is in the vocabulary but on no champion yet, waiting
for the owner's OK on a list.

**Done when:** in recorded champ selects replayed offline, the suggestions update as enemies
lock and always give 2-3 options with reasons, including for a role with no pool.

## M9c. Report fixes from the outside review (2026-10-02; docs/REVIEW_BRIEF.md)
- [x] Only what's relevant to my role: every rule and insight checked for who needs it (a
      support isn't told their top must not get fed; the jungler hears about a top that can 1v2)
- [x] Lane read = Priority (who pushes early) x Fight (who wins trades and all-ins): bully,
      shove and respect, bait lane, survive; engage counts fully only if it can reach someone
- [x] Bot lane scored as one 2v2 unit; volatility = how likely someone dies (both sides'
      all-in, low escape, kill summoners), not the stronger side's power
- [x] Rule fixes: no "cover levels 1-3" (help comes after first clears); the counter-pick number
      is labelled as a game win rate, apart from the lane read; "Best gank options"; Lillia-style
      "little threat" reworded
- [x] Summoner spells: ours from champ select, theirs at loading (Ignite/Exhaust kill lanes,
      Teleport top, Smite); they also reach the writer (`summoner_spells` in `facts`)
- [ ] Cleanse vs point-and-click CC and Heal/Barrier rules: not built (REQUESTS G8; they need
      sourced crowd-control data per ability)
- [x] Map side (blue/red) from champ select, shown in the header (the owner to confirm red = team 2;
      side-specific map facts wait for the researched constants below)
- [x] Riot's own words: each lane opponent's passive and Riot's tips against them (Data Dragon
      `enemytips`), the whole kit to the writer
- [x] Two phases: champ select = pick options; the loading screen = the one report, written by
      the LLM (the free draft read at champ select was dropped 2026-10-03: "One report per game" below)
- [x] Game constants per patch (objective spawn times, role quests) in a file researched from
      Riot's patch notes, with sources (`data/manual/game_facts.csv`; re-checked by the owner's
      research round for 26.19 on 2026-10-03)

## M13. The Sidekick app (dashboard window; first version 2026-10-02)
- [x] One command opens the window, which shows the state: waiting for the client, waiting for
      a game, pick options while drafting, the report, loading-screen notes, game in progress,
      game ended; it follows the client by itself (no terminal needed)
- [x] A one-page, role-specific dashboard: a one-line plan; my lane (Priority x Fight card and a
      who's-favored-by-phase chart = when to trade or engage); what to ask my jungler (laners) or
      my lanes at a glance (jungler); threats that reach me; counter-pick and items; a color theme,
      clear type sizes, no scrolling for the main view
- [x] The written version fills the same layout; the plain-text report stays for the terminal
      and saved files
- [ ] the owner tries it in real games (`scout demo` first) and says what to change

## M15. Sourced data everywhere (2026-10-03: no conclusions of our own)
Everything the report says about a champion or the game comes from a named source, refreshed
each patch, with the source recorded per field. Drafted notes stay only where no source exists,
and each of those has a research prompt in `research/`.
- [x] Blue/red side confirmed from Riot's match data (team 2 = teamId 200 = red), documented
- [x] Riot's own ratings (CommunityDragon `playstyleInfo`) replace drafted `cc`, `escape`,
      `frontline`; the LoL Wiki's champion categories (crowd-control types incl. knock-ups,
      dashes, blinks, shields, heals, executes, stealth) give the tags and facts; Riot's ability
      text gives "needs airborne targets"; credited to the wiki (CC BY-SA)
      (`scout/data/sourced.py`, `champion_meta.csv` `mechanics`, DECISIONS #70-72)
- [x] OP.GG win rates by game length for all ten champions (fetched during the draft) decide who
      scales when there's data; drafted `scaling` only as a fallback (DECISIONS #73)
- [x] Every champion field records its source; the report and the writer know which facts are
      Riot's, the wiki's, OP.GG's, or still a drafted note (`Traits.sources`, the writer's
      `riot_ratings`, `wiki_mechanics`, `game_length_data`, `notes_are`)
- [x] Game facts file from Riot's patch notes (objective and camp spawn times, role quests),
      cited per line, used as static pre-game text (never timers): `data/manual/game_facts.csv`
- [x] `docs/PATCH_UPDATE.md`: every data file, its source, how it's refreshed (a command, or a
      prompt in `research/` for an agent), and what to check after a new patch
- [x] `research/`: ready-to-run prompts for the facts with no automatic source (jungle clear
      speed, wave clear, engage, early game, roaming, power spikes, enemy runes, patch notes,
      game facts), each with the exact output format to drop back in
- [x] Run the research prompts and merge the results: done 2026-10-03 for the three prompts
      left after M19 (patch notes, game facts, class definitions); the number prompts were
      replaced by the collector

## M16. Players at the loading screen (2026-10-03; built 2026-10-03)
- [x] The loading roster's player IDs turned into Riot IDs through the client (read-only), so
      the duo check and player stats work (the client's IDs aren't the web API's); hidden
      players skipped
- [x] Each visible player's ranked record on the champion they're playing (games, win rate,
      average kills/deaths/assists) and their recent form, from OP.GG's profile tool; no names
      shown or sent to the LLM, only "their Sivir player" (`scout/player_cards.py`; a win rate
      only with 5+ games)
- [x] A players section on the dashboard (a strip under the report, one row per team) and in
      the writer's input (the final write waits up to 15 s for the records)
- [ ] the owner: check the records in a real game (the OP.GG region comes from Settings, Account)

## M17. The whole team, in plain words (2026-10-03; built 2026-10-03)
- [x] Every champion's kit in Riot's own short descriptions (no numbers): lane opponents on the
      main view (both enemies in bot lane; Riot's first sentence per ability), all ten in a
      "Both teams" panel opened from the report header (full text, Riot's ratings in Riot's
      words, the wiki's mechanics, Riot's tips)
- [x] The writer gets every champion's kit, Riot's tips, the matchup data and the game facts,
      with a restructured prompt: what each field means, where it came from, what to do with it
      (REPORT_AGENT.md "What you receive"; the self-written class glossary is gone)
- [x] Riot's split tips (Illaoi, Quinn) are joined back at refresh

## M19. Measured data, honest gaps (2026-10-03)
Real numbers from Riot's own match data instead of agents' copy work; data only where a
champion is actually played in a role; and when there's no data, say so and let the AI reason,
labelled.
- [x] Role pools: a champion counts for a role when OP.GG says at least 10% of its games are
      there, in every role (`scout/analysis/role_pool.py`); off-role picks are flagged and kept
      out of the measured rankings
- [x] Honest gaps: an off-role pick (Jinx top) is named as "no data" in the report; the writer
      may add how to play it from the kit, starting "No data; AI read:" with the `reasoning`
      source (the validator enforces both; the page tags it "AI read, no data")
- [x] Collector (`scout collect`, and in the background while the app is idle, with its own
      share of the key's rate limit): Emerald+ ranked solo games from Riot's ladder and
      Match-V5; current and previous patch only; each game counted once (hashed); no player or
      game ids stored
- [x] Measured per champion and role (`scout/data/measure.py`): gold, XP and CS difference at
      10 and 15 against the lane opponent, share of minutes 3-10 on the enemy half (laners),
      level 3 and 4 times, first finished item (Riot's build depth 3), takedowns, roaming
      takedowns and kill participation before 14:00, deaths before 14:00, win
- [x] Measured figures set `early`, `waveclear` (lane push) and `roam` by a written rule
      (quarters within the role among champions really played there with 50+ games; DECISIONS
      #86), replacing drafted values, and reach the writer and the Both teams panel as quoted
      figures with games and patch
- [x] Coverage and accuracy: `scout collect --status` and Settings show games measured, how
      many champion-roles have enough games, and the average gap to OP.GG's win rates
- [x] Importer (`scout import-research`, and Settings, Research results): reads agents' replies
      from `research/results/` by their table, checks every row, shows the changes, applies on
      OK, moves applied replies to `research/results/done/`
- [x] Research prompts: only patch notes, game facts and Riot's class definitions are left
      (the number prompts are gone: the collector measures those; enemy runes: see below)
- [ ] Enemy runes: Riot's Spectator-V5 active-game data lists every player's runes once the
      game is on the loading screen; check it in a real game, then show the lane opponent's
      keystone (no agent needed)
- [ ] Let the collector run (common picks reach 50 games after a few thousand games), then check
      the cross-check gap and the coverage list
- [x] What changed since last patch (2026-10-03: "if clear times change, how will we
      know?"): compare each champion-role's measured figures between the current and previous
      patch (50+ games in both) and flag differences beyond normal game-to-game variation (3
      standard errors); shown in Settings, `scout collect --status`, the Both teams panel, and
      given to the writer

## M21. The app tells you what's due (2026-10-03)
- [x] Research status: `research/status.csv` (tracked, so a friend's copy knows too) records
      which prompt was done for which patch; the importer writes it
- [x] A top-bar button when research is due (a new patch with no patch-notes or game-facts
      check yet, or the class definitions never done); it opens Settings, Data and updates
- [x] The app checks GitHub for updates by itself (at start and every 6 hours) and shows an
      "Update available" button in the top bar: one click shows what's new, one more updates
      and restarts (mostly for friends)
- [x] The app refreshes its data by itself every 6 hours while it's open (a new patch's
      champion data, OP.GG's numbers, matchup tables, the backtest), never during champ select
      or a game, and says so only for a new patch (2026-10-03: "is everything else
      automatically updated?"); the Windows scheduled task is now optional
- [x] Research reminders are on the owner's PC only (`owner: true`, 2026-10-03; it was a Settings
      switch before): only the
      person who runs the research sees "Research due"; it goes away as soon as results are
      applied, and for everyone else once the owner's commit reaches them
- [x] Research results for 26.19 applied (17 kit changes to the review queue, 16 class
      definitions, game facts confirmed); when the game facts reply and the patch notes reply
      give the same fact, the full game facts check wins
- [x] Docs: `PATCH_UPDATE.md` has what updates by itself and how often, when things come out
      and how Sidekick notices, the research round step by step, every source, and what's
      shared through GitHub versus kept on each PC; README has the friend's install step by step
- [x] Hotfixes (2026-10-03: "a good idea"): each refresh on the research PC reads the LoL
      Wiki's page for the patch (V26.19) for mid-patch updates ("Hotfixes" with dated entries,
      or sections like "October 2nd Queue Update"; `scout/data/patch_updates.py`). Applying the
      patch notes research records which ones it covered (`research/status.csv`, `covered`); a
      new one makes the patch notes research due again
- [x] The research prompts write themselves (2026-10-03: "the prompts I send are
      customized to what is needed ... I can just send it every time"): the patch number is
      filled in; after a hotfix the patch notes prompt asks only about that update; they're
      rewritten after each refresh and each applied reply on the research PC, only when their
      text changes; nothing to fill in. Settings has "Open the research folder"
- Declined: sharing the measured match data with friends through git (2026-10-03: match
  data stays private and out of git; another agent handles privacy)
- [ ] Matchup notes per person: `data/manual/matchup_notes.csv` is shared through git, so the owner's
      notes would show as a friend's "Your notes" (empty so far; part of the privacy work another
      agent is doing)

## Collected match data, the owner's PC only (2026-10-03; docs/MATCH_DATA.md)
- [x] `owner: true` in config.yaml marks the owner's PC: only it collects Riot match data, runs
      the backtest in each refresh and gets research reminders; everyone else (`owner: false`,
      the default) doesn't, and Settings hides "Match data" and "Research results" for them
      (the research reminder switch is gone: the owner gets them). `scout collect` refuses on
      other PCs. What the games teach reaches everyone through the code
- [x] Collecting stops at 4,000 games per patch (`PATCH_TARGET`) and starts again with the next
      patch; `scout collect --status` shows games against the target
- [x] Each collecting run first drops older patches' totals, matchups and records (the current
      and previous patch stay), and "already counted" marks after 30 days: about 15 MB at most
- [x] More from each game: first blood, solo kills, the level 2 time and race, plates in the
      lane; for junglers the first gank (whether and when), dragons, voidgrubs and Herald by
      20:00 and the first dragon; every figure's lane opponent, with totals per matchup
      (`measured_matchups`: win, gold/XP/CS at 10, gold at 15, lane push, solo kills, the level 2
      race, early deaths); each game record keeps the ladder tier it came from
- [x] Each game played with the app (with a Riot key) is kept for a later review:
      `reports/<report>.review.json` (every player's figures, what happened, each call's result)
- [ ] Use the matchup totals in the lane read once common matchups have enough games (with M20's
      fitting)
- [ ] Future project: the post-game review against the plan (`docs/future/postgame-review/`)

## One report per game (2026-10-03: "never the free draft read; straight from champ select to the LLM report")
- [x] No report when picks lock: the app shows "Picks locked, your report comes at the loading
      screen"; trades after that still count (the report uses the draft as it stands at
      loading). The trade debounce and its setting (`report.rerender_debounce_seconds`) are gone
- [x] At the loading screen, as soon as the roster shows the summoner spells: roles confirmed,
      the players' records and the likely-duo / one-trick check start, the report is built, and
      the app shows "Writing your report" while the writer waits (up to 15 s) for both, then
      writes them in (the duo lines as a "Loading screen" section the AI writes); the written
      report is the only report shown, for every role (the jungler's dashboard shows the duo
      lines too now)
- [x] With the AI writer off the rules version is the report; if the writer fails, the rules
      version is shown with a one-line note; if the roster never shows, the report is built
      with the guessed roles
- [x] `scout demo` and the docs follow the new flow

## Audit (2026-10-03: "confirm everything is complete, connected, and nothing unused")
- [x] Unused code removed (old config pool writer, unused helpers in draft, stats_db, champ,
      context, cdragon); every module is imported; the excluded-rules test calls `conflicts()`
- [x] Every doc checked against the code by four read-only agents (about 90 findings) and fixed:
      SPEC, ARCHITECTURE, README, CLAUDE.md, KNOWLEDGE, TRAITS, COUNTERPICK, RULES, ROLES,
      REPORT_AGENT, STATS, LCU, POLICY
- [x] Bugs it found, fixed with tests: stats arriving after the final report dropped the written
      version and fell back to the draft read; background work ran during a game the watcher
      wasn't following (Swiftplay, the app opened mid-game); a row the owner wrote lost early, wave
      clear, roam and scaling to measured and OP.GG levels; accepting a row in `scout review`
      made its drafted crowd control and mobility override Riot's ratings; COUNTER-WE-SCALE told
      junglers "losing lane slightly is fine"; a one-champion list gave a single pick option; pick
      and lane win rates showed no game count; the "mostly last patch" flag fired when OP.GG was
      ahead; data several patches old was blended as "last patch"; `scout doctor` never checked
      briefs against OP.GG's lane labels; OP.GG guides for off-role picks failed to parse;
      measured figures followed OP.GG's patch, so a new patch's figures went unused while OP.GG
      lagged (now Riot's own patch); the update check ran during games
- [x] The jungle clear level was computed but unused: junglers' measured figures now say their
      clear speed in words ("among the fastest (top quarter)"), ranked among junglers
- [x] REVIEW_BRIEF.md (the summary for outside reviews) brought up to date
- [x] Config: `riot_id` and `main_role` dropped (unused; older files still load), `ollama_url`
      documented

## M23. History: past games in the app (2026-10-03)
- [x] Each final report's dashboard screen is saved next to the report (`reports/<report>.view.json`,
      gitignored: nothing goes to GitHub), rewritten when the written version or the players
      arrive, with the account that played (`scout/report/past.py`, the watcher)
- [x] A History button in the top bar: past games newest first (when, account, champion, lane
      opponent, written or not, how many calls came true after the game), a filter by account
- [x] Opening one shows its whole dashboard (Both teams works too) with the post-game results
      under it, and "Back to now"; a new champ select takes over by itself. Reports from before
      History show their saved text
- [x] The post-game check skips the saved screens when it looks for claims to grade

## M22. The Champions page, one list per account, look fixes (2026-10-03; built 2026-10-03)
- [x] Scrollbars in the app's colors everywhere (Settings showed Windows' light grey one)
- [x] An × at the top right of Settings instead of Close at the bottom left (the Both teams
      panel got the same ×)
- [x] No A- / A+ text-size buttons (the text is back at its default size)
- [x] The champion search: pictures in the list, a bigger list, no blank area at the bottom
      (Sidekick's own list instead of the browser's; it opens above the box when there's no
      room below)
- [x] Champions is its own page, from a top-bar button where A- / A+ were; Settings keeps the
      account, AI writer, data and updates
- [x] Changes save as you make them; no "Saved your champions (pool.yaml)" line in the top bar
- [x] Each League account keeps its own champions (`pools/`, `scout/accounts.py`): the list
      follows whoever is logged in to the client, every change saves to that account's file,
      and a new account starts from a copy of pool.yaml
- [x] Suggestions from your own recent games: a champion played 4+ times ("more than 3") in a
      lane in the client's recent games that isn't in that lane's list, with Add / No; a No is
      remembered per account and lane
- [x] "Suggest from my most-played" only suggests champions not in your list yet, and names the
      lane to add each to (where it's played most, OP.GG)
- [x] The nightly matchup refresh covers every account's champions
- [x] Answered: what Refresh data updates and what still needs a research prompt
      (`PATCH_UPDATE.md`, "In short")
- [x] Nothing to type for your account: Settings shows who is logged in (read from the client)
      and the Riot ID box is gone (nothing used it); the region is set from the server your own
      recent games were played on (their `platformId`), the list stays only for an account
      with no games yet
- [x] Answered: the logged-in account's champions feed the pick options and the "not in your
      pool" note; the report and the AI writer work from the champ select itself, so they need
      no name
- [x] Answered: bot and support pick options change as teammates lock champions (OP.GG's duo
      numbers with each locked ally, the team's damage mix, crowd control and frontline), not
      while they only hover (offered, REQUESTS D8)
- [x] A note above your champion lists: keep the star ratings accurate, since your pick options
      are ranked with them
- [x] The waiting-for-the-client line is shorter, with no semicolon ("Open the League client to
      start.")
- [ ] the owner: close and reopen Sidekick (the window loads the page when it opens), then open the
      Champions page and Settings with the League client open: check the recent-games
      suggestions and that Settings shows your account and region (the match-history format is
      Riot's match-v4 shape, not yet seen live; if Sidekick can't read it, the page says so and
      the log names the fields it saw)

## M25. Nothing personal in git (2026-10-03: "nothing saved by me in the GitHub repo")
- [x] Test data made up: the six sample champ select sessions, the post-game match and its
      draft, the shove-lane and unsure-jungler games, and the OP.GG profile (DECISIONS #111)
- [x] The owner's name, Windows user folder, time zone and real report names gone from code,
      docs, tests and the research archive; the trait source is `owner` (DECISIONS #112)
- [x] `config.example.yaml` starts with no champions; real recordings are gitignored
- [x] The owner's past match data deleted from this PC (reports, history, cache); the stats
      database kept (public OP.GG numbers and anonymous ladder games only)
- [x] One clean first commit replaces the history on GitHub (DECISIONS #110)
- [ ] The owner: turn on GitHub's "Keep my email addresses private" and "Block command line
      pushes that expose my email" (Settings, Emails)

## M24. A real installer (2026-10-03: "no commands at all, safe, looks and feels professional")
- [ ] Program files and personal files apart: the program in `%LOCALAPPDATA%\Programs\Sidekick`,
      each Windows user's settings, keys, champion lists, reports, recordings and data in
      `%LOCALAPPDATA%\Sidekick` (the developer copy uses the same folder)
- [ ] `Sidekick.exe` built with PyInstaller (its own Python inside), a hidden helper for data
      refreshes, version and icon in the file details
- [ ] Inno Setup installer: per user (no admin), Start menu and Desktop, uninstall entry, WebView2
      if missing, waits for Sidekick to close, reopens it after an update, asks before deleting
      your settings on uninstall
- [ ] Updates from GitHub Releases (no Git needed), checked against a published SHA-256
- [ ] GitHub Actions: tests, lint, build and publish a release when the app changes
- [ ] README for beginners: download, the two Windows warnings, first start, your champions,
      the keys, updates, removing the old version (REQUESTS A14, B26, B27)
- [ ] Tested: a clean install, an update between two releases, an uninstall

## Parked (the owner decides when)
- [ ] Live in-game numbers (your lane's gold and item lead, levels, CS) from the game's own
      local data feed, as a switchable feature; conflicts with hard rule 2 (REQUESTS E18)

## M20. Backtest every judgment (2026-10-03: "make the judgments really strong")
- [x] The collector also keeps a small record per game: the ten champions and roles, and what
      happened from each side (gold at 15 per lane, who pushed, early deaths, first gank lane,
      jungle start side, each enemy's gold share, length, winner); no player or game ids
- [x] The grader works from those records too (match -> outcome -> grade), so the post-game
      check and the backtest grade the same way
- [x] `scout backtest`: for each stored game, run Sidekick's analysis on its draft and grade every
      read against what happened, building a track record per read, rule and lane label
      (`data/history/backtest.csv`), each against always guessing the usual outcome
- [ ] Enough games to judge by: a few thousand stored games (the app's collector, or `scout
      collect`); records start with games collected from 2026-10-03
- [x] First real backtest (114 games, 2026-10-03, with OP.GG's numbers): calling a lane for one
      side is right 57% of the time (that side wins about 36% of lanes overall), so it carries
      signal; calling a lane "even" is right 17% (at Emerald+ most lanes end 500+ gold apart
      by 15), and calling it "quiet" is right 32% (most lanes see 4+ kills and deaths by
      14:00): those two cut-offs are the fitting step's first job. Gank lane (37% vs 40%),
      jungle start and the fed threat are at the baseline. Fixed on the way: OP.GG guides for
      off-role picks failed to parse (empty game-length rates), 68 of about 1,100 calls
- [ ] Fit the lane model's weights and the cut-offs to outcomes (logistic regression on gold at
      15 and lane push); keep the old values when the fit isn't clearly better
- [x] `scout backtest --fetch` first gets OP.GG's matchup tables the stored drafts need, so lane
      reads are graded as live reports make them; results split by what a lane read was based
      on (OP.GG's numbers or traits only). `scout refresh` reruns the backtest (offline)
- [x] Each call's record goes to the writer (`track_record`, 100+ checked games): a call that
      doesn't beat the usual result is stated as a lean ("right 61% of 1,240 games" otherwise)
- [ ] Retire rules whose hit rate doesn't beat the usual result, once there are enough games
- [ ] Show each call's record in the app's report view too

## M18. Picks for the whole team (2026-10-03; built 2026-10-03)
- [x] Pick options ranked on data for the draft so far: the matchup against my lane opponent plus
      OP.GG's synergy with each locked ally (DraftGap-style sum of deltas); team-need facts
      (damage mix, crowd control, knock-ups for a Yasuo, frontline) as reasons, from sourced data
- [x] A draft's OP.GG calls aren't repeated every second when they fail or have no data
      (`RETRY_AFTER_S`, 10 minutes)
- [ ] "Bad into their comp" (Rammus into a mostly magic team): needs matchup data across roles;
      no source yet (a research prompt could look for one)

## M9d. New champion notes from the review (drafted, the owner reviews)
- [ ] `early_push` 0-3 (kill an early wave cheaply), jungle `clear` and `l3_gank` 0-3, `sustain`
      0-3, kit tags (stacking, execute, reset, % health damage); drafted from Riot's ability
      text for all champions, `reviewed=n`
- [ ] The lane read uses `early_push` for Priority once it exists (waveclear until then)

## M14. The Sidekick app, no command line (2026-10-03; built 2026-10-03)
- [x] `sidekick.exe` (pip's no-console launcher from `[project.gui-scripts]`, in
      `.venv\Scripts`) opens the app; `scout watch` opens the same app (`scout/app/main.py`)
- [x] First start does the setup: config.yaml and .env from the examples, an empty pool.yaml,
      then downloads the champion data with progress in the window
- [x] Desktop and Start-menu shortcuts with Sidekick's icon (Settings button, `scout shortcut`,
      install.ps1); one copy at a time; Sidekick's own taskbar icon
- [x] Update button (Settings, Data and updates): checks GitHub, lists what's new, pulls
      (fast-forward only: never overwrites local edits), restarts through a small helper that
      reinstalls only when pyproject.toml changed, then refreshes the data and says what changed
- [x] Settings page: your champions per lane with 1-5 comfort stars (pool.yaml; your
      most-played from the client as suggestions), used by pick suggestions; your Riot ID and
      region; the AI writer on/off with today's cost; the Riot and Anthropic keys (tested
      before saving); refresh data; shortcuts; open the reports and log folders
- [x] Looks: champion pictures (Data Dragon squares, downloaded once to data/cache/img), the
      logo, the same dark theme throughout. Role icons skipped: the gold lane labels read fine
- [x] install.ps1 and README for friends: install once, then everything from the app
- [x] Data format check: an update that changes a static file's columns makes the next refresh
      rebuild it (`static_complete` compares headers)
- [ ] the owner: open it from the Desktop shortcut for a real game; try Update after the next push
- [ ] Known gap: pinning the running window to the taskbar pins Python, not Sidekick. Pin the
      Start-menu shortcut instead (fixing it needs the shortcut's AppUserModelID, not set yet)

## M10. Post-game check (built 2026-10-03)
- [ ] Riot personal API key registered (`POLICY.md`; developer.riotgames.com, Register Product,
      Personal API Key) (the owner; the 24-hour development key works meanwhile)
- [x] `data/riot.py` (Account-V1, Match-V5 match and timeline)
- [x] Save each report's predictions as structured claims (`reports/<report>.json`, next to the
      final report): lane winner, who pushes early, early kills, first gank lane, jungle start,
      the fed threat, the long game (`scout/postgame/claims.py`)
- [x] `scout postgame` (and automatic at end of game in the app): fetch the match by the
      client's game id (no player lookup) and its timeline, grade each claim by the review's
      table (`scout/postgame/grade.py`), append to `data/history/postgame.csv`
- [x] Offer to add a matchup note (`scout postgame`)
- [x] `data/history/rule_accuracy.csv`: hit rate per claim kind, per lane label, per rule
- [x] Fitting the lane weights and retiring rules moved to M20 (the backtest has thousands of
      collected games to work from instead of 100-200 of the owner's own)
- [ ] the owner: play a game with the app open and check the post-game line (Riot can take a few
      minutes to publish a match; `scout postgame` checks it later)

**Done when:** after a real game, the check runs and its results show up in the accuracy table.

## --- v1 is M0 to M10. Check `SPEC.md` acceptance criteria here. ---

## M11. Loading-screen addendum (built 2026-10-02; live check waits on the owner's Riot key)
- [x] Participant list at loading screen (LCU gameflow session; identities kept in memory only)
- [x] Likely duos: shared recent matches **on the same team**; skip hidden players
- [x] Enemy one-tricks via champion mastery; no ratings of players (`POLICY.md`)
- [x] One short addendum, then stop (enemy role confirmation moved to M6)
- [x] the owner added a Riot key (2026-10-03; the collector runs on it)
- [ ] Check the loading-screen addendum live in a real game

## M12. Polish and extras (optional)
- [x] Patch-notes helper: done another way (M19): the `research/patch_notes.md` prompt and the
      importer put changed champions in the review queue with Riot's words
- [ ] Draft lean (DraftGap-style sum of matchup and synergy deltas), shown as a lean, never a %
- [ ] Our own matchup numbers from Match-V5 for the owner's bracket (`STATS.md`)
