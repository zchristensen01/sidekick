# Future project: the post-game review

**Status:** not built. The owner asked for it on 2026-10-03 as a later project ("a post game
review of how they did based on the plan"). For now only the data it needs is kept.

## What it should do
After a game, a short review in the app (and a few lines for the LLM to write) that answers:
1. **Did the plan hold?** The report's calls (lane winners, who pushes, the first gank, the fed
   threat, the long game) against what happened. The post-game check already grades these.
2. **How did you play against the plan?** For example: the report said "gank bot first, Samira
   and Nautilus have no escape"; did your first gank go bot, and when? It said "you win early
   jungle fights, contest the scuttles"; did you, and what was your gold at 10 against the
   enemy jungler?
3. **How did you do against the usual?** Your figures (gold, XP and CS against your lane
   opponent at 10 and 15, level 2/3/4 times, first item, deaths and takedowns before 14:00,
   first gank time, objectives by 20) next to the average for your champion in that role, and
   for that matchup, from the collected games (`docs/MATCH_DATA.md`).
4. **Over time, per account:** the same figures across your recent games on each League account
   (the History list already knows which account played), so trends show ("your gold at 10 on
   Lee Sin is up since last week").

Not in scope: anything during the game (CLAUDE.md hard rule 2); anything about other players
beyond their champion (hard rules 8 and 10).

## The data it will use (all on the player's PC only)
Paths are inside the player's Sidekick folder (`%LOCALAPPDATA%\Sidekick`, `scout/paths.py`).

| What | Where | Kept since |
|---|---|---|
| The plan: the report, written and rules versions | `reports/<report>.md` | M6 |
| The report's screen as shown | `reports/<report>.view.json` (History) | M23 |
| The report's calls, and the client's game id | `reports/<report>.json` | M10 |
| Each call's result | `data/history/postgame.csv`, and in the review file | M10 |
| Every player's figures from the game, what happened, each call's result | `reports/<report>.review.json` (`scout/postgame/check.py` `save_review`) | 2026-10-03 |
| Champion and matchup averages | `stats.sqlite` (`measured`, `measured_matchups`), owner's PC | M19, 2026-10-03 |
| Which account played | the History screen's `meta.account` | M23 |

The review file is versioned (`version: 1`). Fields: `report`, `patch`, `my_role`,
`my_champion`, `lane_opponent`, `players` (side, role, champion, opponent, figures), `outcome`
(scout/postgame/grade.py `outcome()`), `claims` (kind, lane, predicted, actual, hit, measure).

## What the LLM should get (when it's built)
Same rules as the report writer (`docs/REPORT_AGENT.md`): facts only, pre-formatted numbers,
every line citing its source. A plan for the input:
- `plan`: the report's sections and items as shown (from the view file), each with its source id.
- `calls`: each claim with its result and the measure it was graded by.
- `you`: the player's figures, each next to the champion average and the matchup average when
  there are enough games (display strings like "gold at 10: +240 (Lee Sin jungle average +35,
  1,240 games)"), and next to the player's own recent average on that account.
- `game`: the outcome (won or lost, length, lanes' gold at 15, objectives, first gank).
The writer would produce 3-5 lines: what held, what you did well against the plan, and one thing
to try next game. No grades of the player as a person, no blame on teammates.

## Open questions for when it starts
- Where it shows: under the game in History (likely), and a line at "Game ended".
- How many games make an account trend worth showing (probably 10+).
- Whether the review costs an LLM call per game (about 1 cent) or stays rules-only text.
- Whether the first item time needs the item table in the post-game check (the review file
  leaves `first_item_s` out today).
