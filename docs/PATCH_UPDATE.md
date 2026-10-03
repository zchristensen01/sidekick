# PATCH_UPDATE: where every piece of data comes from, how it stays current, what needs a person

League changes about every two weeks. This file lists everything Sidekick knows, where each
piece comes from, what the app keeps current by itself (and how often), and what still needs a
person: The owner, or an agent given a prompt from `research/`. Read it at each new patch; an agent
can follow it top to bottom.

## In short
- **The app keeps itself current while it's open.** Every 6 hours, when you're not in champ
  select, at the loading screen or in a game, it runs the same refresh as the Refresh data
  button: a new patch's champion data, OP.GG's numbers, matchup tables for everyone's
  champions, the backtest. It measures
  Riot's match data in the background the whole time it's idle. It checks GitHub for a new
  version of Sidekick at start and every 6 hours. Nobody needs the command line for any of it.
- **Research prompts** cover what only exists as words on a page (which kits a patch changed,
  objective timers, role quests, Riot's class descriptions). After a new patch, or a mid-patch
  hotfix, the top bar shows "Research due" on the owner's PC (`owner: true` in config.yaml;
  everyone else has `owner: false` and never sees it). The prompts write themselves for what's
  due (the patch filled in; after a hotfix, only that update), so they're sent as they are.
  The owner runs them, applies the results, and commits; everyone else gets them with the next
  update.
- **The owner, now and then**: reviewing the drafted champion notes and matchup briefs that a kit
  change flagged (`scout review`). Each person's champion lists are their own.

## What updates by itself, and how often
| What | How often | Notes |
|---|---|---|
| Sidekick itself (GitHub) | checked at start, then every 6 hours (put off during champ select or a game) | "Update available" in the top bar shows what's new; "Update and restart" updates, restarts and refreshes the data (not during a game) |
| New patch: Riot's champions, abilities, tips, ratings, items, spells, pictures | the app's refresh, every 6 hours while it's open (and after each update, and with the Refresh data button) | noticed from Data Dragon's version list; a new patch's data is used from the next game |
| The LoL Wiki's champion data and mechanics | with the new patch, then once more 3 days later | the wiki can lag a patch by a few days |
| OP.GG's lane stats and role rates | when older than 24 hours (each refresh, and at app start in the background) | |
| OP.GG's matchup tables, labels, synergies, builds | during each draft for the lanes in it; each refresh for every account's champions (all but synergies); kept 72 hours | |
| Measured match data (Riot's Emerald+ games) | continuously while the app is idle (about 35 games every 2 minutes); pauses in champ select, at the loading screen, in games, and while a refresh or update runs | needs a Riot key; a new patch starts fresh, last patch's figures stand in until 50 games |
| "Changed since last patch" flags | as the measured data comes in | a figure must move by more than 3 standard errors, with 50+ games on both patches |
| The backtest (each call's track record) | each refresh | offline; `scout backtest --fetch` also gets OP.GG's numbers the stored games need |
| Mid-patch updates (hotfixes) | each refresh, on the owner's PC | read from the LoL Wiki's page for the patch (V26.19); a new one makes the patch notes research due again |
| The research prompts | each refresh and each applied reply, on the owner's PC | rewritten for what's due now, only when their text changes |
| Research due | worked out every minute | goes away as soon as the results are applied, and for everyone once the owner's commit reaches them |
| The review queue | each refresh and each game | `data/generated/review_queue.csv` |

Optional, for when the app is closed: a Windows scheduled task running `scout refresh --pool`
(README, "Refresh while the app is closed").

## When things come out, and how Sidekick notices
- **A new patch** comes out about every two weeks. Riot's patch notes go up around patch day
  (www.leagueoflegends.com, Game Updates). Data Dragon (Riot's data download) usually has the
  new version within a day; the app refreshes once its last refresh is 6 hours old (it looks
  every 5 minutes), so it has the new champion data within 6 hours while it's open, or a few
  minutes after opening if the last refresh is older than that, and "Research due" appears for
  the owner.
- **OP.GG** needs a few days of games on a new patch. Until its numbers cover the new patch,
  last patch's numbers are blended in (`STATS.md` rule 3).
- **Measured figures** (gold at 10, lane push, level 3 and 4 times, first item, roaming) restart
  each patch, by Riot's own patch number (not OP.GG's, so they count while OP.GG catches up).
  Last patch's stand in until a champion-role has 50 games. Then the two patches
  are compared and real changes are flagged ("reaches level 4 nine seconds sooner than patch
  16.18"). **Jungle clear times** are measured this way (time to level 4 is a full clear), so a
  patch that speeds up a jungler's clear shows up in our own numbers. No outside page is needed
  or watched, and no outside clear-time list exists that we'd trust more than Riot's own games.
- **Mid-patch hotfixes** (balance changes between patches) don't change Data Dragon's version.
  The LoL Wiki lists them on the patch's page (https://wiki.leagueoflegends.com/en-us/V26.19)
  after the patch's own notes, as "Hotfixes" with dated entries ("May 14th Hotfix") or one-off
  sections ("October 2nd Queue Update"). Each refresh on the owner's PC reads that page's
  section titles (`data/generated/patch_updates.json`); when the patch
  notes research is applied, `research/status.csv` records the updates it covered, and a new
  one makes the patch notes research due again, with a prompt about that update only. The wiki
  lists a hotfix once its editors add it, so it can trail Riot's post; the measured figures
  catch the effect either way.

## Research: what the app can't get by itself
| Prompt (`research/`) | What it brings back | When | Where it goes |
|---|---|---|---|
| `patch_notes.md` | champions whose kit changed, quoted from Riot's notes; game facts the patch changed | each new patch, and after a mid-patch update (then only that update) | the review queue (the owner checks those champions' notes); `data/manual/game_facts.csv` |
| `game_facts.md` | every objective and camp timer and role quest reward, re-checked with sources; hotfixes | each new patch | `data/manual/game_facts.csv` |
| `class_definitions.md` | Riot's own description of each champion class | once (done 2026-10-03) | `data/manual/class_definitions.csv` |

**How a research round works** (the owner):
1. "Research due" appears in the top bar. Settings, Data and updates, **Open the research
   folder**: the prompts there are already written for what's due (the current patch and
   champion list, today's game facts; after a hotfix, that update only).
2. Open the prompt file, copy from **Prompt** to the end (nothing to fill in), and give it to
   an agent with web browsing.
3. Paste the agent's whole reply into a new `.md` file in `research/results/` (any name).
4. In the app, Settings, Data and updates, **Check research/results**, then **Apply these
   changes** (or
   `scout import-research`, or ask Claude Code). Every row is checked first (champion ids, a
   source and https link, a patch) and nothing changes until you say yes. When the game facts
   reply and the patch notes reply both have the same fact, the game facts reply wins (it's the
   full re-check). Applied replies move to `research/results/done/`, kept as the record of
   where each fact came from (their SOURCES, NOT FOUND and NOTES sections).
5. Applying marks the prompts done for this patch in `research/status.csv` (for patch notes,
   with the hotfixes it covered); the "Research due" button goes away and the prompts are
   rewritten. Claude Code commits `data/manual/`, `research/` and pushes; everyone else's app
   gets them with the next update.

**Known gaps** (no source found; left blank on purpose):
- Riot never published a description for the Catcher and Specialist classes, so those two
  have none (`research/results/done/class_definitions-2026-10-03.md`, NOT FOUND).
- Engage, power spikes and play style stay drafted notes (`source=llm`) until the owner reviews
  them; no source gives them.

## What's shared through GitHub, and what stays on each PC
| Shared (in git; comes with each update) | On each PC only (never in git) |
|---|---|
| the code and rules; `data/manual/` (game facts, class definitions, champion notes, matchup briefs, overrides, matchup notes); `research/` prompts, results and status | keys (`.env`), `config.yaml`, champion lists (`pool.yaml`, `pools/`), `data/generated/` (static data, OP.GG numbers, measured data, the review queue), `data/cache/` (downloads, champion pictures, window size), `data/history/` (post-game results, the backtest), `reports/` (each game's report and its History screen) |

So a friend's app builds its own static data and OP.GG numbers (no key needed), and measures
its own match data only if it has a Riot key. `data/manual/matchup_notes.csv` is shared too, so
The owner's own notes would show up as "Your notes" on a friend's PC (it's empty so far).

## Each new patch: the checklist
1. **Nothing to start**: the app's refresh notices the new Data Dragon version within 6 hours
   (or press Refresh data). It rebuilds the static files, fetches the new OP.GG numbers,
   downloads new champion pictures, and queues champions whose kit changed for review.
2. **Read the log** if something looks off: `data/generated/REFRESH_LOG.md` (what changed, what
   failed, which champions the wiki or CommunityDragon don't have yet).
3. **Research** (the owner): the round above, for `patch_notes.md` and `game_facts.md`.
4. **Review** what's queued: `scout review` walks the drafted notes of champions that changed;
   stale matchup briefs are in the queue too (`brief_stale`).
5. **A week in**: Settings, Data and updates shows how many games are measured and what
   changed since last patch; `scout collect --status` shows the same with the OP.GG
   cross-check. `scout backtest` shows how each call is holding up.

## Every source
| Source | What Sidekick takes | Key | How often |
|---|---|---|---|
| Riot Data Dragon (ddragon.leagueoflegends.com) | versions, champions, abilities and cooldowns, tips, items, summoner spells, pictures | none | each new version |
| CommunityDragon (raw.communitydragon.org, Riot's game files) | melee or ranged, damage type, Riot's 1-3 playstyle ratings | none | each new version |
| The LoL Wiki (wiki.leagueoflegends.com) | `Module:ChampionData` (classes, positions, last change), page categories (knock-up, dash, stealth...); the patch page's mid-patch updates (V26.19) | none (CC BY-SA) | each new version, again 3 days later; the patch page each refresh on the research PC |
| OP.GG's MCP server (`lol_list_lane_meta_champions`, `lol_get_lane_matchup_guide`, `lol_get_champion_synergies`, `lol_get_summoner_profile`) | role rates, matchups, lane labels, builds, synergies, game-length win rates, players' records at loading | none | 24 hours (lane stats), 72 hours (matchups), each draft |
| Riot API: League-EXP-V4, Match-V5 (matches and timelines) | Emerald+ ladder pages and their ranked games, measured by the collector; visible enemies' recent ranked games at loading (the duo check); your own match after a game (post-game check) | Riot key | continuously while idle; at loading; after each game |
| Riot API: Champion-Mastery-V4, Account-V1, Status-V4 | one-tricks at loading (Account-V1 turns each visible player's Riot ID into Riot's id), the key check | Riot key | at loading; when a key is pasted |
| The League client (LCU, on your PC) | champ select, who's logged in, region, your recent games and mastery | local, read-only | live |
| Riot's patch notes (www.leagueoflegends.com/en-us/news/game-updates/) and the LoL Wiki | kit changes, timers, role quests, class descriptions | none | research rounds |
| GitHub (github.com/zchristensen01/sidekick) | new versions of Sidekick | none (public repo) | start and every 6 hours |
| Anthropic API | the written report (optional) | Anthropic key | each final report |

Details for each source (endpoints, fields, politeness, failure handling): `DATA.md`.

## Refreshed by the app or `scout refresh` (machine-owned, never edit by hand)
| File | What's in it | Source | When |
|---|---|---|---|
| `data/generated/PATCH` | the current Data Dragon version | Data Dragon `versions.json` | each refresh |
| `static/<version>/champions.csv` | champion ids, client keys, names | Riot: Data Dragon `championFull.json` | new version, or a column change |
| `static/<version>/abilities.csv` | every ability's name, cooldowns and Riot's text | Riot: Data Dragon | same |
| `static/<version>/champion_meta.csv` | range, attack range, move speed, damage type, Riot classes, positions, **Riot's ratings** (damage, toughness, control, mobility, utility, difficulty), **the wiki's mechanics** (knock-up, dash, stealth...), last changed patch, OP.GG's name; `field_sources` says which source gave each field | CommunityDragon (Riot's client data), the LoL Wiki (`Module:ChampionData`, page categories), Data Dragon | same; the wiki is re-read 3 days after a new version |
| `static/<version>/summoner_spells.csv`, `items.csv` | spell keys and names, item names, costs and build depth | Riot: Data Dragon | same |
| `static/<version>/tips.csv` | Riot's "playing as" and "playing against" tips | Riot: Data Dragon | same |
| `stats.sqlite` | OP.GG: role rates and tiers (daily), matchup tables, lane-advantage labels, synergies, builds, win rate by game length (72 hours) | OP.GG's MCP server | lane stats each day; matchups during each draft and at each refresh for everyone's champions |
| `stats.sqlite` (`measured`, `collected`, `games`) | figures measured from Emerald+ ranked games per champion and role (gold/XP/CS vs the lane opponent, lane push, level 3/4 times, first item, roaming), and one small record per game (both drafts and what happened, no ids) for the backtest | Riot's match data, through the collector | continuously while the app is idle, or `scout collect`; the current and previous patch |
| `review_queue.csv` | what needs a person: new champions, kit changes, stale briefs, data that disagrees with a drafted note | the refresh, the research importer and the app | each refresh and game |
| `REFRESH_LOG.md` | one entry per refresh | the refresh | each refresh |
| `data/history/backtest.csv` | each call's record on the stored games | `scout backtest` | each refresh |
| `patch_updates.json` | the mid-patch updates on the LoL Wiki's page for the current patch | the LoL Wiki | each refresh on the research PC |
| `data/cache/` | raw downloads (per version) and champion pictures (`img/champion/`) | all of the above | as needed; safe to delete |

## Curated (hand-owned: code never overwrites; `data/manual/`)
| File | What's in it | Source today | What to check each patch |
|---|---|---|---|
| `game_facts.csv` | objective and camp timers, role quest rewards: one line each with source, link and patch | Riot's patch notes; the LoL Wiki where Riot's notes don't say (dragon timers, Herald despawn, current role quest values) | the research round (`patch_notes.md`, `game_facts.md`); last checked 2026-10-03, patch 26.19 |
| `class_definitions.csv` | Riot's own words for each champion class (16 classes) | the LoL Wiki's copy of Riot's 2016 classes dev blog (`class_definitions.md`, 2026-10-03) | nothing, unless Riot changes its classes |
| `champion_traits.csv` | per champion: the values no source gives (engage, spikes, style, most tags) and the three notes; early game, wave clear and roaming until the collector has 50+ games. `cc`, `escape`, `frontline` and the tags `airborne`, `stealth`, `needs_airborne` are **overridden in memory** by Riot and the wiki (`scout/data/sourced.py`) unless the row's `source` is `owner` | drafted by an LLM from Riot's text (`source=llm`), until reviewed | champions in the review queue (`scout review`) |
| `matchup_briefs.csv` | how to play one matchup | drafted from Riot's text and OP.GG's labels; reviewed by the owner | `brief_stale` entries in the review queue |
| `matchup_notes.csv` | the owner's own notes, shown as "Your notes" | the owner | nothing |
| `champion_overrides.csv` | corrections that win over every source, each with a reason | the owner | whether the source fixed it (then delete the row) |

## Not data files, but they change with the game
- `scout/rules/league_rules.yaml`: the rules' wording uses the data above; a rule never names
  a timer, cooldown or number itself (CLAUDE.md hard rule 3).
- `docs/REPORT_AGENT.md`: the writer's instructions.
- OP.GG's tool names and fields: checked every time Sidekick connects (it stops with a clear
  message if they changed).

## What each value in a report rests on
| Value | Source | Notes |
|---|---|---|
| Crowd control, mobility (escape), toughness (frontline) | Riot's ratings: 1 low, 2 moderate, 3 high | escape is 0 when Riot says low and the wiki lists no dash or blink; a frontliner is Riot's "high" toughness |
| Knock-ups (airborne), stealth | the LoL Wiki's categories | Airborne = knock-up, knock-back, knock-aside or pull (wiki: Types of Crowd Control) |
| Needs airborne targets (Yasuo) | Riot's ability text | |
| Scaling | OP.GG's win rate by game length (under 25 vs past 35 minutes) | drafted note only when the draft has no numbers; reports quote the numbers |
| Lane advantage, matchup win rates, builds, synergies | OP.GG | shrunk toward expectations (docs/STATS.md) |
| Early game, wave clear (lane push), roaming | measured from Riot's match data: the champion's quarter within its role (gold at 10, minutes 3-10 on the enemy half, roaming takedowns before 14:00), with 50+ games for that champion and role and 8+ such champions in the role | drafted values until then |
| Jungle clear | measured level 3 and 4 times, and the clear speed in words ("among the fastest (top quarter)") ranked among junglers with 50+ games; quoted to the writer and in the Both teams panel | not used by the jungle formulas yet |
| Ability text, tips, passives | Riot (Data Dragon) | |
| Objective and camp timers, role quests | `game_facts.csv` (Riot's patch notes, the LoL Wiki) | research round each patch |
| Class descriptions | `class_definitions.csv` (Riot's words via the LoL Wiki) | none for Catcher and Specialist |
| How often a call came true | the backtest on stored games (`track_record`) | shown to the writer at 100+ graded calls |
| Engage, spikes, style, notes | drafted (LLM) or the owner | no source exists |
