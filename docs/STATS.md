# STATS: how we use win rates and matchup numbers

`DATA.md` covers where numbers come from and how they're refreshed. This doc covers what we
compute from them and how much we trust them. Most of this lives in `scout/analysis/stats.py`
as small, tested functions (the measured figures in `scout/analysis/measured.py`).

## What we use
| Number | Per | Used for |
|---|---|---|
| Win rate, games | champion x role | base strength; expected matchup result; blind pick options |
| Pick and ban rate | champion x role | stored only (a non-empty pick rate marks a lane meta row, to tell when lane meta was last fetched) |
| Tier | champion x role | "strong this patch" (tier 1-2), to top up pick options when the pool and most-played give fewer than 2 |
| Role play rate | champion x role | enemy role inference |
| Matchup wins and games | champion x opponent x role | lane verdict, counter-pick |
| Lane advantage | matchup | early lane verdict |
| Solo-kill advantage | matchup | quoted as text ("Elise gets more solo kills"); not used in any verdict. Volatility comes from traits only (`analysis/lanes.py`) |
| Synergy wins and games | champion pair (same team) | bot lane duos in the report; pick options, with each locked ally (M18) |
| Win rate by game length | champion x role | each champion's `scaling` level (Scaling, below) |

## Rule 1: never trust a raw percentage without its sample size
A win rate from `n` games is accurate to about +-1.96 x sqrt(0.25/n), at 95% confidence:

| games | 95% range | can it tell 46% from 50%? |
|---|---|---|
| 300 | +-5.7 pts | no |
| 1,000 | +-3.1 pts | barely |
| 3,000 | +-1.8 pts | yes |

The old plan used 300 games as the minimum with severity bands only 2-3 points wide, which would
label coin flips as hard counters. Instead of a hard cutoff, we **shrink** every rate toward what
we'd expect without the matchup data, by an amount that depends on the sample size.

## Rule 2: compare to what's expected, not to 50%
A 47% matchup can mean "this opponent counters me" or just "my champion is weak this patch".
Those call for different advice, so we separate them.

Notation: `p_me` and `p_opp` are each champion's base win rate in this role.
1. **Expected matchup result** with no special interaction, Elo-style:
   `logit(e) = logit(p_me) - logit(p_opp)`, where `logit(p) = ln(p / (1 - p))`.
   Example: 52% vs 48% base gives about 54% expected.
2. **Shrunk matchup rate** from `w` wins over `n` games, with prior strength `k`
   (`stats.prior_games`, default 1000):
   `p_hat = (w + k * e) / (n + k)`.
   Few games stay near `e`; many games move toward the observed rate.
3. **Matchup delta**: `delta = p_hat - e`. This is "how much this specific opponent changes things".

The counter-pick verdict (`COUNTERPICK.md`) uses `p_hat` for the outlook ("how bad is this
lane") and `delta` for "is this a real counter or is my champion just weak".
Synergies use the same method with the duo's expected result from both base rates
(`stats.synergy_prior_games`, default 500).

This is the method the open-source DraftGap uses (MIT licensed; we reuse the math, not its data).

## Rule 3: carry data across patches carefully
On patch day the new patch has almost no games. We blend in the previous patch, meaning only
the patch right before this one (`patch_pair`): after a break, older data isn't blended in.
- `w_eff = w_this + lambda * w_prev`, `n_eff = n_this + lambda * n_prev`, with
  `lambda = stats.previous_patch_weight` (default 0.5).
- `lambda = 0` for any champion that **changed this patch**: its `last_changed_patch` in
  `champion_meta.csv` (the LoL Wiki's "last changed") equals this patch
  (`scout/data/stats_service.py`). Old data for a changed champion is misleading. Ability
  changes in Data Dragon (text or cooldowns) and kit changes from the patch notes don't set it:
  they go to the review queue (`abilities_changed`, `patch_notes`) for the owner.
- If `n_eff` is still below `stats.min_games_display` (default 500), the report doesn't show the
  number; the verdict falls back to traits: "(no reliable numbers; going by champion notes)",
  with the reasons after a colon when there are any (`scout/counterpick.py`).
- When more than half of the blended games are from the previous patch, the number says so:
  "48% over 3,572 games (mostly last patch's data)". When the numbers aren't this patch's at
  all (none yet, or OP.GG is already on the next patch), the patch label shows instead:
  "(26.18)". The counter-pick verdict's flag to the writer
  (`blended_previous_patch`) follows the same more-than-half rule (`MatchupStat.mostly_previous`).

How it's shown: the report gives the shrunk rate from my side, labelled as a whole-game win
rate: "Elise isn't a special counter to Lee Sin (game win rate 48% over 3,572 games): 1 point
worse than both champions' overall strength predicts, so Lee Sin is just weaker this patch."
So it can be a point off OP.GG's site (DECISIONS.md #43). Below `min_games_display` it shows
no number: "Lee Sin vs Elise: even (no reliable numbers; going by champion notes)."

## Rule 4: say it the same way every time
- The builder pre-formats every number into a display string, e.g. `"47% over 4,140 games (26.19)"`.
  The writer copies those strings; it never rounds or formats numbers itself. That's what makes
  the "no invented numbers" validator reliable.
- Show whole percents. Always show games. Show the patch label if it isn't the current patch.
  Every OP.GG win rate goes through the same `display()`: the counter-pick verdict, the
  jungler's lanes overview ("Top even (game win rate 47% over 4,140 games)"), bot lane duos,
  and pick options, blind ones included ("49% over 53,787 games"). OP.GG's game-length rates
  have no game counts, so those are quoted without them (Scaling, below).

## Scaling from game length
OP.GG's matchup guide gives each champion's win rate at 0, 25, 30, 35 and 40+ minutes, but
**without game counts per bucket**, so these can't be shrunk and are a coarse signal only.
- `scaling_index = win rate at 35+ min - win rate under 25 min` (percentage points), for the
  champion in its role. Gaps under 3 points are noise.
- **It sets each champion's `scaling` level wherever OP.GG has the numbers (M15,
  `with_data_scaling` in `analysis/players.py`, `scaling_level` in `analysis/stats.py`)**:
  +6 points or more = 3 (keeps climbing), -3 to +6 = 2 (scales normally), -3 to -6 = 1 (early
  or mid game peak), -6 or less = 0 (falls off). The cut-offs are the noise level, doubled for
  the ends. A row the owner wrote (`source=owner`) keeps its value; the numbers are still quoted.
  The report quotes the two numbers ("OP.GG: 45% of games under 25 minutes, 55% of games past
  35"), never the level. The draft fetches every enemy's matchup guide too, so all ten
  champions have numbers when OP.GG does.
- Team early/late read (`analysis/team.py`): each team's mean `scaling` over its champions,
  which mixes these 0-3 levels with trait values for champions without numbers. The game plan
  (`report/select.py`) and the team rules call one team the better scaler when the means
  differ by 0.4 or more.
- When the index strongly disagrees with a champion's `scaling` trait (3 points or more
  against a trait of 0-1, or -3 or less against 3), `stats_disagree` is queued for review.

## Stats vs traits: who wins
| Question | Stats are good enough when | Otherwise |
|---|---|---|
| Who wins the lane early | `n_eff >= min_games_display` and the source gives lane advantage | traits (lane power diff) |
| Is this matchup bad overall | `n_eff >= min_games_display` | traits plus structural rules, verdict "unknown" if neither |
| Who scales | per champion: OP.GG has its game-length rates (and the row isn't the owner's) | traits `scaling` for that champion |
| Enemy roles | role rates exist for the patch | wiki position lists as a rough prior |
When stats decide and traits disagree, the report notes it in one line and `review_queue.csv`
gets a `stats_disagree` row naming the champions and the field.

How "who wins the lane early" uses stats (`analysis/lanes.py`, `with_stats`): OP.GG's
lane-advantage label from my side, when the matchup is shown. Bot lane uses the ADC and support
labels: one side named (the other even or missing) decides it; opposite sides keep the traits
verdict. Only an opposite verdict (win vs lose) counts as a disagreement; even vs a side doesn't.
Scaling: the level from the numbers replaces the trait in the report (above); a big
disagreement also queues `stats_disagree`, so the drafted trait gets fixed too.

## Rank filter
Stats depend on rank: what loses in Silver can win in Diamond. But the OP.GG tools we rely on
(lane meta, matchup guide, synergies) have **no rank parameter**, and champion analysis silently
ignores tiers it doesn't recognize (`DATA.md`). So every OP.GG number is OP.GG's default
bracket, and both the expected result and the matchup come from that same bracket.
`stats.rank_filter` (default `opgg_default`) is only a label: OP.GG rows are stored and read
under it, but nothing is sent to OP.GG, so whatever it says, the numbers under it are still the
default bracket. The measured figures (below) are always Emerald and above: the collector walks
a fixed ladder (`LADDER` in `scout/data/collector.py`), and the `measured` table has no rank
column.

## What we don't do
- No "you have a 53% chance to win" headline. Draft-only models predict outcomes poorly (about
  55% accuracy), so a team-level draft score, if added later (M12), is shown as a lean
  ("slight edge to your draft"), never as a probability.
- No skill ratings, MMR or Elo estimates of real people (Riot policy). What is shown, at the
  loading screen only, is each visible player's own public OP.GG record on the champion
  they're playing, as OP.GG reports it (M16; switchable in Settings; `POLICY.md`).

## Our own numbers from Riot's match data (M19)
The collector (`scout/data/collector.py`) walks Riot's ranked solo ladder from Challenger down
to Emerald IV, takes each player's few most recent ranked solo games, and measures each game
once (`scout/data/measure.py`): per champion and role, against the lane opponent, gold, XP and
CS differences at 10 and 15 minutes, time on the enemy's half in minutes 3-10, level 3 and 4
times, first finished item, takedowns, roam takedowns, kill share and deaths before 14:00, and
the win. Only this patch and the previous one are kept; games under 15 minutes aren't measured;
player ids are used in memory only and games are stored by a one-way hash. `scout collect`
runs it by hand; the app runs it in the background while you're not in a game (`LCU.md`
section 6), with its own share of the key's rate limit.

How the figures are used (`scout/analysis/measured.py`):
- A champion in a role needs 50 measured games (`MIN_GAMES`) before its figures are used.
- Levels 0-3 for early (gold at 10), wave clear (time on the enemy's half) and roam (roam
  takedowns) come from the champion's rank among its role's champions (those that really play
  the role, with 50+ games) by quarters: top quarter = 3 ... bottom quarter = 0. A role needs
  8 such champions first. These levels replace the drafted values, except on the owner's rows
  (`source=owner`); the figures are quoted as display strings with their source line.
- Changes since last patch: a figure counts as changed only past 3 standard errors, with 50+
  games on both patches.
- Coverage (how many champion-roles really played have 50+ games) and a cross-check of our win
  rates against OP.GG's are shown by `scout collect --status` and the app's Settings.

The backtest (`scout/postgame/backtest.py`, M20) replays each collected game's draft through
the analysis from both sides and grades the claims a final report would make against what
happened, compared with always guessing the most common outcome.
