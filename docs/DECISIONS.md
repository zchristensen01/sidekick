# DECISIONS

Short record of design decisions and why, so they don't get re-argued. Newest first. To change
one, add a new entry that supersedes it rather than editing the old one.

## 2026-10-03: M25 (nothing personal in git)
110. **The repo started over with one clean first commit** (the owner: nothing of theirs on
     GitHub, at any point). The old history had a personal email on every commit, a Windows
     user folder in the README, real games and an OP.GG profile in the test data, and the
     owner's name throughout. Rewriting it commit by commit would keep nothing useful that the
     current files don't already have, so the first commit is the cleaned tree, authored with
     GitHub's private noreply address. Releases are built from this history only.
111. **Test data is made up.** The sample champ select sessions and the post-game match keep the
     client's and Riot's real formats, but every champion is swapped for a look-alike with the
     same role lists, clock times move to a fixed date, skins reset, gold is scaled and event
     times nudged; the OP.GG profile is invented. Real recordings stay on the PC that made them
     (gitignored), and an update's tests never need anyone's real games.
112. **A person's own trait edit is `source=owner`** (it carried the owner's name before):
     `scout review` marks an edited row this way, and such a row still beats every source.

## 2026-10-03: one report per game
120. **No draft read; the one report comes at the loading screen, written by the LLM** (the owner:
     "never the free draft read; straight from champ select to the LLM report"; updates #60).
     When picks lock the app only says so. At the loading screen the writer waits up to 15 s
     for the players' records and the duo / one-trick check, so they're written in, and
     "Writing your report" shows until it answers. The rules version is the report only with
     the AI writer off, and a labelled fallback if the writer fails, so there's always one.
     If the roster never shows, the report is built from the guessed roles rather than none.

## 2026-10-03: the audit
108. **Only an edited row is the owner's** (updates the `scout review` protocol): accepting a row as
     is marks it reviewed but keeps its source, so Riot's ratings and the wiki's mechanics keep
     filling crowd control, mobility and toughness; a row the owner changes becomes `source=owner`, and
     then beats every source, measured levels and OP.GG's scaling included (the figures are
     still quoted). Why: accepting used to freeze the LLM's drafted ratings over Riot's.
109. **Background work waits on the client's phase, not on what the watcher follows**:
     collecting, refreshing and updating pause in champ select, at the loading screen and in
     game (`Watcher.idle`), so a Swiftplay game or a game the app opened in the middle of
     isn't treated as free time.

## 2026-10-03: M21 and M23 (hotfixes, prompts that write themselves, History)
105. **Hotfixes come from the LoL Wiki's patch page**, by its section titles: after the patch's
     own notes, "Hotfixes" with dated entries, or one-off sections ("October 2nd Queue
     Update"). Riot's own news page has no API and hotfixes don't change Data Dragon's
     version. A non-balance update (a queue time) still triggers a short patch notes round;
     the agent says so and nothing changes. The covered updates are recorded with the round.
106. **Only the research PC rewrites the prompts** (research reminders on): they're tracked in
     git, and a friend's app editing tracked files would block its own updates. They're
     rewritten only when their text changes, so a refresh doesn't touch them for nothing.
107. **History keeps the screen as it was shown**, not a re-run: the saved view is what the
     player saw (the written version, the players' records), and a re-run would use later
     numbers. It lives next to the report in `reports/` (gitignored), tagged with the account.

## 2026-10-03: M21 (the app keeps itself current; research for one person)
102. **The app refreshes its data by itself every 6 hours while it's open** (updates M8's
     "nightly scheduled task"): never during champ select or a game, and quietly unless there's
     a new patch. Why: a friend who never opens a terminal would otherwise run on the first
     patch's data until they pressed Refresh data. The scheduled task stays as an option for a PC
     that's on without the app open. The time of the last try is `data/cache/refreshed`.
103. **Research reminders are per person, off by default** (`report.research_reminders`, a
     Settings switch): research is the owner's job and its results reach everyone through git
     (`data/manual/`, `research/status.csv`), so "Research due" on a friend's PC would only
     confuse. The owner's config has it on.
104. **When two research replies give the same game fact, the full game facts check wins**: the
     patch notes reply only has what that patch changed (for 26.19, only the top role quest's
     Teleport cooldown), while the game facts reply re-checks the whole line. Applied replies
     are kept in `research/results/done/` as the record of each fact's sources.

## 2026-10-03: M20 (track records)
100. **Lane reads are backtested with OP.GG's numbers** (`scout backtest --fetch`), because live
     reports have them: offline, nearly every stored draft fell back to traits only (574 of 582
     lane reads in the first 97 games), which grades a path the player rarely sees. Results are
     also split by what each lane read was based on, so the two paths are judged separately.
101. **Each call's record goes to the writer, not just to a CSV**: past 100 checked games
     (about +-5 points), with the lane's own record first and every lane's otherwise. A call
     that doesn't beat the usual result is stated as a lean; the writer may quote a record that
     does. Nothing is hidden or changed automatically: retiring rules stays the owner's call.

## 2026-10-03: M22 (the Champions page and accounts)
95. **Each account keeps its own champions, keyed by its puuid.** The client's current-summoner
    answer says who is logged in (read-only); `pools/accounts.yaml` maps each puuid to a file
    named after its Riot ID, so a name change keeps the list. A new account starts from a copy
    of pool.yaml (nothing to redo, nothing lost); pool.yaml stays for the offline commands.
    Why: a player may use more than one account, and switching shouldn't need any clicks.
96. **Champion suggestions come only from your own games**: the client's recent match history
    (4+ games in a lane: The owner's "more than 3") and your mastery. The lane is the game's own lane
    field; when the client can't say, the lane the champion is played in most (OP.GG). A "No"
    is remembered per account and lane. Why: it's your own data (`POLICY.md`), and asking once
    beats asking every time.
97. **The champion search is Sidekick's own list, not the browser's `<datalist>`**: a datalist
    can't show pictures and drew a blank area in the app's window. Pictures load as rows scroll
    into view, so opening the list doesn't send all 170 at once.
98. **One text size**: the A- / A+ buttons are gone and the saved size is dropped (the owner asked).
99. **Nothing to type for the account (the owner)**: the client says who is logged in, and the
    region is the server your own recent games were played on (their `platformId`, a field of
    Riot's match-v4 format), saved when it differs and left alone when the client can't tell.
    `player.riot_id` stays in config.yaml so older files still load, but nothing reads it: the
    post-game check finds the match by the game's own id.

## 2026-10-03: M20 (backtesting)
92. **The collector also keeps one small record per game** (updates 89's "only totals"): each
    side's ten champions by role and what happened from that side, exactly what the post-game
    grader reads (gold at 15 per lane, positions in minutes 3-10, plates, early deaths, the first
    gank, the jungle start side, each enemy's gold share and kills, length, winner). Still no
    player or game ids: the game is known only by its one-way hash.
93. **One grader for both checks**: match -> outcome record -> grade. The post-game check and
    the backtest can't drift apart, and stored records can be re-graded when a grader changes.
94. **A read is judged against a baseline, not 50%**: always guessing the most common outcome
    for that kind of read (lanes are mostly "even", most enemies don't get fed). A rule or lane
    label is worth showing only when it beats that over 30+ graded claims. The backtest reads
    each draft as that side's jungler, so every lane and the jungle get claims. Caveat: the
    measured figures include the same games, so M20's fitting step holds games out.

## 2026-10-03: M19 (measured data, honest gaps)
86. **Numbers come from Riot's match data, measured by Sidekick**, not from agents copying
    stats pages: the same source the stats sites use, no misreading, the same definitions every
    patch. Agents are left with what only exists as words (patch notes, game facts, Riot's class
    definitions). The one judgment on top of the figures: within a role, among champions really
    played there with 50+ games, a champion's quarter sets its 0-3 level (early from gold
    difference at 10, wave clear from minutes 3-10 on the enemy half, roaming from takedowns
    outside the lane before 14:00, jungle clear from time to level 4). M20 tests and tunes it.
87. **Role pools from OP.GG**: a champion counts for a role at 10%+ of its games there. Off-role
    picks stay out of rankings, prompts and data, and the report says there's no data for them.
88. **Honest gaps (the owner)**: where there's no data, the report says so, and the writer may add
    its own read of the kit, labelled "No data; AI read:". It's the one place the writer may
    reason beyond the input, and the validator holds it to that label.
89. **The collector stores no identifiers**: player ids live in memory while listing games;
    games are remembered by a one-way hash; the database holds only per champion-role totals.
    It takes 80 of the key's 100 calls per 2 minutes and pauses during champ select and games.
90. **First finished item is Riot's definition**: an item with build depth 3 in Riot's item
    data, boots excluded.
91. **"Changed since last patch" needs 3 standard errors** and 50+ games on both patches: with
    about 1,500 comparisons a patch, a looser bar would flag noise every time.

## 2026-10-03: M10 (the post-game check)
82. **Claims are saved with the final report and graded by the review's table**: gold
    difference at 15 for lane winners, laners' positions in minutes 3-10 for who pushed, deaths
    before 14:00 for volatility, the first kill our jungler joins before 10:00, the jungler's
    position at 2:00, the threat's gold share and kills at 15, and game length for scaling.
    The thresholds that judge a measurement (500 gold, 4 deaths, 24% gold share) are tuning
    knobs, named in `scout/postgame/grade.py`.
83. **No map constants**: "your half of a lane" is closer to your own spawn point than theirs,
    and the top and bottom corners come from the two spawn points, all read from the
    timeline's first frame.
84. **The match is fetched by the client's game id** (Match-V5 id = platform + game id), so
    the check needs no lookup of any player; we find ourselves by our champion.
85. **Players' records get a switch** (Settings, `report.player_records`): the outside review
    quotes Riot's policy against showing other players' rank or win rate. On by default
    because the owner asked for it (2026-10-03); POLICY.md has both sides.

## 2026-10-03: M18 (picks for the whole team)
79. **Picks add synergy with every locked ally, DraftGap-style**: score = the lane part (shrunk
    matchup rate, or blind safety) + the sum of shrunk duo deltas with each ally. Synergy
    tables are fetched from each ally's side (that ally with every champion in my role), so
    one call per ally covers all candidates.
80. **Team-fit reasons use sourced facts only**; drafted tags count after the owner reviews the
    row. "Bad into their comp" waits for a source of matchups across roles.
81. **A draft doesn't repeat OP.GG calls every second**: a call that already ran (worked,
    failed or had no data) isn't resubmitted for 10 minutes. Before this, a failing call was
    retried on every client update and queued behind OP.GG's 1-per-second limit.

## 2026-10-03: M17 (the whole team in plain words)
77. **Kits are Riot's words, never ours.** The main view shortens each ability to Riot's first
    sentence (cut, not reworded); the Both teams panel shows the whole text. The writer gets
    every champion's kit (about 7,400 input tokens, about 1.3 cents a written report).
78. **The class glossary is gone from the writer's prompt**: it held descriptions of our own
    ("kite juggernauts"). Riot's class definitions live in wiki tooltips, not quotable text, so
    the writer gets class names only and describes a class only when an item does.

## 2026-10-03: M16 (players at the loading screen)
75. **Player records come from OP.GG's profile tool at the loading screen**, one call per
    visible player (two at a time, inside OP.GG's politeness throttle). Riot's own API would
    need dozens of match calls per player. Only the record on the champion being played,
    rank, and recent results are kept; the Riot ID is passed to OP.GG and then dropped.
76. **The final written report waits up to 15 s for the records** (in the writer's thread, so
    the rules report shows at once), then gets a "Players" section; records that arrive later
    still show on the dashboard and in the saved report.

## 2026-10-03: M15 (sourced data)
70. **Riot's ratings replace drafted `cc`, `escape`, `frontline`**, as Riot states them
    (1 Low, 2 Moderate, 3 High), not mapped onto the old drafted scale. `escape` 0 is kept for
    one sourced fact (Riot: Low mobility, and the wiki lists no dash or blink), which the
    "no dash" rules rely on. A frontliner is High toughness: Riot rates Samira, Vex and
    Evelynn Moderate, and nobody calls them frontline. Thresholds that used to read "2" for
    frontline now read High (`FRONTLINE_AT = 3`). The drafted values were sometimes plainly
    wrong (Vex and Nautilus were "no escape"; both have dashes).
71. **Mechanics from the LoL Wiki's page categories**, filtered by the wiki's own list of
    "Advanced attributes" read at refresh time (not hard-coded). "Global champion" is not our
    `global` tag: it means any ability with global range (Akali, Draven, Zed are in it).
72. **Sourced values are applied in memory**; champion_traits.csv keeps the drafts (the owner's
    file is never rewritten), and a `source=owner` row beats every source.
73. **OP.GG's game-length swing sets `scaling` per game** (STATS.md, Scaling): the cut-offs
    use the documented 3-point noise level; text quotes OP.GG's two numbers. Early-game kill
    pressure (`early`) has no matching source and stays a drafted note.
74. **Game facts are a cited, hand-kept file** (`data/manual/game_facts.csv`): Riot's patch
    notes first, the wiki where the notes don't say (dragon timers, Herald despawn, current
    role quest rewards, which changed four times in 2026). Shown as static pre-game text,
    never as timers.

## 2026-10-03: M14 (the app without a command line)
64. **One app, two doors.** `sidekick.exe` (pip's no-console launcher) and `scout watch` run the
    same `scout/app/main.py`; `scout watch` also prints to the terminal. Only one copy runs at a
    time (a named Windows lock), so two copies never poll the client or write app.json together.
65. **Your champions live in pool.yaml** (gitignored, next to config.yaml) as `{lane: {champion:
    stars}}`, written by Settings and `scout pool`. Until it exists, config.yaml's old
    `champ_pool` lists are read with 3 stars each, so nothing breaks. Comfort is a preference,
    not a League fact: a more comfortable champion ranks first unless another scores more than
    1 point of win rate per star of difference better (`COMFORT_MARGIN` in `picks.py`; equal
    stars keep the old 1-point tie-break). Tune it if the picks feel too stubborn or too loose.
66. **Updates fast-forward only, then restart through a helper.** `git pull --ff-only` never
    merges or overwrites local edits (if the update touches a file the owner edited, it stops and
    changes nothing). Windows locks the running `sidekick.exe`, so a small hidden helper waits
    for the app to close, reinstalls only if pyproject.toml changed, and reopens it; the app
    then runs `scout refresh --pool` and says what changed. git is told never to prompt on a
    hidden terminal.
67. **An update that changes a data file's columns rebuilds it**: the static data counts as
    complete only when every file's header matches the code's schema, so no manual
    `--force` after an update.
68. **Champion pictures are Data Dragon's square portraits**, downloaded once to
    data/cache/img/champion (refresh fetches missing ones) and handed to the page as data: URIs
    on request: the window has no web server, and the page caches what it got.
69. **The game plan line is about the whole team, so it yields to your own lane**: a laner
    whose lane is losing hears "hold your lane while the rest of the team uses its early edge"
    instead of "press your early advantage", and a laner winning a lane on a slow team hears
    "use your lane lead". (Found 2026-10-02: the plan said press beside "Survive".)

## 2026-10-03: player ids and map side
62. **The League client's player ids aren't the web API's** (Riot's API rejects them: it
    encrypts ids per key). The loading-screen checks go client id -> Riot ID (client, read-only
    `/lol-summoner/v2/summoners/puuid/{id}`) -> web API id (Account-V1). Players whose Riot ID
    can't be read count as hidden and are skipped.
63. **Champ-select team 1 = blue, team 2 = red**, checked against Riot's match data: ranked
    games recorded as team 2 are teamId 200 (red) in Match-V5; blue picks first.

## 2026-10-02: M13 (the app window) and the two phases
59. **The app is a web page in a native window** (pywebview with Windows' Edge engine): charts,
    themes and type sizes are plain HTML/CSS, with no internet needed. The page polls a small
    bridge a few times a second instead of being called from the watcher thread. The old Tk text
    window stays only as a fallback where pywebview is missing.
60. **Two phases (the owner):** champ select shows pick options and a free rules read; the loading
    screen, with roles confirmed, everyone's summoner spells and duos, makes the final report,
    the only one the LLM writes. One call per game, and no written report built on a role guess.
61. **Riot's own words first** (the owner: no conclusions of our own): the opponent's passive and
    Riot's tips against them come straight from Data Dragon and are labelled as Riot's.

## 2026-10-02: M11 (loading-screen addendum)
56. **Duos come from public match history, not the client's party ids.** The loading roster
    has a `teamParticipantId` that groups parties, but the game doesn't show enemy parties, so
    using it would expose obfuscated information (`POLICY.md`). Instead: 2+ of their last 20
    ranked games together, checked on the same team (Match-V5).
57. **One-trick = their champion is their top mastery by 3x the next, or 1M+ points.** It's
    about champion experience, phrased as "far more games on X", never a skill rating.
58. **Identities never leave memory**: puuids are read from the loading roster for the calls and
    dropped; the addendum names champions only; nothing goes to the LLM or a file.

## 2026-10-02: M9b (pick suggestions)
52. **Blind safety score** = own shrunk win rate minus 10 points x the share of the role's 10
    most-played champions that hard-counter it; below 5 known matchups it shows the win rate
    only ("few matchups known yet"). First guess; tune later.
53. **"Strong into auto-attackers" is a trait tag (`anti_auto`), not derived from ability
    text.** Riot's short descriptions are too uneven (Rammus's reflect shows, Jax's dodge and
    Shen's block don't). The tag is in the vocabulary; which champions get it is the owner's call
    (proposed list, not applied).
54. **`scout pool` edits only the pool lines of config.yaml** (text edit, comments kept, then
    re-validated), after a confirm. Mastery comes from a new read-only client endpoint.
55. **Pick options are shown, not chosen**: "Options, not orders" in the text, no auto-lock
    (CLAUDE.md hard rule 1, POLICY.md).

## 2026-10-02: M9 (counter-pick and matchup briefs)
46. **The win rate moves from Your lane into the Counter-pick verdict** ("Elise isn't a special
    counter to Lee Sin (48% over 3,572 games): 1 point worse than both champions' overall
    strength predicts..."), so it's shown once, next to what it means. Your lane keeps OP.GG's
    early-lane labels.
47. **Structural verdicts start from the lane verdict and add one band per signal** (ranged into
    melee, engage into peel); never `specific`. Simple and visible; tune with post-game data.
48. **Jungle gets its own counter-pick advice**: laner advice ("give up CS under tower") doesn't
    fit; the rules check `me.role`.
49. **Counter-pick lines have no subject**, so the report keeps the verdict plus how to play it
    (one-item-per-champion de-duplication would drop the second line).
50. **Matchup briefs start with a verdict word** (`Favored:`/`Even:`/`Unfavored:`) so a draft
    that contradicts OP.GG can be rejected mechanically, and a brief replaces the computed
    timeline in the report (one phase read, not two).
51. **First briefs drafted in a Claude Code session** for the jungle pool (Lee Sin, Elise,
    Amumu) against each one's 5 most-played opponents, from ability text, traits and OP.GG data
    only, gated by the same validator, all `reviewed=n`. No API cost.

## 2026-10-02: M8 (stats from OP.GG)
40. **OP.GG over plain HTTP, not the `mcp` SDK.** The SDK (2.2) validates every tool in
    `tools/list` strictly and rejects OP.GG's list (two Valorant tools declare an array output
    schema), so no call could be made. The protocol is three JSON POSTs (initialize,
    notifications/initialized, the request with `Mcp-Session-Id`), done with httpx in
    `scout/data/opgg.py`. The tool check (hard rule 6) still runs before any call. The `mcp`
    dependency is dropped.
41. **OP.GG champion names come from the display name** (`opgg_name`: capitals, apostrophes,
    periods and "&" dropped, spaces to underscores). Checked live: `WUKONG`, `NUNU_WILLUMP`,
    `RENATA_GLASC`, `KSANTE`, `DR_MUNDO` work; `MONKEY_KING`, `NUNU`, `RENATA` don't (the old
    note in `DATA.md` was wrong). No `lol_list_champions` call needed.
42. **OP.GG's lane-advantage label decides the lane verdict** when the sample is big enough
    (`stats.min_games_display`) and, in bot lane, the ADC and support labels don't point
    opposite ways. The traits verdict is kept; only an opposite verdict (win vs lose) is called a
    disagreement: one warning line in the report and a `stats_disagree` review row.
43. **The report shows the shrunk rate** ("you win 48% over 3,572 games"), the number we judge
    by, so it can differ from OP.GG's site by a point. Thin samples show no number.
44. **The draft never waits on the network for more than `report.fetch_budget_seconds`** (5).
    Calls start as soon as both champions in a lane are known (enemy roles guessed); if some are
    still running at the report, it goes out with a notice and updates once when they land.
    With OP.GG down, the report is the rules report plus one line saying so.
45. **Known off-meta drafts are listed in the role answer-key test**, not tuned away: two
    off-role picks in one draft (Morgana jungle, Tryndamere mid) are unguessable from any role
    rates; the loading-screen check fixes them.

## 2026-10-02: M7 (LLM writer)
36. **Warnings and the owner's notes are printed by code, not written by the model**, so they can't
    be dropped or reworded, and a loading-screen confirmation that changes nothing costs no
    call (the writer's input is unchanged, so its answer is cached).
37. **The rules report always comes first**; the written version replaces it when it's ready
    (a background thread), unless a newer report came in meanwhile.
38. **Length is a soft target set as line limits.** Measured: Haiku 4.5 overshot 120-word
    totals by 40-100%, and retries didn't fix it. Line limits in the prompt got first-try
    passes; only more than 2.5x the target is rejected. Accuracy checks (sources, numbers,
    item and ability names) stay strict.
39. **Spending safety:** Haiku 4.5, a daily call cap (40), capped output, cached drafts, a
    usage log with cost estimates, `scout doctor` shows today's spend; `scout report` only
    calls the model with `--write`, and `scout watch --no-llm` turns it off.

## 2026-10-02: depth pass after the owner's review
34. **The jungle route is an insight, not a rule.** It combines the gank ranking, lane
    volatility and where their jungler goes, which a yes/no rule can't rank (DECISIONS #2);
    `JG-START-SIDE` was removed. Early fights where a lane meets both junglers are a
    computed `skirmishes` insight with rules on top.
35. **Every role sees all three lanes** in one line, so a laner knows where both junglers are
    likely to be and the jungler sees the whole map at a glance. Two sections
    (`lanes_in_trouble`, `jungle`) hold 4 items to make room for it.

## 2026-10-02: M6b (report window)
33. **tkinter window, on by default** (`scout watch --no-window` for terminal only). It ships
    with Python, so nothing to install. The watch loop runs in a background thread and hands
    reports over through a queue. Position, text size and the always-on-top choice are kept
    in `data/cache/window.json`; a position on an unplugged monitor falls back to the main one.
    A new report brings the window to the front for a moment without taking keyboard focus.

## 2026-10-02: M6 (live watch)
31. **Events only wake the watcher; state is always read with GETs.** One code path whether
    the WebSocket works or not, and the recorder sees exactly what the watcher saw.
32. **One report file per champ select**, overwritten on re-renders and deleted on a dodge,
    so `reports/` only holds games that happened.

## 2026-10-02: M5 (analysis, rules, report)
27. **The selector caps items per section, not words.** Rule texts are full sentences written
    for the writer to condense; trimming them to 120 words before the writer would leave three
    items. The word budget applies to the writer's output (M7); the deterministic report shows
    the selected items as they are.
28. **Report-time trait loading checks structure only.** The content checks (numbers must appear
    in the ability text, no item names) run when rows are written (draft-traits, review). A
    patch that rewords ability text must not stop every report; it already queues the champion
    for review.
29. **Golden tests use a frozen copy of the traits** (`tests/fixtures/static/<version>/`), so
    the owner's reviews change their reports but not the test expectations. Re-copy on purpose.
30. **One item per champion per section** (deduplicated by subject), and the enemy-jungler
    insight only adds what the style rules don't say. Rules that advised about the jungler
    before the jungle plan existed (`LANE-LOSING`'s "ask for cover rather than a gank") now
    leave that to the `LANER-*` plan rules, which they could contradict otherwise.

## 2026-10-02: plan changes after the first recording
24. **Enemy roles are confirmed at the loading screen** (moved from optional M11 into M6). The
    report appears at the end of champ select with the guess, then re-renders once with the
    roster the game shows (Smite marks the jungler). Why: the guess can be wrong, and the
    loading screen is pre-game information Riot shows anyway.
25. **Pick suggestions are part of v1** (new M9b, after the counter-pick logic it reuses),
    not an optional extra. Why: the most useful thing a champ pool can do.
26. **A report window is part of v1** (new M6b, right after the test version). Why: The owner
    wants it on a second monitor, and pick suggestions update during the draft.

## 2026-10-02: M1 (client connection and recorder)
18. **Pinned certificate, one check relaxed.** Python 3.13's default `VERIFY_X509_STRICT`
    rejects the client's certificate ("Missing Authority Key Identifier", checked live). We turn
    off strict mode only; the chain to Riot's root and the hostname `127.0.0.1` (listed in the
    certificate) are verified. Certificate failures are reported, never retried.
19. **Endpoint allowlist in code** (`ENDPOINTS` in `lcu/client.py`), tested against `LCU.md`
    section 2. Why: read only what we need, and the Riot registration lists our endpoints.
20. **Recorder keeps an allowlisted slice of the gameflow session** instead of scrubbing it.
    Why: it holds server addresses, dodger ids and, at the loading screen, every player's
    identity; champ select tests need only phase, queue and dodge state. Champ select sessions
    are scrubbed by key, plus a safety net that blanks any long token-like string.
21. **Recordings: draft queues only by default, deduplicated ignoring timer ticks and skins,
    numeric champion id in file names until M2.** Why: files small enough to commit every game,
    no ARAM noise, no static-data dependency in M1.
22. **Every recording carries an answer key for enemy roles**: the roster the game shows at
    loading (champion, position, summoner spells; no identities). Why: enemy roles are the one
    thing champ select hides that every report depends on, and without the real answer the
    90% accuracy target in `SPEC.md` couldn't be measured until M10.
23. **No setup questions; the champ pool is optional.** Your role comes from champ select and
    the report works for any champion. The pool only speeds things up (nightly stats) and seeds
    pick suggestions; when it's empty, those use your own most-played champions per role
    (your champion mastery or recent games, which is your own data). Why: filled games and
    off-pool picks must work with zero input.

## 2026-10-02: planning pass before M1
1. **Code decides, the LLM only writes** (kept from v0). Analysis is deterministic and tested;
   the writer turns pre-selected items into text. Why: traceable, testable, no invented facts.
2. **Rankings are Python insights, advice text is YAML rules.** Best gank, jungle threat, feed
   threats and lane state are computed with reasons; rules read them. Why: the prototype's
   "Gank first" had no input because yes/no rules can't rank.
3. **Rules carry `section`, `audience` (role list), `priority`, and inline `tests`.** Why: makes
   every role's report deterministic in structure and guarantees every rule is tested.
4. **All five roles are first-class** (`ROLES.md`). Why: the prototype gave supports and ADCs an
   empty report and laners no jungle information.
5. **Static data: Data Dragon + CommunityDragon + LoL wiki; Meraki dropped.** Meraki stopped
   updating (champions last changed 2025-08, missing new champions). Data Dragon's attack range
   misclassifies some champions' melee/ranged; CommunityDragon and the wiki get them right.
6. **Stats source: the OP.GG MCP server**, discovered at runtime. U.GG, Lolalytics and
   Mobalytics forbid reuse; DraftGap's data is scraped from Lolalytics, so we reuse its math,
   not its data. Our own Match-V5 numbers are an optional later supplement.
7. **Shrink matchup rates toward the expected result; label counters by delta.** Why: 300 games
   is +-5.7 points, wider than the old severity bands, and raw win rate mixes "countered" with
   "weak champion this patch" (`STATS.md`).
8. **Storage: static and manual data as CSV, stats in SQLite** (`data/generated/stats.sqlite`).
   Why: static and manual data are small and worth reading by eye; stats need upserts, history
   across patches, and safe writes while `scout watch` and a scheduled refresh both run.
9. **Writer returns structured JSON with sources per line; code renders.** Numbers are
   pre-formatted strings the writer copies. Why: the old "every number appears in the input"
   check would fail on rounding, and inline rule IDs cluttered the text.
10. **No `temperature` in config.** Sonnet 5.5 and Opus 5.5 reject it; Haiku 4.5 rejects
    `effort`. Default model stays Haiku 4.5.
11. **Own small LCU client** (httpx + websockets + psutil), pinned Riot certificate. `lcu-driver`
    and `willump` are dormant; WMIC is gone from Windows 11 24H2.
12. **Recorder first, live client before stats** (milestone order). Every game played becomes a
    fixture, and the test version (M6) works on rules alone.
13. **Runs on Windows; develop anywhere.** Live commands need Windows Python (WSL's default NAT
    networking can't reach the client). LF line endings enforced by `.gitattributes`.
14. **Naming**: repo `sidekick`, Python package and CLI `scout`.
15. **Personal data stays out of git**: `data/generated/`, `data/cache/`, `data/history/`,
    `reports/`, `config.yaml`, `.env` are gitignored. Recorded fixtures are scrubbed.
16. **Four knowledge layers** (`KNOWLEDGE.md`): Riot ability text (generated), champion briefs
    and matchup briefs (drafted, the owner-reviewed, in `data/manual/`), and matchup data (OP.GG).
    Why: the report has to explain abilities, ults that join other lanes, spikes, trade windows
    and jungle asks without the writer relying on memory. Drafting the first full pass in Claude
    Code sessions avoids API cost.
17. **Laners get a jungle plan** (`ask_gank`, `ask_cover`, `self_sufficient`, `danger`) and a
    lane timeline by phase, both computed insights.
