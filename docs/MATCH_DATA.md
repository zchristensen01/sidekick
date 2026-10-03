# MATCH_DATA: the games Sidekick collects, and what they're for

Sidekick measures real ranked games itself from Riot's match data: Emerald and above, the
current and the previous patch. This file says who collects them, what's kept, what each game
gives, when collecting stops, and what the games are used for.

## Who collects: the owner's PC only
- Only the PC with `owner: true` in its `config.yaml` collects games, runs the backtest and gets
  research reminders. That's the person who maintains Sidekick. Everyone else has
  `owner: false` (the default in `config.example.yaml`), and Settings doesn't show those parts.
- Why: what the games teach (the lane model's settings, which rules hold up, measured figures)
  is learned once, on one PC, and goes into the code, so every install gets it with the next
  update. A friend's PC collecting its own games would only spend their Riot key (a development
  key has to be renewed every 24 hours) to relearn the same thing.
- What a friend's reports don't have: the per-champion measured figures (gold at 10, clear
  speed...), because those are read from the local database. Everything else is the same.
- On the owner's PC, the "Match data (Riot)" switch in Settings pauses collecting
  (`stats.collect`). It needs the Riot key and never runs in champ select or a game.

## Where it's kept, and what's never kept
- In `stats.sqlite` in the user's data folder (`Paths.stats_db`: under `%LOCALAPPDATA%\Sidekick`).
  Never in git, never sent anywhere.
- No player names, Riot IDs or account ids are stored. Players are listed from Riot's ladder in
  memory only, and a game is remembered by a one-way hash of its id, so nothing stored points
  back to a player or a game.
- Two kinds of data:
  - **Totals per champion and role** (`measured`), and **per matchup**, a champion against its
    lane opponent (`measured_matchups`): counts, sums and sums of squares only.
  - **One small record per game** (`games`), about 1.6 KB: both teams' champions by role, what
    happened from each side (gold at 15 per lane, who pushed, plates, early deaths, the first
    gank, the jungle start side, each enemy's share of their team's gold, game length, winner),
    and the ladder tier the game was found through. This is what the backtest grades on.

## What each game gives (`scout/data/measure.py`)
| figure | who | what it counts |
|---|---|---|
| win | everyone | 1 if their team won |
| gold, XP and CS difference at 10 and 15 | everyone | against the lane opponent (same position, other team) |
| cs_10 | everyone | minions and monsters killed by 10:00 |
| push_3_10 | laners | share of minutes 3-10 on the enemy's half of the map |
| level 2, 3 and 4 times | everyone | seconds; for a jungler, level 4 is a full clear |
| level2_first | laners | 1 if they reached level 2 before their lane opponent |
| first_item_s | everyone | seconds to the first finished item (Riot's build depth 3, not boots) |
| takedowns, roam takedowns, kill share, deaths before 14:00 | everyone | roam = outside their own lane |
| first_blood | everyone | 1 if they killed or helped kill in the game's first kill |
| solo_kills_14 | everyone | kills before 14:00 with nobody assisting |
| plates_14 | laners | plates of the enemy turret in their lane destroyed before 14:00 |
| gank_10, first_gank_s | junglers | a takedown on an enemy laner before 10:00, and when |
| dragons_20, grubs_20, herald_20, first_dragon | junglers | their team's dragons, voidgrubs and Herald before 20:00; the first dragon |

Per matchup, the counted figures are win, gold and XP at 10, gold at 15, CS at 10, lane push,
solo kills, the level 2 race and deaths before 14:00 (`MATCHUP_METRICS`).

Not collected, because OP.GG already gives it: win rates by matchup and patch, builds, runes,
synergies, game-length win rates.

## What the games are used for
- **Measured figures in reports** (M19): once a champion has 50+ games in a role, its figures
  reach the writer and the Both teams panel, and they set its early game, wave clear and
  roaming levels (quarters within the role); a jungler's clear speed is said in words. Changes
  since last patch are flagged.
- **The backtest** (M20, `scout backtest`): Sidekick's whole analysis runs on each stored draft
  and every call is graded against what happened; each call's record reaches the writer once it
  has 100+ games. Next: fit the lane model and its cut-offs to the outcomes, and retire rules
  that don't beat the usual result. The fitted settings go into the code.
- **Matchup figures**: collected now; they become usable as matchups reach 20-50 games (`scout
  collect --status` counts them). Planned use: the lane read (TASKS, M20).

## How much, and when it stops
- **4,000 games per patch** (`PATCH_TARGET` in `scout/data/collector.py`), then collecting pauses
  until the next patch. Past that, the common champions' figures barely move. At about 35 games
  every 2 minutes in the app (45 with `scout collect`), that's about 4 hours of the app open and
  idle per patch.
- **Older patches are dropped** at the start of each collecting run: only the current and the
  previous patch's totals, matchups and records are kept. The "already counted" marks go after
  30 days (past the 14-day look-back, a game can't come up again).
- **Size**: about 1.6 KB per game record plus the totals: around 15 MB at most for two patches.

## Your own games (kept for a later review)
After each game played with the app (when it has a Riot key), the post-game check fetches that
match anyway. It now also keeps `reports/<report>.review.json` next to the report and its History
screen, on that PC only: every player's figures from the table above (champions and roles, no
names), what happened from the player's side, and each claim's result. Nothing reads it yet: it's
for the post-game review planned in `docs/future/postgame-review/`.

## Commands
- `scout collect [--games N]`: collect by hand (the owner's PC; the full key rate).
- `scout collect --status`: games this patch against the target, champion-roles with 50+ games,
  matchups with 20+ games, changes since last patch, the cross-check with OP.GG.
- `scout backtest [--fetch]`: grade every call on the stored games.
