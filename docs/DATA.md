# DATA: sources, storage, and keeping it up to date

Four kinds of data:
- **Static facts** (champion list, ids, abilities, cooldowns, melee/ranged, damage type, class):
  change only with a patch. Pulled automatically per Data Dragon version.
- **Stats** (win/pick/ban/role rates, matchups, synergies, game-length win rates): change daily.
  Pulled automatically, kept per patch with history. How we use them: `STATS.md`.
- **Judgment** (champion traits, matchup notes, overrides): hand-owned in `data/manual/`,
  flagged for review when a patch or the stats suggest they're off. See `TRAITS.md`.
- **History** (post-game results, M10; the backtest, M20): machine-written on each PC. The
  post-game results are append-only and can't be rebuilt; the backtest is rewritten each refresh.

Sample responses from every source are recorded in `tests/fixtures/sources/` (see its README).
Build and test parsers against those; never against the live network in tests.

## Sources
| Source | What we take | Auth | Status (2026-10) |
|---|---|---|---|
| **Data Dragon** (Riot's static CDN) | version list, champion id/key/name, abilities and cooldowns, Riot's tips, summoner spell ids, item names, costs and build depth, champion pictures | none | current (16.19.1) |
| **CommunityDragon** (community mirror of game files) | melee/ranged, damage type, Riot's 1-3 playstyle ratings, difficulty | none | current |
| **LoL wiki** `Module:ChampionData`, page categories, patch pages | Riot subclass (Diver, Catcher, ...), positions, base attack range and move speed, last-changed patch, cross-checks; mechanics (knock-up, dash...); a patch page's mid-patch updates (`scout/data/patch_updates.py`) | none, CC BY-SA 3.0 | current |
| **OP.GG MCP server** | lane stats and role rates, full matchup tables, lane-advantage labels, builds, synergies, game-length win rates, players' records at loading (M16) | none | current, unofficial; tool names change |
| **Riot static docs** | queue ids | none | current |
| **Riot API** (M10+): Match-V5, Champion-Mastery-V4, Account-V1, Status-V4 | the owner's own matches (post-game), loading-screen duos and one-tricks (M11), the key check | personal key in `.env` | current |
| **Riot match data** (M19): League-EXP-V4 ladder pages, Match-V5 matches and timelines | Emerald+ ranked solo games, measured per champion and role (`scout/data/measure.py`, `scout/data/collector.py`); totals per champion-role plus one small record per game for the backtest (M20), no ids | personal key in `.env` | the current and previous patch |
| **League client (LCU)** | champ select session, who's logged in, region, recent games, mastery | local token | see `LCU.md` |
| **Riot's patch notes and the LoL Wiki, by research prompt** | kit changes per patch, objective and camp timers, role quests, Riot's class descriptions (`research/`) | none | each patch, by a person (`PATCH_UPDATE.md`) |
| **GitHub** | new versions of Sidekick (the app's update check) | none (public repo) | at start and every 6 hours |
| **Anthropic API** | the written report (`REPORT_AGENT.md`) | key in `.env` | each final report |
| ~~Meraki Analytics~~ | dropped: stopped updating (last champion change 2025-08, role rates stuck at 16.3) | | stale |

Not allowed (terms forbid reuse or scraping): U.GG, Lolalytics, Mobalytics, and DraftGap's
dataset (scraped from Lolalytics).

### Data Dragon
- `https://ddragon.leagueoflegends.com/api/versions.json`: newest first. Store the full version
  (`16.19.1`).
- `.../cdn/<version>/data/en_US/championFull.json`: every champion with spells, in one request.
  `data.<Id>.id` ("LeeSin"), `.key` (a **string** "64" = LCU `championId`), `.name`,
  `spells[].cooldown` (length = `maxrank`), `spells[].description`, `passive.description`,
  `allytips` / `enemytips` (Riot's tips; a tip Riot's data splits around a keyword is joined
  back).
- `.../data/en_US/summoner.json`: summoner spells by numeric `key` (Smite is `11`). Names repeat
  across modes, so map by `key` and keep only spells whose `modes` include `CLASSIC`.
- `.../data/en_US/item.json`: item ids and names, so item ids from OP.GG builds can be shown by
  name; total gold, build `depth` and the `Boots` tag (a finished item is depth 3, boots
  excluded: the collector's first item). Keep items available on Summoner's Rift
  (`maps["11"]` true) that are purchasable (254 of 870 in 16.19.1). Item names repeat across
  variants; always key by item id.
- Traps: spell tooltips contain unfilled `{{ }}` placeholders (use `description`, strip HTML);
  `stats.attackrange` misclassifies melee/ranged (Gnar 175 and Jayce 125 are ranged, Lillia 325
  and Rakan 300 are melee); per-level stats are unreliable (16.19.1 has
  `attackdamageperlevel: 0` for every champion), so we don't use base stats; mode-specific
  `Jade_*` champions exist and are filtered out. Data Dragon can update a day or two before or
  after the patch goes live.

### CommunityDragon
- Read from the folder for the current patch (`https://raw.communitydragon.org/16.19/...`), not
  `latest/`, so it matches Data Dragon; fall back to `latest/` (with a warning) if the folder
  doesn't exist yet.
- `.../plugins/rcp-be-lol-game-data/global/default/v1/champions/<key>.json`, one per Data Dragon
  champion key (173 requests per new version, 6 at a time, cached): `tacticalInfo.attackType` (`melee|ranged`),
  `tacticalInfo.damageType` (`kPhysical|kMagic|kMixed`), `tacticalInfo.difficulty` (1-3),
  `playstyleInfo.{damage,durability,crowdControl,mobility,utility}` (1-3, Riot's own ratings).
  Cooldown arrays here are padded to 6; truncate with Data Dragon's `maxrank`.
- `<folder>/content-metadata.json` shows which game build the folder holds (and 404s for a
  folder that doesn't exist).
- `champion-summary.json` (`id`, `alias`, filter `0 < id < 60000`) isn't needed: the per-champion
  files are fetched by Data Dragon key. Kept as a fixture for reference.

### LoL wiki
- `https://wiki.leagueoflegends.com/en-us/Module:ChampionData/data?action=raw`: one Lua table,
  keyed by display name. Fields: `apiname` (= Data Dragon id), `role` (list of Riot
  **subclasses**, the only source for these), `rangetype`, `adaptivetype`, `client_positions`,
  `external_positions`, `changes` (last patch the champion changed, like `V26.12`, in-game
  numbering), and the same 1-3 ratings as CommunityDragon.
- Entries that aren't Data Dragon champions are ignored (`Mega Gnar`, apiname `GnarBig`); for
  duplicates (`Kled & Skaarl` next to `Kled`) the first one wins.
- Parsed as data by a small reader (`scout/data/wiki.py`), never executed. It handles comments
  and plain number arithmetic (Kled's `hp_lvl = 84+1000/17`).
- Labels seen (16.19): positions `Top, Jungle, Middle, Bottom, Support`; 13 subclasses
  (`marksman, assassin, diver, skirmisher, burst, vanguard, juggernaut, specialist, enchanter,
  battlemage, catcher, artillery, warden`). Unknown position labels are logged, not guessed.
- `adaptivetype` is the adaptive-force type, **not** the damage type (Leona and Thresh are
  `Physical` there). Only a fallback for `damage_type` when CommunityDragon lacks a champion.
- The wiki is edited by volunteers and can lag a patch by a few days: re-pull it 3 days after
  a new version.

### OP.GG MCP server
- Endpoint `https://mcp-api.op.gg/mcp` (Streamable HTTP; responses are plain JSON with an
  `Mcp-Session-Id` header). Code: github.com/opgginc/opgg-mcp. Spoken over plain HTTP with
  httpx (`scout/data/opgg.py`): the `mcp` SDK rejects OP.GG's tool list (DECISIONS.md #40).
- **Call `tools/list` on connect and fail loudly if a tool or required parameter we use is
  missing** (CLAUDE.md hard rule 6). The tool list has already drifted from its README.
- Output is always `result.content[0].text`. Two formats:
  - Tools with `desired_output_fields` return a **compact class format**: `class X: f1,f2,...`
    header lines, then `X(v1,v2,...)` values. Rates are rounded to 2 decimals. Parse **by
    header**, never by position: field order differs from the schema, class names repeat across
    sibling lists (all five lanes come back as `Top(...)`), and which list is which lane comes
    only from the order in `class Positions`.
  - `lol_get_lane_matchup_guide` returns plain JSON at full precision.
- Errors: an unknown champion returns HTTP 200 with a JSON-RPC `error` (`-32600`), not `isError`.
- Champion arguments are the display name in capitals, apostrophes, periods and "&" dropped,
  spaces as underscores: `LEE_SIN`, `KAISA`, `DR_MUNDO`, `NUNU_WILLUMP`, `WUKONG` (not
  `MONKEY_KING`). Stored as `opgg_name` in `champion_meta.csv`. Answers name champions by
  display name (lane meta) or League key (`champion_id` in matchup tables and synergies).
- An unknown name and "no data for this champion in this lane" give the same `-32600` error:
  treated as no data, not an outage.
- Positions are `top, jungle, mid, adc, support` (`adc` = our `bot`).
- No rate-limit headers; calls take about 2-5 s each.

The tools we use:
| Tool | Args | Gives | Calls |
|---|---|---|---|
| `lol_list_lane_meta_champions` | `position=all`, `desired_output_fields` | per lane, every champion above a play threshold: `play`, `win`, `win_rate`, `pick_rate`, **`role_rate`**, `ban_rate`, `tier` (1 = OP ... 5 = weak). About 270 rows | 1 per stats refresh (when 24+ hours old) |
| `lol_get_lane_matchup_guide` | `position`, `my_champion`, `opponent_champion` | **`data.counters[]`: my champion's full matchup table for that lane** (`play`, `win` per opponent); `game_lengths[]` (my champion's win rate at 0/25/30/35/40 min, no game counts); pair labels `lane_advantage_champion`, `lane_solo_kill_advantage_champion`, `recommended_play_style`; `opponent_champion_tip`; build arrays (items, runes, spells with play/win counts, filtered to this matchup; exact fields confirmed against an untrimmed response in M8); `trends[].version` (OP.GG's patch, e.g. `16.19`) | 1 per (champion, lane), on demand and at each `--pool` refresh |
| `lol_get_champion_synergies` | `champion`, `my_position`, `synergy_position`, `desired_output_fields` | top 10 partners by games: `play`, `win_rate`, tier | on demand |
| `lol_get_summoner_profile` | `game_name`, `tag_line`, `region`, `desired_output_fields` | one player's solo rank, ranked games, wins and average kills/deaths/assists per champion, recent champions (M16) | 1 per visible player at the loading screen, when `report.player_records` is on |
| `lol_get_champion_analysis` | `game_mode=ranked`, `champion`, `position`, `tier`, `desired_output_fields` | per-champion summary, top-3 counters only, `damage_type`, `skill_combos` | optional cross-check only |
| `lol_list_champions` | | `champion_id` (key), `key` (Data Dragon id), `name` | not used (names follow the rule above) |

Limits we have to live with:
- **No patch parameter** anywhere, and lane meta and synergies don't say which patch they cover.
  See "Patch rollover" below.
- **Rank filter**: lane meta, matchup guide and synergies have no tier parameter. Champion
  analysis takes `tier` but silently ignores values it doesn't know (`emerald_plus` returned the
  same numbers as no tier; `challenger` worked). v1 stores everything as
  `rank_filter = opgg_default`. A tier only counts as applied if the game count changed.
- **No gold-difference-at-15** or other early-lead numbers in any stats tool. Early lane state
  comes from the lane-advantage labels plus traits, whose `early` is our own measured gold at
  10 once the collector has 50+ games (M19, Riot match data above).

## Storage layout
`data/manual/` is in the repo (and inside the installed app). Everything else is in each
user's own Sidekick folder, `%LOCALAPPDATA%\Sidekick` (`scout/paths.py`, DECISIONS #113), with
the same subfolders, plus `matchup_notes.csv` ("Your notes") and `recordings/`.
```
data/
  manual/                          # hand-owned, committed (TRAITS.md)
    champion_traits.csv  matchup_briefs.csv  champion_overrides.csv
    game_facts.csv                 # cited timers and role quests (docs/PATCH_UPDATE.md)
    class_definitions.csv          # Riot's own words for each class (research, M19)
  generated/                       # machine-owned, gitignored, safe to delete and rebuild
    PATCH                          # current Data Dragon version, one line
    REFRESH_LOG.md                 # one entry per refresh: what changed, what failed
    review_queue.csv
    patch_updates.json             # the wiki patch page's mid-patch updates (research PC, M21)
    static/<ddragon_version>/      # one folder per version; keep the last 3
      champions.csv  abilities.csv  champion_meta.csv  summoner_spells.csv  items.csv  tips.csv
      manifest.json
    stats.sqlite                   # all stats, every patch, with fetch times
  cache/<source>/<version>/        # raw responses, gitignored; keep the last 3 versions
  cache/img/champion/<id>.png      # Data Dragon square portraits for the app (M14)
  cache/app.json  cache/update.json  # window size and position; an update in progress
  cache/refreshed                  # touched after each refresh the app runs (its 6-hour clock)
  history/                         # M10, machine-written, gitignored
    postgame.csv                   # one row per graded claim: predicted, actual, the measure
                                   # (append-only, not rebuildable)
    rule_accuracy.csv              # hit rates per claim kind, lane label and rule (rebuilt)
    backtest.csv                   # each call's record on the stored games (M20, rewritten)
```
Deleting `stats.sqlite` is safe but loses previous-patch history used for early-patch blending
(OP.GG doesn't serve old patches), and the measured match data and stored games (the collector
starts over).

## Static file schemas (`scout/data/schemas.py` is the source of truth)
**`champions.csv`**: `champ_id, key, name, ddragon_version`

**`abilities.csv`**: `champ_id, slot (P|Q|W|E|R), name, max_rank, cooldowns (pipe-separated per
rank), description (HTML stripped), description_hash (sha1 of description + cooldowns),
ddragon_version`

**`champion_meta.csv`**: `champ_id, range_type (melee|ranged), attack_range and move_speed (base
values from the wiki's `stats.range` / `stats.ms`; Gnar, Jayce and other form-changers have a
melee base range though their range type is ranged), damage_type
(physical|magic|mixed), classes (Riot subclasses, pipe-separated, lowercase snake_case),
legacy_tags, positions (wiki client + external, pipe-separated roles), client_positions
(Riot's in-client positions only, usually the main role; weighted double in the role prior
until OP.GG role rates exist), rating_damage,
rating_durability, rating_cc, rating_mobility, rating_utility, difficulty, mechanics (the LoL
Wiki's page categories that are "Advanced attributes", lowercase: `knockup|dash|stealth`; the
list of attributes is read from the wiki at refresh time), last_changed_patch, opgg_name,
field_sources (e.g. range_type:cdragon|classes:wiki|mechanics:wiki), ddragon_version`

**`summoner_spells.csv`**: `key, spell_id, name` (CLASSIC mode only)

**`items.csv`**: `item_id, name, gold_total, depth (Riot's build depth; 3 = finished), boots
(y/n), ddragon_version` (Summoner's Rift, purchasable)

**`tips.csv`**: `champ_id, kind (ally = playing as, enemy = playing against), n, text,
ddragon_version` (Data Dragon `allytips` / `enemytips`)

**`review_queue.csv`**: `champ_id, reason, details, patch_detected, created_at, resolved (y/n), resolved_at`.
Reasons: `new_champion`, `abilities_changed`, `patch_changed`, `traits_missing`,
`traits_unreviewed`, `class_missing`, `source_disagreement`, `stats_disagree`, `patch_notes`,
`brief_stale` (a matchup brief whose champion changed or whose stats flipped, see `KNOWLEDGE.md`).

**`manifest.json`** (per static version): build time, per source: URL, fetch time, row count,
warnings; cross-source disagreements found.

## Stats database (`data/generated/stats.sqlite`)
Every OP.GG table stores **wins and games, not just a rate** (OP.GG's compact format rounds rates
to 2 decimals), plus `patch` (OP.GG's label, Data Dragon major.minor, e.g. `16.19`),
`rank_filter`, `source`, and `fetched_at`. Upserts replace a row for the same key.
| table | key | other columns |
|---|---|---|
| `lane_stats` | patch, rank_filter, role, champ_id | games, wins, pick_rate, role_rate, ban_rate, tier |
| `matchups` | patch, rank_filter, role, champ_id, opp_champ_id | games, wins (from champ_id's side) |
| `matchup_labels` | patch, role, champ_id, opp_champ_id | lane_advantage (`us|them|even`), solo_kill_advantage, play_style, tip |
| `synergies` | patch, rank_filter, champ_id, role, ally_champ_id, ally_role | games, wins, tier |
| `game_length` | patch, rank_filter, role, champ_id, minute | win_rate (no game counts available) |
| `matchup_builds` | patch, role, champ_id, opp_champ_id, kind, rank | item_ids or rune/spell ids, games, wins (kind: `core`, `boots`, `starter`, `runes`, `spells`) |
| `fetch_log` | id | source, tool, args, fetched_at, ok, error, elapsed_ms, format_fingerprint, patch_seen |
| `measured` (M19) | patch, champ_id, role, metric | n, total, total_sq (sums: the mean is total / n); Riot match data, per champion-role, no ids |
| `collected` (M19) | game_hash | patch, collected_at: each game counted once, known only by a one-way hash |
| `games` (M20) | game_hash | patch, record: each side's draft and what happened, for the backtest |
| `collector_state` | key | value (where the collector is on Riot's ladder) |
Role rates for enemy role inference come from `lane_stats.role_rate`. A champion missing from a
lane means it's below OP.GG's threshold there: use the floor value.

## The refresh pipeline (`scout refresh`)
Modes: `scout refresh` (do whatever is stale), `--static`, `--stats`, `--pool`
(matchup tables for everyone's champions; the app runs `--pool` every 6 hours), `--force`,
`--prune`.
1. **Version check**: read Data Dragon `versions.json`. New version, `--force`, a static
   file whose columns no longer match `schemas.py` (an app update changed it), or the one-time
   wiki re-pull 3 days after the version was first built: run the static build (steps 2-5).
   Otherwise skip to step 6. Then download any missing champion pictures
   (Data Dragon `cdn/<version>/img/champion/<id>.png`) for the app.
2. **Pull** `championFull.json`, `summoner.json`, `item.json`, CommunityDragon per-champion
   files, the wiki module and each champion's wiki categories (mechanics). Raw responses go to
   `data/cache/<source>/<version>/`.
3. **Build** the static CSVs into `static/<version>/` (`scout/data/static.py`). Each
   `champion_meta` field comes from its preferred source with a fallback, recorded in
   `field_sources`; `champion_overrides.csv` wins over all. Cross-check melee/ranged between
   CommunityDragon and the wiki, and champion keys across all three; log disagreements as
   `source_disagreement` (none on 16.19.1).
4. **Diff** against the previous version: new champions -> `new_champion` (`scout
   draft-traits` drafts their traits row, M3); changed `description_hash` ->
   `abilities_changed` (list the slots); wiki `changes` equal to the new patch ->
   `patch_changed`; champions with no traits row -> `traits_missing`. `abilities_changed` and
   `patch_changed` are only queued for champions that have traits (otherwise
   `traits_missing` already covers them). Open entries are never duplicated.
5. **Validate**: schemas, champion id, key and name non-empty, every LCU `key` unique, every
   champion has abilities, summoner spells present. If validation fails, keep the previous
   version as `PATCH` and log why. A champion missing from CommunityDragon or the wiki (common
   for a day or two after a release) is a warning with fallbacks, not a failure.
6. **Stats** (if older than `stats.max_age_hours`, `--stats` or `--force`): one `lane_meta`
   call -> `lane_stats`, plus one matchup guide to learn OP.GG's patch (Patch rollover below).
   Then matchup briefs whose champion changed or whose OP.GG lane label now disagrees are
   queued as `brief_stale`.
7. **Pool** (`--pool`: the app's refresh every 6 hours and after each update; skipped if an
   earlier step failed): a matchup guide for each champion on every account's list and in
   pool.yaml (per role) against its lane's most-played opponents, filling `matchups`,
   `matchup_labels`, `game_length`, `matchup_builds`.
8. **Log** an entry in `REFRESH_LOG.md`: versions, counts, review queue additions, per-source
   failures, stale datasets. `--prune` drops static and cache folders beyond the last 3 versions.
9. **Backtest** (M20, offline): grade every call on the stored games and rewrite
   `data/history/backtest.csv`; the writer gets each call's record from it.
10. **Research upkeep** (M21, only on the owner's PC, `owner: true`): read the section
    titles of the LoL Wiki's page for the patch into `patch_updates.json` (mid-patch updates),
    then rewrite the prompts in `research/` whose text changed (`PATCH_UPDATE.md`).
11. **Never touch `data/manual/`.**

`--static` stops after step 5 and the pictures; `--stats` skips steps 1-5.

## Keeping data current over time
| Data | Changes | Refreshed by | Max age before refresh |
|---|---|---|---|
| Static facts | each patch (every ~2 weeks) | the app's refresh every 6 hours while it's open and idle, the Refresh data button, after each update; wiki re-pulled 3 days after a new version | until the next version |
| Lane stats + role rates | daily | each refresh; at app start if stale (in the background) | `stats.max_age_hours` (24) |
| Full matchup tables | daily | each refresh for every account's champions; during each draft for the lanes in that game | 72 h |
| Measured match data (M19) | each patch | the collector, continuously while the app is idle | the current and previous patch |
| Pair labels, synergies | daily | during each draft (labels also come with each refresh's matchup tables) | 72 h |
| Matchup builds | daily | with every matchup guide: during each draft, each lane in both directions; each refresh's matchup tables | 72 h |
| Traits, briefs, notes | when the owner edits them | `scout review`; stale ones queued automatically | never automatic |

**During a draft** (`scout watch`, M8, `scout/data/stats_service.py`): as soon as an ally locks
a champion and the enemy in that role is known (or likely, from role inference), queue a matchup
guide call for (ally champion, enemy champion, role). Each call returns that ally's full matchup
table plus the pair's lane labels, so five calls cover every lane. Each enemy's guide into its
lane opponent comes too, mine first (their usual build, and their win rate by game length, so
`scaling` is OP.GG's for all ten champions), and one call per team gets the ADC's support
synergies. While I'm still picking, each pick option gets its own guide (against my locked
opponent, or the role's most-played champion), and each locked ally's synergies with my role.
Anything fetched within `stats.matchup_max_age_hours` isn't fetched again. At most 2 calls run at
once, 1 s apart. When picks lock, the report waits at most `report.fetch_budget_seconds`
(default 5) for calls still running; if some are still out, it says so and updates once when
they land (before the game starts). At the loading screen, corrected roles get their own calls.
`scout report --fetch` does the same for a saved game.

**Patch rollover**: Data Dragon, CommunityDragon, the wiki and OP.GG don't switch patches at the
same moment, and OP.GG's lane meta doesn't say which patch it covers. So:
- Every matchup guide response carries `trends[].version`; the newest one is OP.GG's current
  patch. A stats refresh starts with one guide call to learn it.
- Lane meta and synergy rows are stored under that OP.GG patch, not under Data Dragon's.
- Until OP.GG's patch equals the new Data Dragon patch, its numbers count as previous-patch data
  for blending and labels (`STATS.md` rule 3).

**Format drift**: every parser checks the headers or fields it expects. On a mismatch, that
dataset fails loudly (clear message in the terminal and `REFRESH_LOG.md`), the previous data
stays in place, and reports say the stats are stale. Each fetch stores a
`format_fingerprint` (the sorted field names) in `fetch_log`, so the log shows exactly when a
source changed shape. Fixing it means re-recording the fixture in `tests/fixtures/sources/` and
updating the parser.

**Scheduling**: the app runs `scout refresh --pool` by itself while it's open: it looks every 5
minutes (`REFRESH_CHECK_S` in `scout/app/main.py`) and refreshes once the last try is 6 hours
old (`REFRESH_EVERY_S`; the time of the last try is the file `data/cache/refreshed`), no other
job is running, and the client isn't in champ select, at the loading screen or in a game
(phases `ChampSelect`, `GameStart`, `InProgress`, `Reconnect`: `Watcher.idle`, whether or not
the app followed that game). The match data collector and the GitHub update check wait for
those phases too. A Windows scheduled task can run the refresh when the app is closed
(`README.md`). The session also refreshes stale lane stats (role rates) at start in a
background thread without blocking the draft. `--pool` fetches each champion's guide (every
account's lists) against its role's 5 most-played opponents. The full schedule of what updates
when: `PATCH_UPDATE.md`.

## Being a polite client
Cache everything per version. At most 1 OP.GG call per second (`stats.opgg_min_interval_s`) and
2 at once, a timeout on every call, and only fetch what a report or the champ pool needs. A
full refresh is about 1 lane-meta call plus a few dozen matchup guides (the backtest's
`--fetch` is the exception: a few hundred guides the first time, then only what new games need).

## Failure modes and fallbacks
- A source is down: keep the previous data, log it, carry on. Reports still work with
  rules and traits only, plus a one-line notice.
- A new champion before `scout refresh` has run: a placeholder with a warning; nothing crashes.
- Early in a patch (thin samples): blend the previous patch, labeled (`STATS.md`).
