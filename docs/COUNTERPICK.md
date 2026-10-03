# COUNTERPICK: detection and how to play into it

## Definitions
- **Lane opponent**: the enemy champion in my role (`ROLES.md`): enemy top for top, enemy
  jungler for jungle, enemy mid for mid, enemy ADC for bot, enemy support for support. Bot and
  support also get a 2v2 read of the whole lane.
- **Outlook**: how hard the matchup is for me, from the shrunk matchup rate `p_hat` (`STATS.md`).
- **Specific counter**: the opponent changes my odds beyond what both champions' overall strength
  predicts (`delta <= -counterpick.specific_delta`). Without this, a bad outlook may just mean my
  champion is weak this patch.
- **Counter-picked**: the opponent locked **after** me, the outlook is bad, and it's a specific counter.
- **Bad draw**: the outlook is bad, but they locked first (I picked into it) or it isn't a specific counter.
- **I countered them**: I locked after them and the outlook favors me.

## Detection (`scout/counterpick.py`)
1. **Pick order** (`LCU.md` section 4): find the pick turn of my champion and of the opponent's
   champion. `picked_after_me = opp_turn > my_turn`. From a game fixture YAML, use its
   `pick_turns` map (champion id -> draft turn, `scout/model/gamefile.py`); if either turn is
   missing, `picked_after_me` is unknown and only the outlook is reported.
2. **Outlook from stats** (preferred): the matchup row for (my role, me, opponent) gives `p_hat`
   and `delta` with blended games `n_eff`. Requires `n_eff >= stats.min_games_display`.
3. **Outlook from structure** (stats missing or thin): start from the lane verdict (winning
   = favorable, even = even, losing = soft counter, losing with `state.diff <= -3` = hard
   counter), then each signal makes it one band worse: ranged into my melee, top lane only
   (`ranged_into_melee`, from `lane.range_mismatch` in `scout/analysis/lanes.py`), my engage
   (3) into their `peel`/`disengage` (`engage_into_peel`). Losing with `diff <= -1.5` is
   listed as `loses_early`. Jungle: the early 1v1 difference
   (`>= 1` favorable, `0` even, `-1` soft, `<= -2` hard). Structure never says `specific`.
4. **Unknown** if neither gives a verdict, and the report says so.
5. **Bands** on `p_hat` (config `counterpick.*`, defaults):

   | `p_hat` | outlook |
   |---|---|
   | >= 51.5% | favorable |
   | 48.5% to 51.5% | even |
   | 46.5% to 48.5% | soft_counter |
   | < 46.5% | hard_counter |

6. **Role uncertainty**: if the opponent comes from an enemy role guess below
   `roles.low_confidence_below`, compute the verdict for the top alternatives too and report
   "if Sylas is your laner: ..., if Yone: ...".
7. **Jungle**: the opponent is the enemy jungler. The outlook comes from the jungle matchup
   stats when they're shown, else from the early 1v1 difference (step 3); the two aren't
   combined. Draft-level threats come from a map rule: an `invade_strong` enemy jungler whose
   mid and at least one other lane can move first means "expect a level 1-2 invade"
   (`JG-INVADE-RISK`).
8. **Bot and support**: the verdict is for my role's matchup. The 2v2 read (kill lane vs poke
   lane, engage vs peel) comes from lane rules, not this module.

## Output block (goes into the writer input as `counterpick`)
Built by `counterpick_block` in `scout/report/builder.py`:
```json
{
  "opponent": "Teemo",
  "opponent_role_confidence": 0.55,
  "picked_after_me": true,
  "outlook": "hard_counter",
  "specific": true,
  "label": "counter_picked",
  "evidence": {
    "source": "opgg",
    "display": "45% over 1,840 games",
    "delta_display": "3 points worse than both champions' overall strength predicts",
    "blended_previous_patch": false
  },
  "structural_flags": [],
  "alternatives": [
    {"opponent": "Yone", "outlook": "even", "display": "50% over 2,100 games"}
  ]
}
```
`label` is one of `counter_picked`, `bad_draw`, `weak_patch` (bad outlook, not specific),
`even`, `you_countered`, `favorable`, `unknown`. `picked_after_me` is `null` when a pick turn
is missing. `specific` is `true` or `false` only for a bad outlook from the numbers, else
`null`. `evidence.source` is `opgg` (the numbers decided), `structure` (traits decided;
`display` and `delta_display` are empty) or `none` (unknown). `display` gets a patch label
(say `(26.18)`) or "(mostly last patch's data)" when it isn't this patch's data.
`structural_flags` holds the internal names of the signals behind a structure verdict
(`ranged_into_melee`, `engage_into_peel`, `loses_early`); the verdict line puts them in words.
`alternatives` (up to two, each at least 15% likely) are filled only when the role guess is
below `roles.low_confidence_below`; an alternative's `display` is empty when that pair has no
numbers. Rule ids, builds and the owner's notes aren't in this block: rules reach the writer as
section items, and "Your notes" are rendered by code.

## "How to play into it": rules (scope `counterpick`)
Context paths: `outlook`, `specific`, `label`, `picked_after_me`, `p_hat`, `games`, `source`,
`me.*` (incl. `me.role`), `opp.*`. The rules themselves (wording, priority, confidence, `tests`
block per `RULES.md`) live in `scout/rules/league_rules.yaml`, section `counterpick`. There are
eight:
- `COUNTER-HARD`: hard outlook, label `counter_picked` or `bad_draw`, not jungle. Winning lane
  isn't the goal: give up CS under tower when you have to, trade while their key ability is
  down, ask for early cover.
- `COUNTER-SOFT`: soft outlook, same labels, not jungle. Play even, avoid their power windows,
  look for your spike.
- `COUNTER-PICKED-AFTER`: label `counter_picked`, any role. They locked after seeing you;
  expect early aggression.
- `COUNTER-WEAK-PATCH`: label `weak_patch`, any role. Play your normal game, a bit safer.
- `COUNTER-WE-SCALE`: soft or hard outlook, `me.scaling` 3, not jungle. You out-scale them:
  losing lane slightly is fine, dying isn't.
- `YOU-COUNTERED`: label `you_countered`, not jungle. Press it early: priority, deny CS, plays
  before their spikes.
- `JG-COUNTER-BAD`: soft or hard outlook, label `counter_picked` or `bad_draw`, jungle only.
  Stay off their side early unless your lanes move first, ward their entrances, path toward
  your strongest lanes.
- `JG-YOU-COUNTERED`: favorable outlook, jungle only. Track their start, contest camps or
  scuttles when your lanes can move first.
`bad_draw` has no rule of its own: the verdict line already says it, and `COUNTER-HARD`,
`COUNTER-SOFT` and `JG-COUNTER-BAD` give the plan.

As built, `scout/counterpick.py` computes the verdict in `analyze()` (`Insights.counterpick`),
the report's Counter-pick section opens with `verdict_text` (with the evidence display string
in `numbers`), and `report/builder.py` adds this block to the writer input. Role alternatives
use my own matchup table (one guide call already returns it), so they cost no extra fetch.

## What the report says (laner)
1. Verdict in one line with evidence (`verdict_text` in `scout/counterpick.py`), for example
   "Counter-picked: Teemo locked after you and is a hard matchup for Darius (game win rate 45%
   over 1,840 games), 3 points worse than both champions' overall strength predicts." Thin
   numbers read "(no reliable numbers; going by champion notes: ...)".
2. The plan by phase (levels 1-3, 3-6, after 6, first item), from counter-pick rules, lane rules,
   and both champions' spikes.
3. What to punish: the opponent's `key_note`.
4. What to ask the jungler for.
5. The opponent's usual core build into me, from OP.GG (`stat:items:<role>`, "X's usual build
   into Y: A, B, C."). No build or rune advice of our own.
6. "Your notes", if any.

## Pick suggestions (`scout/picks.py`, M9b)
Before I lock, show 2-3 options from my champ pool for my **assigned** role, with reasons.
Same data and bands as the verdicts above, used before the pick instead of after it.
1. **Candidates**: my champions for my role, best rated first (1-5 comfort stars). In the app
   that's the logged-in account's list, `pools/<Name_TAG>.yaml` (`scout/accounts.py`, read at
   each champ select by `scout/lcu/watcher.py`); the app's Champions page edits it. `pool.yaml`
   is the starting copy for an account Sidekick hasn't seen yet and the list used when no
   account's list is loaded (the offline commands, `scout watch --no-window`); `scout pool`
   writes it. Champions banned or already picked are removed. If
   fewer than 2 are left (`MIN_OPTIONS`; autofilled, or no pool set), the list is topped up
   with my most-played champions in that role (champion mastery from the client, bucketed into
   roles by role rates), then, if still short, with up to 3 champions that are strong this
   patch and low difficulty (CommunityDragon's difficulty rating), labelled "outside your pool".
2. **Opponent known** (my lane opponent locked, by the role guess; for jungle, the enemy
   jungler): rank by the shrunk matchup rate `p_hat` against them and give the band
   (favorable / even / soft / hard counter) with games. There's no fallback to traits here: a
   pairing without enough games gets outlook `unknown`, reads "no reliable numbers into
   <opponent>", and ranks after the options with numbers, in comfort order.
3. **Opponent not locked yet** (blind): rank by safety, meaning the share of that role's common
   opponents this patch that are a hard counter, plus the champion's own shrunk win rate.
4. **Tiebreakers and reasons**: a more comfortable champion ranks first unless the other scores
   better by more than `COMFORT_MARGIN` per star of difference (1 point of win rate, a constant
   in `scout/picks.py`; with equal stars, 1 point, and the list order decides). Reasons can
   add team needs (damage split, frontline, engage) and synergy with locked allies, never more
   than one line per option.
5. **Wording**: options with reasons, never "pick X" (`POLICY.md`: highlight decisions, don't
   dictate). Example: "Lee Sin: favored into Elise (52% over 3,000 games) · Amumu: even ·
   Elise: slight disadvantage, but your main".
6. **Updates** as enemies lock and as the role guess firms up; stops at my lock.
7. **Off-pool lock**: the report works the same and notes "<champion> isn't in your <role>
   pool (the Champions button adds it)" (only when that role's list isn't empty).

As built (M9b): candidates come from the pool (step 1), then champion mastery
(`/lol-champion-mastery/v1/local-player/champion-mastery`, up to 5 per role, bucketed by OP.GG
role rates of at least 25%), then champions among the role's 60 most played with Riot
difficulty 1 and OP.GG tier 1-2 in the role. Blind safety and the score: `DECISIONS.md` #52.
`scout watch` re-renders the options whenever their text changes and fetches each candidate's
matchup table (one guide each) in the background.

Since M14 each champion in the pool has 1-5 comfort stars (`DECISIONS.md` #65); since M22 each
League account on the PC keeps its own list (step 1).

**The whole team (M18).** Each option's score adds, DraftGap-style, how much better or worse
than expected the champion does with each locked ally: OP.GG's synergy tables, shrunk toward
the pair's expected rate (`expected_duo`, `synergy_prior_games`), summed over allies
(`DECISIONS.md` #79). One table per locked ally (that ally with every champion in my role)
covers all candidates, so a draft costs at most four synergy calls. A pairing is named when it
moves the rate by 1 point or more and has enough games to show: "pairs well with your Leona
(together 55% over 900 games)". Team-fit reasons (up to two), from sourced facts only:
knock-ups (the wiki) for an ally whose ultimate needs airborne targets (Riot's text), our
damage mix (Riot's damage types), a frontliner or crowd control the team lacks (Riot's
ratings: High). The drafted `anti_auto` and `engage` count only on rows the owner has reviewed
(`reviewed=y`, or `source=owner`). Not covered yet: "bad into their comp" (for example a champion weak into a
mostly magic-damage team) needs matchup data across roles, which OP.GG's tools don't give.

## Tests
- Synthetic matchup rows covering each band, with and without `specific`, and with thin samples
  (verdict must fall back to structure or unknown).
- Pick-order fixtures: opponent before me, after me, and a recorded session where a trade
  happened in finalization.
- A role-uncertainty fixture where the verdict flips between alternatives.
- 20 real recorded champ selects hand-labelled by the owner for the acceptance check in `SPEC.md`.
