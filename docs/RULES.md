# RULES: the engine and how to extend it

## Why rules live in YAML
Generic League knowledge ("ranged top vs melee top", "invade a weak early jungler") is written
once as data, with conditions the code can check. The engine decides which rules apply to a
game; the writer only sees rules that fired. When a report is wrong, the rule ID points at the
exact line to fix.

Rules read **insights** (computed in Python, see `ROLES.md`) and **traits/facts**. Anything that
ranks or scores (best gank, biggest threat) is an insight, not a rule.

The live file is `scout/rules/league_rules.yaml`: the prototype's rules converted to the format
below, the role packs from `ROLES.md` (M5), and rules added since. `scout doctor` prints the
current count.

## Rule format
```yaml
- id: TOP-RANGED-INTO-US          # stable UPPER-KEBAB id, never reused or renamed
  scope: lane                     # lane | map | team | champ | ally | pair | counterpick
  lanes: [top]                    # lane scope only; default all lanes
  audience: [top, jungle]         # roles that can see it; default depends on scope (below)
  section: your_lane              # report section key, or a per-role map (below)
  priority: 80                    # 0-100, higher shown first; default high=70, med=50
  confidence: high                # high = near-universal | med = usually true (default med)
  when:                           # ALL must be true; at least one
    - [us.range, ==, melee]
    - [them.range, ==, ranged]
  say: "{them} is a ranged top against melee {us}. ..."
  excludes: [LANE-WINNING]        # optional: should never fire with these for the same lane
                                  # (checked by a test, not enforced at runtime)
  tests:                          # required: one context that fires, one that doesn't
    fires: {us.range: melee, them.range: ranged}
    not:   {us.range: melee, them.range: melee}
```
Per-role sections, when the same advice belongs in different places:
```yaml
  section: {jungle: lanes_in_trouble, default: your_lane}
```

**Ops**: `== != >= <= > < in not_in has lacks has_any` (`in`: value is in a list; `has`: a set
contains the value; `lacks`: it doesn't; `has_any`: a set contains any value of a list). **Any comparison against a missing value (`None`) is false**,
including `!=` and `lacks`, so missing traits or stats can never make a rule fire.

**Section keys** (titles and order per role are in `ROLES.md`): `gank_first` (titled "Best
gank options"), `lanes_in_trouble`, `enemy_jungler`, `start_objectives`, `your_lane`,
`counterpick`, `punish`, `jungle` ("Junglers"), `map_threats` ("Watch the map"), `roams`,
`your_job`, `fights`, `protect_or_engage`, `watch_out`, `dont_feed`, `game_plan`. Every
laner's report also has `opponent` ("Know your opponent", between `your_lane` and
`counterpick`), but code fills it (`select.py`, `_opponent_items`: the lane opponents'
passives and Riot's tips against them), so rules can't use it as a section.

## Scopes, default audience, and context paths
| scope | runs | default audience | paths |
|---|---|---|---|
| lane | once per lane, from our side | the lane's roles + jungle | `us.*`, `them.*` (side aggregates); bot lane also `us.bot.*`, `us.support.*`, `them.bot.*`, `them.support.*`; `state.*`, `gank.*`, `threat`, `timeline.*`, `plan.*`, `reach.*`, `my_lane`, `stats.*` |
| map | once | jungle | `us.jg.*`, `them.jg.*`, `jg_diff`, `lanes.<top/mid/bot>.*` (each lane's `state`, `gank`, `threat`), `priority.side`, `gank_rank.us`, `gank_rank.them`, `roam.us.<mid/support>`, `roam.them.<mid/support>`, `my_lane` |
| team | once | everyone | `us.team.*`, `them.team.*`, `early_diff`, `scaling_diff` |
| champ | once per enemy champion | everyone | `them.*` incl. `role`, `feed_rank`, `confidence` |
| ally | once per allied champion | everyone except that champion's own player | `us.*` incl. `role`; `team.n_frontline_others` |
| pair | every ordered pair on the same team, both teams | everyone | `a.*`, `b.*` (incl. `role`), `team` (`us`/`them`), `stats.synergy_*` |
| counterpick | once, my champion vs my lane opponent (when known) | me only | `outlook`, `specific`, `label`, `picked_after_me`, `p_hat` (percent), `games`, `source` (`opgg|structure|none`), `me.*` (incl. `me.role`), `opp.*`; placeholders `{me}`, `{opp}` (`COUNTERPICK.md`) |

Pair rules about our own team (`team: us`) whose section is `watch_out` go to a section for
our plan instead (`select.py`, `ALLY_COMBO_SECTION`): support Protect or engage, bot Fights, top
Your job, jungle and mid Game plan.

`audience: their_lane` (champ and ally scope only): that champion's lane, plus the jungler. Used
for advice that only matters to whoever faces the champion (e.g. "no dash, a pick target").
For lane scope, an explicit `audience` is intersected with the lane's roles plus jungle.

Champion paths (`us.bot.*`, `them.*` in champ scope, `a.*`, ...): `early engage cc escape scaling
roam waveclear frontline spikes tags style range attack_range move_speed range_varies classes
damage_type reviewed spells`. `range_varies` is true when the base attack range contradicts the
range type (Gnar, Jayce: their range changes with form), so numeric range rules skip them.
`spells` is the champion's summoner spells (lowercase names, e.g. `ignite`, `teleport`): known
for allies in champ select and for enemies from the loading screen, missing until then, so
spell rules can't fire on a guess.

Side aggregates in lane scope: `early`/`scaling` = mean; `engage`/`cc`/`roam`/`waveclear` =
max; `escape`/`range`/`attack_range`/`range_varies` = the lane's carry (the ADC in bot);
`frontline` = max; `tags`/`classes`/`spells` = union; `power` = mean early + max engage + 0.5 x
max cc.

Map paths also include every role on both teams (`us.<top|jg|mid|bot|support>.*`,
`them.<...>.*`), `invade_risk`, `priority.<lane>` (`us|them|even|unknown`), `priority.them_side`,
`gank_rank.us_score` (the gankability of our best target), `them_divers` (enemy divers and
assassins), `roam_target.us.mid` and `roam_target.us.mid_gank`, `skirmish.<lane>` (`us|them|even|unknown`:
who wins early fights there with both junglers), `path.start_side|target|counter` (the
suggested jungle route), and per lane
`lanes.<lane>.gank.on_them|on_us`, `lanes.<lane>.threat`, `lanes.<lane>.plan.kind`.

Lane insight paths: `state.verdict` (`winning|even|losing|unknown`), `state.diff` (our fight
score minus theirs), `state.volatility`, `state.prio` (`us|them|even`: who controls the waves
early), `state.fight` (`us|them|even`: who wins trades and all-ins), `state.label`
(`bully|push_edge|shove_respect|bait|pushed|survive`; missing when the pair has no label),
`state.range_mismatch` (top only, ranged vs melee), `state.source` (`traits|stats`),
`state.range_gap` (our carry's base attack range minus theirs), `gank.on_them`, `gank.on_us`,
`gank.our_rank` (1 = our jungler's best gank target), `gank.their_rank`, `threat`
(`low|med|high|unknown`, the enemy jungler's threat to our side),
`timeline.<l1_3|l3_6|post6|item1>` (`us|them|even|unknown`, who's favored in that phase),
`plan.kind` (`ask_gank|ask_cover|self_sufficient|danger|unknown`), `plan.phase` (when it
applies, e.g. `before 6`, `against their jungler`), `reach.them_count` / `reach.us_count` (how
many champions' `ult_join`/`global`/roam reaches this lane; names via placeholders), `my_lane`.

Team paths: `early`, `scaling`, `n_engagers`, `n_frontline`, `n_hard_cc`, `n_dive_threats`,
`n_<class>` for each Riot class, `damage.physical`, `damage.magic`, `damage.mixed`, `archetype`
(`engage|poke|pick|split|protect|mixed`).

Stats paths (nullable; filled only when the sample reaches `stats.min_games_display`): lane
`stats.matchup_wr` (our laner's shrunk win rate in percent; bot lane = the ADCs),
`stats.matchup_games`, `stats.matchup_delta` (points vs the expected result),
`stats.lane_advantage` (`us|them|even`, OP.GG's label); pair `stats.synergy_wr`,
`stats.synergy_games` (the bot duo). Rules using stats must also check games, e.g.
`[stats.matchup_games, ">=", 500]`.

Placeholders in `say`: lane `{lane} {us} {them}` plus `{phase}`, `{plan_why}` (the jungle
plan's reasons), `{reach_them}` / `{reach_us}` (champion names), and `{us_range}`,
`{them_range}`, `{range_gap}` (attack ranges from the data); map `{us_jg} {them_jg}
{gank_lane} {their_gank_lane} {prio_side} {us_mid} {us_support} {them_mid} {them_support}
{dive_threat} {mid_roam_lane}`, plus `{<top|mid|bot>_fight_<us|them>}` (the champions in that
lane's early skirmish, e.g. "Illaoi + Lee Sin"); champ `{name} {role} {scaling_data}`
(`{scaling_data}` is OP.GG's game-length line in parentheses with a leading space, or empty);
ally `{name} {role}`; pair `{team} {a} {b}`; counterpick `{me} {opp}`.

Renamed from the prototype: scope `jungle` is now `map`; `us.adc`/`us.sup` are now
`us.bot`/`us.support`; `cls` is now `classes` (a set: use `has` / `has_any`); `diff`,
`volatility` and `range_mismatch` moved under `state.`; `lanes.<lane>.diff` is now
`lanes.<lane>.state.diff`; `CHAMP-GLOBAL` became `MAP-GLOBAL-THEM`.

## Validation at load (`rules/engine.py`)
The engine refuses to start, listing every problem, if any rule has:
- an id that isn't UPPER-KEBAB (`LANE-WINNING`), or a duplicate id;
- a key outside the format above;
- an unknown scope, section, role or op; a per-role section map without `default`, or with a
  key that isn't a role;
- `lanes` outside lane scope (or a value that isn't a lane); `audience: their_lane` outside
  champ and ally scope;
- `confidence` other than `high` or `med`; a `priority` that isn't a whole number 0-100;
- no `when` condition, a condition that isn't `[path, op, value]`, a path that isn't in its
  scope's schema, or a non-list value for `in`, `not_in` or `has_any`;
- an empty `say`, or a placeholder its scope doesn't fill;
- a missing `tests` block (both `fires` and `not`), or a test path outside the schema;
- `excludes` pointing at an unknown id.

The schema of allowed paths per scope lives in `rules/context.py`, next to the code that builds
the contexts, so they can't drift.

## Writing `say`
- Our side's point of view, plain language, short.
- **Options with reasons, not commands.** "Consider covering bot early: their lane wins level 2"
  rather than "Go bot". Riot's policy allows highlighting decisions with choices, not dictating them.
- No numbers except placeholders. No item names. No cooldown claims (those come from data).
- Generic timing only ("before their first clear ends"), never clock times.

## Adding a rule (checklist)
1. Pick the scope and the narrowest condition that captures the idea, using existing paths. If
   you need a new path, add it to `rules/context.py` (builder + schema) and to the tables above.
2. Choose `audience` and `section` from `ROLES.md`.
3. Write `say` per the rules above.
4. Fill `tests.fires` and `tests.not`. Only list the paths the rule depends on; the test helper
   (`engine.rule_test_values`) leaves every other path missing (`None`), so a condition on a
   path you didn't list is false.
5. If it must never fire with another rule, add `excludes`. A test checks this across the game
   fixtures; nothing stops both from firing in a live game.
6. Run `pytest`. If a golden game fixture now fires it, update that golden file on purpose.

## Tests
- **Per rule**: `tests/test_rules.py` loops over every rule and checks `tests.fires` fires and
  `tests.not` doesn't. Every rule has both by construction.
- **Golden games**: `tests/fixtures/games/*.yaml` with `tests/golden/<game>.<role>.yaml` listing
  the expected sections (exact, in order), rule IDs that must appear in that role's report,
  and rule IDs that must not (`tests/test_report.py`). Four of the game fixtures have goldens,
  and every role has at least two (`test_two_golden_games_per_role`). They use the frozen
  traits in `tests/fixtures/static/<version>/`, so reviewing traits doesn't break them.
- **Contradictions**: `test_excluded_rules_never_fire_together` (`tests/test_rules.py`)
  evaluates every game fixture and asserts that `engine.conflicts()` finds no two rules linked
  by `excludes` firing for the same lane. This is a test only: at runtime the engine doesn't
  check `excludes`, so both rules can be shown. Pairs linked today include
  `LANE-WINNING`/`LANE-LOSING`/`LANE-COINFLIP`/`LANE-EVEN`, `LANE-WINNING`/`TOP-RANGED-INTO-US`,
  `JG-STRONGER-US`/`JG-STRONGER-ENEMY`, `TEAM-WE-SCALE`/`TEAM-THEY-SCALE`.

## Tuning
When the owner says a report was wrong, the fix is usually one of:
- **Trait data wrong**: edit `data/manual/champion_traits.csv` (most common).
- **Insight formula off**: adjust the function in `scout/analysis/` and its tests.
- **Condition too broad**: tighten `when`.
- **Advice wrong or vague**: rewrite `say`.
- **Missing rule**: add one.
Always add the game as a fixture so it stays fixed. Once the post-game check exists (M10), check
the rule's hit rate in `data/history/rule_accuracy.csv` before and after.
