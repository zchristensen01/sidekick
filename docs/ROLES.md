# ROLES: what each role's report needs

The prototype only really worked for jungle. This doc is the spec for all five roles: how roles
map to lanes, the shared insights every report draws from, the sections each role gets, and the
role-specific rules and traits needed to fill them.

## Roles and lanes
Five roles, three lanes. Internal names everywhere: roles `top, jungle, mid, bot, support`
("bot" means the ADC / marksman role) and lanes `top, mid, bot`. The bot lane has two players.

| My role | My lane | Primary lane opponent | Also in my lane |
|---|---|---|---|
| top | top | enemy top | |
| jungle | none | enemy jungle | all three lanes matter |
| mid | mid | enemy mid | |
| bot | bot | enemy bot | enemy support (it's a 2v2) |
| support | bot | enemy support | enemy bot (it's a 2v2) |

- The League client (LCU) uses `top, jungle, middle, bottom, utility`. The mapping lives in
  `scout/model/roles.py` (`LCU_POSITION_ROLE`, `role_from_lcu`), called at the edge by
  `scout/lcu/champselect.py` and the recorder; the LoL Wiki's position labels (`middle`,
  `bottom`) are mapped in `scout/data/wiki.py`. Nothing else ever sees these names.
- `scout/model/roles.py` also holds the enums and the `ROLE_LANE` / `LANE_ROLES` mappings.
  Code that needs "my lane" calls `lane_of(role)`; never compare a role string to a lane string
  (that was the prototype bug that gave supports and ADCs an empty report).

## Shared insights (computed in `scout/analysis/`)
Insights are computed once per game in tested Python, not in YAML. They rank and score things,
which yes/no rules can't do. Every insight carries `reasons` (short machine-readable strings)
so the report can say *why*. Rules (see `RULES.md`) read insight values as condition paths.

| Insight | Answers | Main inputs |
|---|---|---|
| `lane_state[lane]` | Who controls the waves early (priority), who wins trades and all-ins (fight), the verdict and label that follow, and how volatile the lane is | traits (early, engage, cc, waveclear, escape, tags), classes, base attack range in bot, summoner spells once known, stats when the sample is big enough (`STATS.md`) |
| `gankability[lane][side]` | How easy it is to gank one side of a lane | target escape and peel, the laners' CC follow-up, lane state |
| `jungle_threat[lane]` | How dangerous the enemy jungler is to *our* side of a lane, after counting our jungler's ability to counter-gank | enemy jungler early/cc/style, our laners' escape and peel, lane state |
| `jungle_matchup` | Early 1v1, invade risk, both styles, each jungler's likely first gank side | jungle traits and tags, lane priority |
| `priority` | Which lanes can move first, so which side of the map (top or bot/dragon) has priority | lane states, waveclear |
| `roam[side]` | Mid and support roam threat, and the best roam targets | roam and waveclear traits, side-lane gankability |
| `team_profile[side]` | Damage split (physical/magic), engage count, frontline, hard-CC count, comp type, early vs late | traits, damage type and class (static data), game-length stats |
| `threats` | Enemy combos and the ranked "don't let get fed" list | pair rules, snowball potential, scaling, role impact |
| `lane_timeline[lane]` | Who's favored at levels 1-3, 3-6, after 6, after first item, and why: when to trade, when to back off | traits (early, spikes, scaling, ult tags), lane-advantage label, game-length rates |
| `jungle_plan[lane]` | What a laner should tell their jungler: `ask_gank` (and when), `ask_cover` (before which spike), `self_sufficient`, or `danger` | lane timeline, gankability, jungle threat, our jungler's likely side |
| `cross_map[side]` | Enemy (and our) champions whose ult or roaming reaches other lanes (`ult_join`, `global`, high `roam`), which lanes, from when | traits and tags |
| `expected_items[lane]` | The enemy laner's usual first core items in this matchup | OP.GG matchup builds, Data Dragon item names (M8) |
| `counterpick` | Was I counter-picked, how bad, how to play it | `COUNTERPICK.md` |
| `skirmishes[lane]` | Who wins early 2v2/3v3 fights where a lane meets both junglers (mid: river and scuttle; bot: dragon side; top: top side) | the lane's players plus each jungler: mean early + max engage + 0.5 x max cc, 1 point to win |
| `jungle_path` | A suggested route: start on the side opposite the first gank target so the clear ends next to it; a volatile lane nearly as gankable wins the target; where their jungler most likely shows first (counter-gank) | gank ranking, lane volatility, priority, their likely first gank |
| lanes at a glance | Every lane's verdict in one line ("Top even; Bot they win early, you scale (volatile)"): the first item in the jungler's Lanes in trouble (jungler only) | lane states and timelines |

Formulas as built (`scout/analysis/lanes.py`, `scout/analysis/ganks.py`; tune them with
post-game data, M10):
- **One side of a lane** (bot lane counts as one unit): `push` = `waveclear` (bot: the best
  pusher plus half the other, kept on the 0-3 scale); `trade` = mean `early`, +0.5 if anyone
  has the `poke` tag; `allin` = max `engage` + 0.5 x the CC chain (best `cc` + half the next),
  +0.5 with Ignite or Exhaust; `reach` = someone can start a fight without priority (`engage`
  3, the `point_click_cc` or `dive` tag, or the catcher class). The lane is `unknown` when a
  champion's traits are missing or a pick isn't known.
- **Priority** (`state.prio`): a `push` difference of 1.5 or more gives that side the waves;
  otherwise even.
- **Fight score** (one side): `trade` + range edge + access x `allin`. Range edge (bot only):
  +0.5 for the ADC with 75+ more base attack range, none if either ADC's range changes with
  form. Access: 1, or 0.5 when the other side has priority and this side has no reach. `diff`
  = our fight score minus theirs; `state.fight` is ours at `diff >= 1.5`, theirs at `<= -1.5`,
  otherwise even.
- **Verdict and label** come from the (priority, fight) pair, in the table below. With even
  priority there's no label and the fight alone decides the verdict.
- **Volatility** (how likely someone dies early): each side's threat = access x `allin` + 0.5 x
  mean `early` - 0.5 x the other side's carry `escape`; volatility = the larger threat + 0.5 x
  the smaller. 4 or more is "volatile" (lanes at a glance, the jungle path, LANE-COINFLIP); 5.5
  or more is very volatile (JG-HOVER-VOLATILE-BOT).
- **Top lane, ranged vs melee**: sets `state.range_mismatch` and keeps the traits verdict. The
  lane-verdict rules (LANE-WINNING, -LOSING, -COINFLIP, -EVEN) skip that lane, and the range
  rules (TOP-RANGED-INTO-US, TOP-US-RANGED) speak instead.
- **Stats**: when every shown OP.GG lane-advantage label for the lane agrees (bot: the ADC and
  support labels), it decides the verdict (`state.source: stats`); a verdict opposite to the
  traits one becomes a warning, and in `scout watch` a review-queue entry (`STATS.md`).
- **Gankability** (us ganking them): `(3 - min target escape) * 1.5 + max ally-laner cc +
  0.5 * our jungler cc - 1.5 per target with the peel tag + 0.5 * max(0, lane diff)`, plus 1 if
  the lane's volatility is 5 or more (not the 4 that means "volatile" elsewhere).
- **Jungle threat** (them ganking us): the same formula with sides swapped, plus 1 if their
  jungler's `style` is `ganker`, minus 0.5 x our jungler's `early`. High at 6+, med at 4+,
  otherwise low; unknown when a trait is missing.

| priority \ fight | ours | even | theirs |
|---|---|---|---|
| ours | bully, winning | push_edge, winning | shove_respect, even |
| even | (no label) winning | (no label) even | (no label) losing |
| theirs | bait, even | pushed, losing | survive, losing |

Where the knowledge behind these comes from (ability text, champion and matchup briefs, items):
`KNOWLEDGE.md`.

## Report sections by role
Order matters: the writer keeps this order (`report/select.py`, `ORDER`). The selector sorts
each section's items by priority and keeps the top ones: 3 per section; 4 for Lanes in trouble,
Junglers and Know your opponent; for laners, 1 for Watch out for and Don't let them get fed.
The word budget is applied by the writer (its prompt and validator, `REPORT_AGENT.md`), not by
the selector. "Always" sections (`ALWAYS`) appear even when there's little to say ("Nothing
stands out here for this draft."); the others appear only when they have items.

### Jungle (about 150 words)
1. **Best gank options** (`gank_first`, always): our best gank target from the gankability
   ranking, plus the second-best when it's a real target (gankability 6+), with reasons; gank
   shapes from rules (a bait lane, a carry with no dash); our champions whose ult can join a
   fight (MAP-ULT-JOIN-US).
2. **Lanes in trouble** (always, up to 4): first every lane's verdict at a glance; then our
   lanes that lose early, and whether to cover them (play nearby to counter-gank) or skip them
   (they can't be helped early), and which lanes are fine alone (the mirror of each laner's
   jungle plan).
3. **Enemy jungler** (always): style, early 1v1, invade risk, their likely first gank (their
   gankability ranking of our lanes); the enemy jungler's passive and Riot's tips against them;
   the jungle matchup brief and OP.GG's numbers when there are any.
4. **Start and objectives** (always): which side has priority (top side or dragon side); start
   on the side opposite where you want your first gank, so your clear ends near it; objective
   and camp timers.
5. **Counter-pick**: whenever there's a jungle matchup verdict (both junglers known), even and
   unknown included.
6. **Watch out for** (up to 3): enemy combos, the enemy jungler's key note, enemy champion
   warnings (a juggernaut, a range that changes, a mid assassin), and enemy cross-map threats:
   ults that join fights (MAP-ULT-JOIN-THEM), Teleport (CHAMP-TP-THEM), global ults
   (MAP-GLOBAL-THEM).
7. **Don't let them get fed** (up to 3): the top two threats from the feed ranking and why,
   plus the snowball and late-carry rules.
8. **Game plan** (always): one line.

### Top (about 120 words)
1. **Your lane** (always): the lane timeline (who's stronger at 1-3, 3-6, after 6, after first
   item), when to trade, ranged vs melee, items to expect.
2. **Know your opponent** (`opponent`, up to 4): the opponent's passive and Riot's tips against
   them, in Riot's words. Filled by code, not rules.
3. **Counter-pick**: the verdict vs the enemy top.
4. **Punish**: the opponent's key ability and what to do while it's down.
5. **Junglers** (always, up to 4): the enemy jungler's threat to top, whether your jungler is
   likely to play top side or bot side early, and the jungle plan (ask for a gank and when, ask
   for cover before their spike, or tell your jungler you're fine).
6. **Watch the map**: cross-map ults or roamers that can reach top (e.g. "after 6, check where
   Shen is before fighting"), and your own team's.
7. **Your job later**: split push or group, based on the comp (frontline count, `split_push` tags).
8. **Game plan** (always).

### Mid (about 120 words)
1. **Your lane** (always): lane timeline, when to trade, items to expect.
2. **Know your opponent** (up to 4): the enemy mid's passive and Riot's tips against them.
3. **Counter-pick**.
4. **Punish**.
5. **Junglers** (always, up to 4): both junglers path near mid; the jungle plan; invade help if
   mid can move first.
6. **Roams and the map**: the enemy mid's roam threat (warn side lanes when they leave), your
   best roam target (the most gankable side lane), and cross-map ults that change fights.
7. **Game plan** (always).

### Bot / ADC (about 120 words)
1. **Your lane** (always, as a 2v2): kill lane, poke lane, or farm lane; who wins level 2; the
   lane timeline; their engage vs your support's peel; items to expect.
2. **Know your opponent** (up to 4): both enemies' passives and Riot's tips against them.
3. **Counter-pick**: vs the enemy ADC.
4. **Punish**: the enemy support's engage tool and the window when it's down; the enemy ADC's
   escape.
5. **Junglers** (always, up to 4): bot side and dragon pressure, and the jungle plan.
6. **Watch the map**: cross-map ults and roamers that can join bot fights (e.g. a Galio or Shen
   ult), on both teams.
7. **Fights**: who threatens you in teamfights (divers, assassins, engage) and your peel.
8. **Game plan** (always).

### Support (about 120 words)
1. **Your lane** (always, as a 2v2 from the support's side): your engage options vs their peel,
   their engage vs your peel, the best engage target, the lane timeline.
2. **Know your opponent** (up to 4): both enemies' passives and Riot's tips against them.
3. **Counter-pick**: vs the enemy support.
4. **Punish**: the enemy support's key ability; an enemy ADC without a dash.
5. **Roams and the map**: when a mid roam is worth it (mid is gankable and our bot can hold
   alone); the enemy support's roam threat; cross-map ults that can join bot fights.
6. **Junglers** (always, up to 4): bot-side river and dragon, and the jungle plan.
7. **Protect or engage**: which enemy threatens your carry most, and your job in fights.
8. **Game plan** (always).

All roles add **Your notes** (from the user's own `matchup_notes.csv`) and **Warnings** when present.
Laners also get **Watch out for** and **Don't let them get fed** (one item each) before the game
plan. **Counter-pick** is never forced, for any role: it appears whenever my lane opponent (the
enemy jungler, for a jungler) is known, from OP.GG's numbers or, without them, a structural read
from traits (`COUNTERPICK.md`); an even or unknown verdict still shows.
For mid and support, `map_threats` items (cross-map ults) are shown inside **Roams and the map**
rather than as a separate section. The final report at the loading screen also gives the
writer a **Players** section (each visible player's OP.GG record, `REPORT_AGENT.md`).

## Role-specific rule packs
Rule IDs and intent to implement in `scout/rules/league_rules.yaml` during M5. Existing
prototype rules keep their IDs. Conditions use insight and trait paths from `RULES.md`.

| ID | Audience | Section | Fires when (sketch) | Says (intent) |
|---|---|---|---|---|
| LANE-WINNING / LANE-LOSING / LANE-COINFLIP | lane's players + jungle | your_lane / lanes_in_trouble | existing | existing |
| **LANE-EVEN** (new) | lane's players | your_lane | verdict even, priority even, not volatile | "Even early; the first jungler to show up decides it" |
| TOP-RANGED-INTO-US / TOP-US-RANGED | top, jungle | your_lane (jungle: gank_first, TOP-RANGED-INTO-US only) | existing | existing |
| **MID-RANGED-INTO-US / MID-US-RANGED** (new) | mid (+ jungle for MID-RANGED-INTO-US) | your_lane (jungle: gank_first) | melee vs ranged mid, neither changes range | "{them} outranges your melee {us} (550 vs 175)..." |
| **BOT-OUTRANGED / BOT-OUTRANGES-THEM** (new) | bot, support | your_lane | ADC attack ranges differ by 75+ | "Their ADC outranges yours (650 vs 525): they win free auto trades..." |
| **CHAMP-RANGE-CHANGES** (new) | their lane + jungle | watch_out | an enemy whose range changes with form or level | "the usual melee/ranged read doesn't hold all game" |
| **TOP-ALONE-EARLY** (new) | top | jungle | our jungler's gank ranking puts top last, enemy jungler threat to top is high | "Expect to be alone early; ward and play the wave safely" |
| **TOP-SPLIT-JOB** (new) | top | your_job | we have `split_push`, team has frontline elsewhere | "Your job later is side lane pressure" |
| MID-ASSASSIN / MID-GANK-SHAPE | mid, jungle / jungle | your_lane (jungle: watch_out) / gank_first | existing | existing |
| **MID-ROAM-THREAT** (new) | mid | roams | enemy mid `roam >= 2` and `waveclear >= 2` | "Their mid roams; ping your side lanes when they leave" |
| **SIDE-LANE-MID-ROAMER** (new) | top, bot, support | map_threats (support: roams) | same as MID-ROAM-THREAT | "Their mid roams to side lanes; play safe while they're missing" |
| **MID-ROAM-TARGET** (new) | mid | roams | our mid `roam >= 2`, a side lane's gankability is high | "Your best roam is <lane>" |
| BOT-KILL-LANE-THEM / BOT-KILL-LANE-US | bot, support, jungle | your_lane (jungle: lanes_in_trouble / gank_first) | existing | existing |
| BOT-ENGAGE-INTO-PEEL / BOT-THEIR-ENGAGE-INTO-OUR-PEEL | bot, support | your_lane | existing | existing |
| **BOT-POKE-LANE** (new) | bot, support | your_lane | enemy bot lane has `poke` tags, ours doesn't | "Poke lane; don't take free damage, all-in when they misuse a cooldown" |
| **BOT-LEVEL-2** (new) | bot, support | your_lane | both sides are kill lanes | "Level 2 race decides the lane; track wave 1" |
| **BOT-DIVE-THREAT** (new) | bot | fights | enemy has 2+ divers/assassins | "You're their target in fights; position behind your frontline" |
| **SUP-ENGAGE-TARGET** (new) | support | your_lane | our support `engage >= 2`, enemy ADC `escape == 0` | "Engage on the ADC, not the support" |
| **SUP-PEEL-JOB** (new) | support | protect_or_engage | our support has `peel`, enemy has divers or assassins | "Save your peel for <threat>" |
| **SUP-ROAM-MID** (new) | support | roams | our support `roam >= 2`, mid gankability high | "Mid is your roam target once bot can hold" |
| **SUP-ENEMY-ROAMER** (new) | support | roams | enemy support `roam >= 2` | "Their support roams; warn mid" |
| **MID-ENEMY-SUP-ROAMS** (new) | mid | roams | enemy support `roam >= 2` | "Their support roams; keep your side brushes warded" |
| **LANER-ASK-GANK** (new) | top, mid, bot, support | jungle | `plan.kind == ask_gank` | "Ask for a gank around <phase>: <reason>" |
| **LANER-ASK-COVER** (new) | top, mid, bot, support | jungle | `plan.kind == ask_cover` | "They spike at <phase>; ask your jungler to be nearby before then" |
| **LANER-SELF-SUFFICIENT** (new) | top, mid, bot, support | jungle | `plan.kind == self_sufficient` | "You can hold this lane; tell your jungler to play elsewhere early" |
| **LANER-DANGER** (new) | top, mid, bot, support | jungle | `plan.kind == danger` | "Their jungler is likely to look at you early and yours is likely on the other side; play safe until you see their jungler" |
| **MAP-ULT-JOIN-THEM** (new) | everyone (no `audience` key: the champ-scope default) | map_threats (jungle: watch_out; mid, support: roams) | enemy has `ult_join` | "After 6, check where <champ> is before committing to a fight; their ult can bring them in" |
| **MAP-ULT-JOIN-US** (new) | everyone except the champion's own player (no `audience` key: the ally-scope default) | map_threats (jungle: gank_first; mid, support: roams) | we have `ult_join` | "<champ> can join your fights after 6; fights near their ult timing are in your favor" |
| **MAP-GLOBAL-THEM** (new) | everyone | map_threats (jungle: watch_out; mid, support: roams) | enemy has `global` | "<champ> can reach you anywhere; back earlier when low" (replaces CHAMP-GLOBAL) |
| JG-* (existing) | jungle | various | existing | existing |
| **JG-INVADE-RISK** (new) | jungle | enemy_jungler | enemy jungler `invade_strong`, their mid and a side lane have priority | "Expect a level 1-2 invade; ward and start away from them" |
| ~~JG-START-SIDE~~ | jungle | start_objectives | replaced by the `jungle_path` insight | |
| **JG-RIVER-2V2-US / -THEM** (new) | jungle, mid | start_objectives / enemy_jungler (mid: jungle) | `skirmish.mid` | who wins early river and scuttle fights |
| **JG-BOTSIDE-FIGHTS-US / -THEM** (new) | jungle, bot, support | start_objectives / lanes_in_trouble (bot, support: jungle) | `skirmish.bot` | who wins early fights near bot and dragon |
| **JG-TOPSIDE-FIGHTS-US / -THEM** (new) | jungle, top | start_objectives / lanes_in_trouble (top: jungle) | `skirmish.top` | who wins early fights top side |
| **TEAM-DAMAGE-SKEW-PHYSICAL / -MAGIC** (new, two rules) | everyone | game_plan | 4+ enemies deal that damage type | "Mostly physical/magic damage: the matching defensive stat is worth more" |

## Traits these roles need
Added to `data/manual/champion_traits.csv` (definitions in `TRAITS.md`):
- `roam` (0-3): how much the champion can affect other lanes early.
- `waveclear` (0-3): how fast they can push a wave early, which gives lane priority.
- `frontline` (0-3): how well they absorb damage and stand in front in fights.
Damage type, class and melee/ranged come from generated static data, not traits.

## Role swaps, fills, and uncertainty
- **My role**: use `assignedPosition` from the final champ select session (role swaps during
  champ select change it). `scout report --role` overrides.
- **Ally swaps in chat**: allies' summoner spells are visible in champ select. A non-jungle
  ally with Smite is treated as the jungler, and the report notes "role swap detected". Read
  the Smite spell id from `summoner_spells.csv` (static data, built from Data Dragon's
  `summoner.json`), never hard-code it.
- **Enemy roles**: inferred; see the next section.
- **Draft modes only**: queues with positions are Normal Draft (400), Ranked Solo/Duo (420),
  Ranked Flex (440) and Clash (700). Others are skipped with a one-line message.

## Enemy roles and pick order
Two different questions with different answers: **when** each enemy champion was picked is
known for certain; **which role** each enemy plays is hidden in champ select and must be guessed.

### What champ select shows about the enemy team
| Visible | Hidden until the game loads |
|---|---|
| Each champion once it's locked, and the draft turn it was locked in (`actions`) | Their positions (`assignedPosition` is `""`) |
| Their bans | Their summoner spells (so no Smite check), hovers, names |

### Pick order (known, `LCU.md` section 4)
The session's `actions` list is the whole draft in order, enemy turns included; each completed
`pick` action holds the champion locked. For any champion: find its pick action **by champion
id** and take its turn index. `picked_after_me = their_turn > my_turn`. Ally and enemy picks
never share a turn. Edge cases:
- **Trades** (champion swaps during finalization): matching by champion id gives the turn the
  champion was locked, which is when the other team saw it. If I traded for my champion, "my
  turn" is the turn my final champion was locked. [verify on a recorded trade: whether the
  client rewrites the action's champion id; matching by id works either way]
- **Not locked yet**: during drafting, an enemy without a completed pick has no turn yet.

### Enemy roles (guessed, `scout/analysis/role_inference.py`, built in M4)
1. **Role rates**: how often each champion is played in each role this patch (Elise almost
   always jungle; Gragas split across several roles). From OP.GG from M8; until then the LoL
   wiki's position lists (a rough prior: equal weight on each listed position).
2. **Whole-team assignment**: try all 120 ways to give the 5 enemy champions the 5 roles.
   Score each by multiplying the champions' rates for their roles, with a floor (0.5%) so an
   off-role pick is unlikely but possible. Normalize so the scores sum to 1. The top one is the
   guess; its score is the confidence. This is why one flex pick usually resolves: if they
   have Lee Sin, Gragas isn't their jungler.
3. **Per-role answers**: for each role, the probability that each champion plays it (sum of
   the scores where they do). The report says "Their jungler: Elise" when that's above
   `roles.low_confidence_below` (0.6), and "Their jungler: Gragas or Sejuani (55% / 40%)"
   below it, with both readings when they change the advice ("if Gragas is jungle: ...").
4. **Partial teams** (draft helper, M9+): with only some enemies locked, assign the locked
   champions to roles the same way (fewer combinations); the open roles stay "not picked yet".
   "Has their jungler picked?" = is any locked champion's jungle probability high.
5. **The report runs at finalization**, when all 5 enemy champions are locked, so the full
   method always applies there.

### Checking the guesses
- **Answer key from every recorded game**: when the game starts, `scout record` (and later
  `scout watch`) saves the roster the game shows at loading: each player's champion, position
  if the client gives it, and summoner spells, with no identities (`LCU.md` section 7). Smite
  marks the real jungler. A test compares the role guesses with it on every recording; the
  target is `SPEC.md`'s 90% of fixtures. [verify on the first recorded game: whether enemy
  positions are filled in, or only spells]
- **Post-game** (M10): Riot's match data gives every player's real position; wrong guesses go
  into the accuracy table.
- **Loading-screen confirmation** (M6, core): nothing is shown as a report in champ select
  (one report per game, 2026-10-03). When the game-start roster shows who has Smite (and
  positions, if the client fills them in), the watcher confirms or corrects the enemy roles and
  builds the report, marked "confirmed" (or "corrected: their jungler is Zac, not Gragas"),
  and the LLM writes it with the players' records and likely duos in it. If stats were still loading, it's re-rendered once more when they
  arrive, still as the final report. This uses only pre-game data; nothing is computed from
  the game itself.
