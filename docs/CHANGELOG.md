# CHANGELOG

One line per finished task or fix: date, what changed, why.

- 2026-10-03: M25, nothing personal in git: the repo starts over with one clean commit (private
  noreply author); the test games, sample champ select sessions, post-game match and OP.GG
  profile are made up; the owner's name, user folder and time zone are gone from every file;
  the trait source is `owner`; real recordings are gitignored; the example config has no
  champions.
- 2026-10-03: One report per game (the owner): no draft read when picks lock ("Picks locked, your
  report comes at the loading screen"); at the loading screen, as soon as the summoner spells
  show, Sidekick gathers the players' records and likely duos and the AI writes them into the
  one report ("Writing your report" until then). The jungler's dashboard now shows the duo
  lines too. Rules version only with the AI writer off, or labelled if the writer fails. The
  trade debounce and its setting are gone.
- 2026-10-03: The audit (the owner: "confirm everything is complete and connected"): every doc
  checked against the code and fixed; unused code removed. Bugs it found, fixed with tests:
  late stats after the final report dropped the written version; background work ran during
  a Swiftplay game or one the app opened mid-game; the owner's own rows lost values to measured
  data; accepting a row in `scout review` let drafted ratings override Riot's; junglers were
  told "losing lane slightly is fine"; a one-champion list gave a single pick option; win rates
  in pick options and the lanes overview had no game counts; the "mostly last patch" flag and
  the previous-patch blend were wrong in edge cases; `scout doctor` now checks briefs against
  OP.GG's lane labels; measured figures now follow Riot's patch (they went unused while
  OP.GG lagged a new patch); the update check waits for games. Junglers' clear speed is now
  said in words. Unused config keys (`riot_id`, `main_role`) dropped.
- 2026-10-03: M23, History (the owner): a top-bar button lists your past games on this PC (when,
  account, matchup, how many calls came true after the game) and opens any of them as its full
  dashboard; kept in `reports/` only, never sent to GitHub. M21, hotfixes and self-writing
  prompts: each refresh on the research PC reads the LoL Wiki's patch page for mid-patch
  updates, and a new one makes the patch notes research due again; the research prompts are
  rewritten for what's due (the patch filled in, a hotfix round about that update only), so
  they're sent as they are. Fixed: OP.GG guides for off-role picks failed to parse (empty
  game-length rates; 68 of about 1,100 calls in the first backtest). First real backtest
  (114 games): calling a lane for a side carries signal (57% vs about 36%); the "even" and
  "quiet lane" calls don't fit Emerald+ games yet (the fitting step's first job). Audit:
  unused helpers removed, the excluded-rules test uses `conflicts()`.
- 2026-10-03: M21, the app keeps itself current: it refreshes its data every 6 hours while
  it's open and you're not in a game (new patch data, OP.GG's numbers, matchup tables, the
  backtest), so nobody needs the Refresh button or a scheduled task. Research reminders are a
  Settings switch (on for the owner, off for new installs), and "Research due" goes away as soon as
  results are applied. Research for 26.19 applied: 17 champions with kit changes to the review
  queue, 16 of Riot's class definitions, every game fact confirmed (the importer now keeps the
  full game facts check over a patch notes reply's partial row). Docs: what updates when and
  how Sidekick notices, the research round, every source, what's shared with friends
  (`PATCH_UPDATE.md`); the friend's install step by step (README).
- 2026-10-03: M22, a note on the Champions page to keep your star ratings accurate (your pick
  options are ranked with them); the waiting-for-the-client line is shorter, with no semicolon.
- 2026-10-03: M22, nothing to type for your account (the owner): Settings shows who is logged in,
  read from the League client, instead of a Riot ID box nothing used; the region is set from
  the server your own recent games were played on.
- 2026-10-03: M20, track records: `scout backtest --fetch` first gets OP.GG's matchup tables
  the stored games need, so lane reads are graded as live reports make them, and splits the
  results by what each lane read was based on. `scout refresh` reruns the backtest. The writer
  now gets each call's record (100+ checked games): a call that doesn't beat the usual result
  is stated as a lean.
- 2026-10-03: M22, the Champions page and one list per account (the owner): your champions moved
  out of Settings to their own page (the Champions button, where A- / A+ were), saving as you
  go. Each League account keeps its own list in `pools/`, switched by whoever is logged in to
  the client. New suggestions from your recent games (4+ games in a lane) with Add / No, and
  "Suggest from my most-played" now skips champions you have and names a lane. The champion
  search shows pictures in a bigger list of its own (no more blank area); scrollbars in the
  app's colors; an × closes Settings; the text-size buttons are gone.
- 2026-10-03: M20 starts, backtesting: the collector now keeps a small record of each game it
  measures (both drafts and what happened, no ids), and `scout backtest` runs Sidekick's whole
  analysis on every stored draft, grades each read the way the post-game check does, and
  compares it with always guessing the usual outcome (`data/history/backtest.csv`). It needs a
  few thousand games before the numbers mean anything. Also: docs dated 2026-10-04 corrected
  to 2026-10-03.
- 2026-10-03: Changes since last patch: measured figures that moved beyond normal variation (for
  example a jungler reaching level 4 nine seconds sooner) are flagged in Settings, `scout
  collect --status` and the Both teams panel, and given to the writer.
- 2026-10-03: M21, the app tells you what's due: it checks GitHub for a new version at start
  and every 6 hours and shows an "Update available" button in the top bar; a "Research due"
  button appears when a new patch needs the patch-notes or game-facts prompt (or the class
  definitions were never done), tracked per patch in `research/status.csv`.
- 2026-10-03: M19, measured data and honest gaps: Sidekick now measures the numbers itself from
  Riot's match data (`scout collect`; the app collects in the background while you're not in a
  game): gold/XP/CS against the lane opponent at 10 and 15, who pushes, level 3/4 timings,
  first finished item, roaming and kill participation before 14:00, per champion and role,
  Emerald+, with coverage and an OP.GG cross-check. The figures replace drafted early, wave
  clear and roaming values and reach the writer. Role pools (OP.GG, 10%+ of games) in every
  role; off-role picks are named as "no data", and the writer may add its own read, labelled.
  `scout import-research` (and a Settings button) reads agents' replies; the research folder is
  down to patch notes, game facts and Riot's class definitions.
- 2026-10-03: Research prompts rewritten by a new `scout research` command, after a review of
  whether an outside agent could follow them: each now carries its data (the numbered champion
  list with roles, the 53 junglers, today's game facts) and what Sidekick already has, works in
  batches of 20, collects only the sources' own figures and words (no ratings of the agent's
  own, which the old wave clear, engage, early game and roaming prompts allowed), fixes the rank
  filter (Emerald+), and ends with an exact reply format and file name. The docs now say the
  repo is public (a friend needs no collaborator access to install and update).
- 2026-10-03: M10, the post-game check: the final report saves its predictions as claims; after
  the game the app (or `scout postgame`) fetches the match by its game id, grades each claim by
  the outside review's table (gold at 15, positions in minutes 3-10, early deaths, the first
  gank, the jungle start, the fed threat, game length), appends to data/history/postgame.csv,
  rebuilds rule_accuracy.csv and offers a matchup note. A Settings switch turns off players'
  records at the loading screen (the review flags Riot's policy on them).
- 2026-10-03: M18, picks for the whole team: options now add OP.GG's synergy with every locked
  ally (DraftGap-style) and name a strong or weak pairing; team-fit reasons come from sourced
  facts (knock-ups for a Yasuo, damage mix, Riot's toughness and control); drafted tags count
  only once reviewed. Fix: a draft no longer repeats failing OP.GG calls every second.
- 2026-10-03: M17, the whole team in plain words: lane opponents' kits on the main view, a
  Both teams panel with every champion's kit, Riot's ratings, the wiki's mechanics and Riot's
  tips; the writer gets all ten champions and a restructured prompt (what each field is, where
  it comes from, what to do with it); the self-written class glossary is gone; Riot's split
  tips are joined back.
- 2026-10-03: M16, players at the loading screen: each visible player's OP.GG record on the
  champion they're playing (rank, ranked games, win rate from 5 games, average K/D/A, recent
  results), as a strip under the report and a Players section for the writer; hidden players
  skipped, no names anywhere ("their Sivir player"). POLICY.md records the owner's decision.
- 2026-10-03: M15, sourced data: crowd control, mobility and toughness are Riot's own ratings;
  knock-ups and stealth come from the LoL Wiki's mechanic categories (new `mechanics` column,
  read from the wiki at refresh); "needs airborne" from Riot's text; scaling from OP.GG's win
  rate by game length, now fetched for all ten champions, with the numbers quoted. Each value
  records its source, and the writer is told which facts are Riot's, the wiki's, OP.GG's or
  drafts. New `data/manual/game_facts.csv` (objective and camp timers, role quests, each line
  cited) in the jungler's Start and objectives and the writer's input. New
  `docs/PATCH_UPDATE.md` (every data file and the per-patch checklist) and `research/` (nine
  prompts for what has no source yet). Several drafted values were wrong (Vex and Nautilus
  "no escape"); the golden reports changed accordingly.
- 2026-10-03: M14, the app without a command line: `sidekick.exe` and Desktop/Start-menu
  shortcuts (install.ps1 sets everything up for a friend); first start makes the settings files
  and downloads the data; a Settings page (your champions per lane with 1-5 comfort stars in
  pool.yaml, which pick suggestions now use; Riot ID and region; the AI writer on/off with
  today's cost; Riot and Anthropic keys tested before saving; refresh data; shortcuts); an
  Update button (checks GitHub, fast-forward pull, restart, refresh); champion pictures and the
  logo; `scout watch` opens the same app.
- 2026-10-03: Report fix (a losing bot lane): the game plan no longer tells a laner whose lane
  is losing to "press your early advantage" (it's a whole-team read); test added. The section
  "Don't let get fed" is now "Don't let them get fed".
- 2026-10-03: Fixed the loading-screen duo check before its first real game: the client's player
  ids are now turned into Riot IDs (client, read-only) and then web-API ids (Account-V1); the
  web API rejected the raw client ids. Blue/red mapping confirmed with Riot's match data.
- 2026-10-02: M13 first version: `scout watch` opens the Sidekick window (`scout/app/`), which
  follows the client by itself: waiting for the client or a game, pick options and the draft
  board in champ select, the draft read when picks lock, the final (written) report at the
  loading screen, game over. One page per role: plan banner, lane card with wave-control and
  fight bars and a who's-favored-by-phase strip, Know your opponent (Riot's text), your jungler
  or lanes at a glance with gank ranks, counter-pick with game win rate and their build, threats,
  team damage mix. `scout demo` shows the screens with a saved game. New dependency: pywebview.
- 2026-10-02: Riot's own words about each champion: Data Dragon's `allytips`/`enemytips` (147 of
  173 champions) are now kept (`tips.csv`, rebuilt by `scout refresh`). Laners get a "Know your
  opponent" section: each lane opponent's passive and up to two of Riot's tips against them (both
  enemies in bot lane); the jungler gets the enemy jungler's. The writer gets the opponents' whole
  kit and Riot's tips, and is told to explain them without adding anything.
- 2026-10-02: M9c, part 2. Summoner spells: ours from champ select, everyone's from the loading
  screen; Ignite/Exhaust add to a side's all-in (and so to volatility); new rules
  `LANE-KILL-SPELLS-THEM` and `CHAMP-TP-THEM`. Map side (blue/red) from champ select, shown in
  the report header (team 2 = red: in every recording the other team picked first). Two phases
  (the owner): champ select gets pick options and the free rules report; the loading screen makes the
  final report (roles confirmed, spells, duos), the only one the LLM writes (one call a game).
  Game files take optional `side` and `spells`. Two more recorded champ selects.
- 2026-10-02: M9c, part 1 (from the outside review and the owner's notes). Only what's relevant to
  my role: snowball and late-carry warnings go to that champion's lane and the junglers; the
  feed list for laners names only threats they can affect; jungle-only advice goes to the
  jungler, laners get their own versions; skirmish and roam lines name the champions; no
  "Other lanes" list for laners; new `JG-LANER-FIGHTS-2V1` for the jungler. Lane read is now
  Priority (who pushes, bot as a unit) x Fight (trades and all-ins, engage discounted when it
  can't reach someone): bully, push edge, shove and respect, bait lane, pushed, survive; new
  rules for each plan. Volatility = how likely someone dies (both sides' all-in threat).
  Wording: no level 1-3 jungle asks, game win rates labelled as such, "Best gank options".
- 2026-10-02: `scout key` (paste a new Riot key into `.env`, tested first, never echoed);
  `scout doctor` and `scout watch` test the Riot key with one status request and say plainly when
  a 24-hour development key has expired.
- 2026-10-02: `docs/REVIEW_BRIEF.md`: a self-contained summary of everything the report
  considers and what it doesn't, with questions, to send to another AI for a gap review.
- 2026-10-02: Fix for a shoved lane (Kog'Maw/Braum vs Sivir/Seraphine: shoved under tower
  all lane, no deaths, no farm). The written report said "early game favors you through level
  6" because the lane timeline ignored OP.GG's "they win early" label. Now: when the numbers
  decide a lane, levels 1-3 and 3-6 follow them, and no "your lane plus jungler win early
  fights" claim contradicts them. New wave-control signal: a waveclear gap (3 vs 1 or less)
  means the out-pushed side can't be "winning", isn't favored early, and asks its jungler for
  cover instead of being "self-sufficient"; new rules `LANE-SHOVED-THEM` / `LANE-SHOVE-US`. The
  scenario is a fixture (`bot_shove`) with golden files for support and jungle.
- 2026-10-02: M11 built (off until a Riot key is in `.env`). `scout/data/riot.py`: Match-V5 and
  Champion-Mastery-V4, GET only, personal-key rate limits counted locally. `scout/loading.py`: at
  the loading screen, once, in the background: likely enemy duos (2+ of their last 20 ranked
  games together on the same team) and one-tricks (their champion is their top mastery by 3x,
  or 1M+ points); hidden players skipped and counted; champion names only. The lines are added
  to the shown report and the saved file. `scout watch` says at start whether it's on.
- 2026-10-02: M9b built. `scout/picks.py`: 2-3 options for my role before I lock, ranked by the
  shrunk matchup rate against my lane opponent (by the role guess) or by blind safety (own win
  rate, hard counters among the role's 10 most-played), comfort breaking near-ties (within 1
  point), one team-fit reason (their auto-attackers with the new `anti_auto` tag, our damage
  mix, frontline, engage). Candidates: pool, else most-played from champion mastery (new
  read-only endpoint), else easy champions strong this patch. `scout watch` shows them in the
  window and terminal as they change and prefetches the candidates' matchup tables; an
  off-pool lock gets a note in the report. `scout pool` shows and edits the pool (only the
  pool lines of config.yaml change).
- 2026-10-02: M9 built. `scout/counterpick.py`: verdict from the shrunk matchup rate (bands
  from config), specific counter vs weak patch (delta vs both champions' expected result), pick
  order, structural fallback from traits, alternatives for unsure enemy roles (from my own
  matchup table, no extra fetch). New `counterpick` rule scope with 8 rules (laner and jungle
  versions). The report's Counter-pick section opens with the verdict and its numbers; the
  writer gets the counter-pick block. Matchup briefs: `scout/data/briefs.py` (validator that
  rejects drafts contradicting OP.GG's lane advantage, numbers outside both kits or item
  names; append-only writer; `brief_stale` rows from `scout refresh`; `scout doctor` check);
  a brief replaces the computed lane timeline in the report. 15 jungle briefs drafted for the
  pool from ability text and OP.GG data (`reviewed=n`).
- 2026-10-02: M8 built. OP.GG stats: `data/opgg.py` (MCP over plain HTTP, tool check before
  any call, compact-format parser by header, matchup guide and synergy parsers, throttle),
  `data/stats_db.py` (stats.sqlite), `data/stats_service.py` (lane meta and role rates, draft-time
  prefetch with a 5 s budget and one late update, champ pool refresh, fetch log),
  `analysis/stats.py` (expected result, shrinkage, previous-patch blending, display strings,
  per-game stats). Role guesses use OP.GG role rates (wiki for champions it lacks). OP.GG's
  lane-advantage label decides lane verdicts when the sample is big enough; disagreements with
  traits get a warning and a `stats_disagree` review row. Reports show matchup numbers, bot duo
  synergies, the opponent's usual build into you and OP.GG's tip; `stats.*` rule paths are
  filled. `scout refresh --stats/--pool`, `scout report --fetch`, `scout watch --no-stats`,
  doctor shows stats age; nightly Task Scheduler line in the README. `opgg_name` filled in
  static data. The `mcp` dependency is dropped (DECISIONS.md #40).
- 2026-10-02: Fixes from the first live test (the report, the
  loading-screen role fix and the written version all worked): skipped bans (`-1`) no
  longer warn "unknown champion"; the window re-wraps items to its own width instead of
  breaking pre-wrapped lines twice; our own team's combos (pair rules) go to a section
  for our plan (support: Protect or engage, bot: Fights, top: Your job, jungle and mid:
  Game plan) instead of "Watch out for". Two new recordings; the off-meta draft
  (Morgana jungle, Tryndamere mid) is a known exception in the role answer-key test.
- 2026-10-02: M7 built. The LLM writer: `report/builder.py` (input JSON with only the
  champions and abilities the report mentions, Riot's ability text), `report/validator.py`
  (sections, sources, numbers, item and ability names, soft length), `report/writer.py`
  (one retry, fallback to the rules report, cache by draft, daily cap, usage and cost log),
  `render_written`, shared `scout/llm.py` (Anthropic and Ollama). `scout watch` shows the
  written version a few seconds after the rules one; `scout report --write`; `--no-llm`;
  doctor shows today's calls and cost. Tuned with 13 real calls (about $0.11): the prompt now
  limits lines per section, which fixed overlong answers.
- 2026-10-02: Depth pass from the owner's review: every report shows all three lanes at a glance;
  the jungler gets a suggested route (start side, first gank, where their jungler goes, a
  counter-gank chance); new early-fight insight for each lane with both junglers and six
  rules (river 2v2, bot side, top side); fallback lines for top's job, the support's
  engage or peel job, and bot's biggest dive threat. `JG-START-SIDE` replaced by the route.
  TASKS.md gained a "where things stand" summary, known gaps, and M7 cost-safety items.
- 2026-10-02: M6b built. `scout watch` opens a report window (drag it to a second monitor; it
  reopens there), with bold section headings, a status line, text size buttons and an
  always-on-top option; `--no-window` keeps it terminal only. Fixed negative window
  positions (a monitor left of the main one).
- 2026-10-02: Attack range and move speed (from the wiki) added to `champion_meta.csv`; a range
  gap per lane (ADC vs ADC in bot) and rules for melee vs ranged mid, big ADC range gaps, and
  enemies whose range changes with form (Gnar, Jayce are flagged instead of misread). Goldens
  updated on purpose (Ahri outranges Yasuo; Caitlyn outranges Jinx).
- 2026-10-02: M6 built (the test version). `scout watch`: polls the client (woken early by
  the client's WebSocket events), reports when picks lock, re-renders after trades (1.5 s
  debounce), confirms or corrects enemy roles from the loading roster (who has Smite) and
  re-renders once, discards on dodge, records every champ select, survives bad reads.
  Non-draft queues (ARAM and others) are named and skipped. Tests replay a recorded
  draft through the watcher. Waiting on 5 real games for the done-when check.
- 2026-10-02: M5 done. Insights in `scout/analysis/` (lane state and timeline, gankability,
  jungle threat and ranks, jungle plans, jungle matchup, priority, roams, cross-map reach,
  team profiles, feed ranking); a rules engine with load-time validation (paths per scope,
  ops incl. new `has_any`, sections, roles, placeholders, tests, excludes), a new `ally`
  scope and `their_lane` audience; 65 rules (36 converted, the role packs added); report
  selection per role with insight and fact items; a plain-text renderer; `scout report
  --file <game> [--role r] [--debug]`. Three game files (one shaped like a recorded draft) with
  goldens for all five roles. Report-time trait loading is structural only (DECISIONS #28).
- 2026-10-02: M4 built. `lcu/champselect.py` turns a session into a GameState (queue gate,
  my cell from the latest session, locked champions only, pick turns by champion, bans, ally
  Smite swap, unknown champions as placeholders, `confirmed_roles` from the loading roster
  for M6); `analysis/role_inference.py` scores every assignment and gives per-role odds,
  partial teams included; `model/gamefile.py` loads hand-written games with fix-it errors.
  Role prior until M8: wiki positions with Riot's in-client positions counted double (new
  `client_positions` column in champion_meta.csv). All 31 snapshots of the first recording
  parse; its jungler is honestly uncertain (59% / 41%) until real role rates.
  Committed a copy of three static tables in tests/fixtures/static/ for offline tests.
- 2026-10-02: M3 done. Every champion (173) has a traits row with scores and briefs:
  150 drafted in a Claude Code session from Riot's ability text, 23 prototype rows converted
  (original values kept, new columns drafted). Trait validation (scales, tags, spikes, lengths,
  no stray numbers, no item names), `scout draft-traits` (Anthropic structured output, one
  retry, appends reviewed=n), `scout review` (recent games, pool, rest; accept/edit/skip,
  saves only on confirm, resolves queue entries), doctor shows traits coverage. Fixed: the item
  check flagged ability names that contain item names (Golden Eclipse, Cull the Meek).
- 2026-10-02: M2 done. `scout refresh --static` builds champions, abilities, champion_meta,
  summoner_spells and items for the newest Data Dragon version from Data Dragon,
  CommunityDragon (patch-pinned folder) and the LoL wiki (a safe Lua data reader), with
  per-field sources, overrides, validation, a per-version cache, the review queue diff, the
  3-day wiki re-check, `--prune`, and REFRESH_LOG.md. 16.19.1: 173 champions in about 4 s,
  no range disagreements. Dropped the damage-type cross-check: the wiki's adaptive type isn't
  a damage type (it flagged 9 false disagreements). 28 new offline tests.
- 2026-10-02: Plan changes (DECISIONS #24-26): enemy roles confirmed at the loading screen
  (M6), a report window (new M6b), pick suggestions from the champ pool (new M9b, design in
  `COUNTERPICK.md`).
- 2026-10-02: First real recording (ranked solo, jungle, red side) committed. It showed
  pick-order swaps move players between cells (`localPlayerCellId` changes mid-draft), that
  `pickTurn` and `bans` are empty, and a new top-level session `id` token, now blanked by
  name. Findings in `LCU.md` section 3. 1 of 3 recordings for M1.
- 2026-10-02: Enemy roles and pick order written up in one place (`ROLES.md`). The recorder
  now also saves the roster the game shows at loading (champion, position, spells; no
  identities) as the answer key for enemy role guesses; M4 tests against it. Champ pool made
  optional (DECISIONS #23).
- 2026-10-02: M1 live check on the real client (in lobby). The client's certificate lists
  127.0.0.1, so hostname checking is back on; only Python's strict mode stays off. Fixed: the
  recorder would have refused to save (and crashed) because the long game-version string looked
  like a token; it now keeps the part before `+`, and never crashes on an unscrubbed value.
- 2026-10-02: M1 code. `lcu/connection.py` (process args, lockfile fallback with stale-pid
  check, pinned `riotgames.pem` with strict mode and hostname checks off), `lcu/client.py`
  (GET only, endpoint allowlist, one reconnect after a client restart), `lcu/recorder.py` +
  `scout record` (scrubbed, deduplicated snapshots; gameflow allowlist), `scout doctor` client
  check; 43 new offline tests. Live check against the real client still to do.
- 2026-10-02: M0. Rewrote planning docs for all five roles (new ROLES, LCU, STATS, TRAITS,
  POLICY, DECISIONS) based on research into the client API, Riot policy, and data sources;
  reordered milestones (recorder first, test version at M6); scaffolded the `scout` package,
  config loader, CLI, core types, CSV schemas, and offline tests; recorded source samples.
- 2026-10-01: Planning docs and v0 prototype added.
