# Sidekick: what the pre-game report considers (for an outside review)

Written 2026-10-02, updated 2026-10-03, to ask another AI what we're missing. Self-contained:
no other file needed.

## 1. What it is
A personal Windows app for League of Legends (Summoner's Rift, draft and ranked queues). The
Sidekick app (one window, no command line) reads champion select from the local League client
and gives a **pre-game report for the role the player has** (top, jungle, mid, bot/ADC,
support). Players get filled, so all five roles matter. Code decides
everything; a small LLM (Claude Haiku) only rewrites the final report more briefly, using only
the facts it's given. The app also keeps a champion list per League account (1-5 comfort
stars), a History of past games and Settings, and keeps its data current by itself.

Hard limits (Riot's developer policies, and our own rules):
- **Pre-game only.** Nothing is computed from the game itself; no live advice, no tracked or
  counting timers, no "do X now". Static, sourced facts are fine (objective spawn times,
  cooldowns). Results built from pre-game data can finish arriving just after the game starts.
- **Options with reasons, never commands** ("consider covering bot early because...").
- **No player lookups in champ select.** Other players are only looked at on the loading screen,
  never if the game hides them (streamer mode). No skill ratings, MMR or Elo of our own. Each
  visible player's public OP.GG record on their champion is shown at loading: The owner's choice,
  after a first outside review read Riot's policy as discouraging showing other players' rank
  or win rate. It's a Settings switch, on by default.
- **No invented facts, no conclusions of our own.** Cooldowns, numbers, items and champion
  claims come from a named source (Riot, the LoL Wiki, OP.GG, Riot's match data); where none
  exists, the value is blank or a labelled draft. The LLM can't add facts, except a labelled
  "No data; AI read:" line for a pick with no data.
- Read-only access to the client. Never picks, bans or changes anything.

## 2. When it speaks
1. **While drafting** (before the player locks): 2-3 pick options for their role, from the
   logged-in account's list (best stars first), topped up from their most-played champions,
   then easy champions strong this patch, when fewer than 2 are available. Ranked by OP.GG's
   matchup win rate against the enemy in that role once locked (blind-pick safety before) plus
   OP.GG's synergy with each locked ally; a higher-rated champion stays first unless another is
   more than 1 point of win rate per star better. Reasons come from sourced team needs (damage
   mix, crowd control, knock-ups for a Yasuo, frontline).
2. **When all picks lock**: no report, just "picks locked" (one report per game, by the
   player's choice).
3. **Loading screen**: enemy roles confirmed (who has Smite, the positions shown), everyone's
   summoner spells, the players' records and likely duos, then the **one report**, written by
   Claude Haiku if the AI writer is on, and shown only once written
   (usually one call per game). Alongside: likely enemy duos (2+ of their last 20 ranked games
   together on the same team), one-tricks (top mastery 3x the next, or 1M+ points), and
   players' records. The written version waits up to 15 s for the records.
4. **After the game**: the post-game check fetches the match from Riot by the game's own id and
   grades every call the report made (section 4). The game goes to History.

## 3. What it knows (inputs)
**The draft**: 10 champions, the player's role, pick order (who locked after whom), bans, map
side (blue/red), our summoner spells (theirs at loading). Enemy roles are hidden in champ
select, so they're guessed from OP.GG's role play rates (all 120 role assignments scored),
then confirmed at loading.

**Riot static data** (each patch, 173 champions): every ability's name, Riot's short description
(passive included) and cooldowns; Riot's tips for playing as and against each champion;
melee/ranged; damage type; Riot's 1-3 playstyle ratings (damage, toughness, control, mobility,
utility) and difficulty; item names, costs and build depth (a finished item is depth 3).

**The LoL Wiki**: Riot subclass (13 labels, from juggernaut to specialist), positions,
base attack range and move speed, the last patch that changed the champion, and mechanic
categories (knock-up, pull, dash, blink, stealth, ...). Riot's own description of each class
(16 classes and subclasses; Riot never published one for Catcher and Specialist).

**Game facts** (12 lines, each with source and patch): objective and camp spawn times and role
quest rewards, from Riot's patch notes and the LoL Wiki, re-checked each patch (and after a
hotfix the wiki's patch page lists) by a research prompt.

**OP.GG stats** (default rank bracket; lane stats daily, matchups fetched during the draft):
- Per champion and role: games, win rate, pick/ban rate, role play rate, tier.
- **Matchup win rate with game counts**, shrunk toward what the two champions' overall strength
  predicts, last patch blended in early in a patch: the gap from expected separates "this
  opponent counters me" from "my champion is just weak this patch".
- Lane labels (early lane advantage, more solo kills, play style, a tip); the opponent's usual
  core build in this matchup; duo win rates; win rate by game length (under 25 to 40+ minutes).

**Measured by Sidekick from Riot's match data** (Emerald+ ranked solo, current and previous
patch, collected in the background, no player or game ids): per champion and role, gold, XP and
CS difference to the lane opponent at 10 and 15; share of minutes 3-10 on the enemy's half
(lane push); time to level 3 and 4 (a jungler's clear); first finished item; takedowns, roaming
takedowns, kill participation and deaths before 14:00; win rate. Used at 50+ games; a figure
that moved more than 3 standard errors since last patch (50+ games on both) is flagged.

**Role pools**: a champion counts in a role at 10%+ of its OP.GG games there. An off-role pick
gets no numbers or notes; the report says "no data" and the writer may add a labelled AI read.

**Champion values** (0-3, one row per champion), sourced where a source exists:
- `cc`, `escape`, `frontline` = Riot's control, mobility and toughness ratings (escape 0 = Riot
  says Low and the wiki lists no dash or blink; a frontliner is High toughness). Tags
  `airborne` and `stealth` from the wiki's categories, `needs_airborne` from Riot's text.
- `scaling` from OP.GG's win rate in 35+ minute games minus under 25 minutes.
- `early` (gold difference at 10), `waveclear` (lane push) and `roam` (roaming takedowns): the
  measured champion's quarter within its role (top quarter = 3), at 50+ games and 8+ champions.
- Still drafted by an LLM from Riot's text, none reviewed yet: `engage`, `spikes` (power-spike
  levels), jungle style (`ganker`/`farmer`), most tags (peel, disengage, dive, poke, sustain,
  ult_join, global, point_click_cc, split_push, invade_strong, ...), and three short notes
  (what to punish, what the ult does, when they spike). A row the player edits beats sources.

**Matchup briefs** (15 drafts, jungle pool, not reviewed yet): who's favored at levels 1-3,
3-6, after 6 and after first item, how to trade, what to ask the jungler.

## 4. What it computes (deterministic, before any LLM)
- **Lane read**, per lane (bot as one 2v2 unit):
  - *Priority* (who pushes early): waveclear (bot: the best plus half the other); a gap of 1.5.
  - *Fight*: trades (mean `early`, +0.5 for poke) + range (bot: +0.5 for 75+ more base attack
    range) + all-in (best `engage` + 0.5 x CC chain, the best CC plus half the next, +0.5 for
    Ignite or Exhaust). An out-pushed side's all-in counts half unless it can reach anyway
    (engage 3, point-and-click CC, dive, a catcher). A gap of 1.5 wins fights.
  - Together: bully or push edge = winning; shove-and-respect or bait = even; pushed or survive
    = losing. OP.GG's lane-advantage label, with enough games, decides instead (a disagreement
    with the traits goes to a review queue).
  - *Volatility* (someone dies early): each side's all-in + 0.5 x early - 0.5 x the other
    carry's escape; the bigger plus half the smaller; 4+ is volatile.
- **Lane timeline**: who's favored at levels 1-3, 3-6, after 6, after first item, from spikes,
  ult tags, scaling and the fight score; the shoved side isn't favored early. **Range** gaps
  between ADCs and in melee-vs-ranged top/mid lanes.
- **Gankability** of each side of each lane (escape, the laners' and jungler's CC, peel, lane
  lead, volatility), a gank ranking, and the **enemy jungler's threat** to our lanes.
- **Jungle plan per lane**: ask for a gank (and when: after the first clears), ask for cover,
  "can hold alone", or "danger: their jungler is coming".
- **Jungle matchup**: early 1v1, invade risk, styles, each jungler's likely first gank.
  **Priority**: which lanes move first, so which side (top or dragon) is ours. **Skirmishes**:
  early 2v2/3v3 fights by side. **Jungle path**: start opposite the first gank target.
- **Roams and cross-map threats**: mid/support roamers, ults that join, global ults, Teleport.
- **Team profile**: damage split, engagers, frontline, hard CC, divers/assassins, early vs late.
- **Threats**: a ranked "don't let get fed" list (early, scaling, class, carry role, dive).
- **Counter-pick verdict**: counter-picked / bad draw / weak this patch / even / you countered /
  favorable, with the win rate and games; alternatives if the enemy's role is uncertain.

**Checking the calls.** Each final report saves its calls, each with a measure: lane winner
(500+ gold ahead at 15), who has the wave (positions, minutes 3-10), lane kills and deaths
before 14:00 (4+ is high), our jungler's first kill lane before 10:00, jungle start side
(position at 2:00), the fed threat (24%+ of their gold or 3+ kills at 15), the long game. The
post-game check grades the player's games; the backtest grades stored Emerald+ games (each
side read as its jungler) against always guessing the usual outcome. A call's record reaches
the writer at 100+ graded calls; one that doesn't beat the usual result is stated as a lean.
First backtest (114 games, 2026-10-03): calling a lane for one side is right 57% (that side
wins about 36% of lanes). "Even" is right 17% (most Emerald+ lanes end 500+ gold apart at 15)
and "quiet" 32% (most lanes see 4+ kills and deaths by 14:00): those cut-offs don't fit yet.
Gank lane (37% vs 40%), jungle start and the fed threat are at the baseline. Nothing fitted yet.

## 5. The rules (94, YAML conditions on the computed values)
- **Lane** (42): each verdict and label (winning, losing, even, coin flip, bait, survive,
  shove-and-respect, shoved under tower, you shove them), Ignite/Exhaust on an engager, scaling
  lanes, ranged vs melee top/mid, assassin mid, short mid lane ganks, top alone early, ADC range
  gaps, kill lanes, level 2 race, engage into peel (both ways), mage support vs engage,
  enchanter vs mage, poke lanes, engage target (ADC with no escape), the laner's jungle ask, and
  the jungler's mirror view of each lane.
- **Map** (23): invade or not, jungle 1v1, enemy ganker/farmer, invade risk, which side for
  objectives, early 2v2/3v3 fights by side, mid roam threat and targets, support roams and peel,
  side lanes warned about a roaming mid or support.
- **Per enemy champion** (8): ult joins fights, global ult, Teleport, snowballers, no-dash
  carries, hard scalers, juggernauts, range that changes.
- **Allies** (2): split-push job, our ult joins fights. **Combos** (2): knock-up into ult, CC
  into a dash.
- **Team** (9): who scales, who's stronger early, no engage, their engage, two assassins, dive
  threats, damage skew (armor or magic resist worth more).
- **Counter-pick** (8): how to play a hard/soft counter, jungle versions, "they picked it after
  you", "the matchup isn't the problem", "you countered them", "you out-scale them".

## 6. The report, by role
- **Jungle**: Best gank options, Lanes in trouble (every lane at a glance), Enemy jungler (with
  Riot's passive and tips), Start and objectives (route, spawn timers), Counter-pick, Watch out
  for, Don't let them get fed, Game plan.
- **Top / mid / bot / support**: Your lane (timeline, OP.GG labels, lane rules), Know your
  opponent (passive, Riot's tips against them), Counter-pick, Punish, Junglers (threat to you,
  what to ask, other lanes), then role specifics: top Watch the map and Your job later, mid
  Roams and the map, bot Watch the map and Fights, support Roams and the map and Protect or
  engage; then Watch out for, Don't let them get fed, Game plan. The written report adds Players.
- Max 3 items per section (4 for Lanes in trouble, Junglers, Know your opponent; 1 for a laner's
  Watch out for and Don't let them get fed). The written version aims for about 120 words (150
  for jungle). The dashboard shows it on one page, with a Both teams panel (all ten kits in
  Riot's words, ratings, tips, the wiki's mechanics, measured figures and changes).

**The writer receives** the sections (each item with its source and pre-formatted numbers);
facts for all ten champions (role, class, range, Riot's ratings, wiki mechanics, game-length
data, measured figures, "no data" for off-role picks, summoner spells, the drafted notes and
whether they're reviewed, the whole kit in Riot's words, cooldowns for the player and their lane
opponents, Riot's tips); the counter-pick block; Riot's class definitions; the game facts;
track records; players' records. A validator rejects any number, item or ability name not in
the input.

Example (support, the shove-lane test game `bot_shove`, rules version as of 2026-10-03, trimmed):
```text
YOUR LANE
- Who's favored: levels 1-3: them, levels 3-6: them, after 6: even, after first item: even. Why:
  Sivir/Seraphine clear waves much faster.
- Per OP.GG, Seraphine has the early lane and Seraphine gets more solo kills.
- Bot: Sivir/Seraphine push and win the fights (Kog'Maw/Braum behind on both). Options: give up
  some CS rather than health, don't contest the wave, and expect help only after the junglers'
  first clears, best when the wave crashes into your tower.
KNOW YOUR OPPONENT
- Riot's tip against Sivir: Sivir is a powerful pushing champion, so leaving her unattended in a
  lane for too long will often result in your turrets being destroyed.
COUNTER-PICK
- Braum vs Seraphine: even (game win rate 51% over 2,229 games).
JUNGLERS
- Consider asking your jungler for a gank around levels 3-6: Sivir has no escape; Braum has CC
  to follow up.
```

## 7. What we know it doesn't model (yet)
- **Farming**: CS and gold difference at 10/15 are measured and quoted, and lane push sets
  waveclear. Nothing on how hard last-hitting is in a matchup, freezing/slow-pushing, recall
  timing, or tower-farming.
- **Passives and kit mechanics**: Riot's text and the wiki's categories reach the LLM, but the
  formulas don't model stacking damage, healing, shields, execute, resets, conditional power,
  sustain and anti-heal, tank shredding, true or %HP damage.
- **Summoner spells**: Ignite/Exhaust add to an all-in, Teleport has a rule, Smite confirms the
  jungler. Heal, Barrier, Cleanse and Ghost reach the writer but no rule uses them.
- **Runes** and builds beyond the opponent's usual core: not used. Enemy runes at loading
  (Riot's Spectator-V5) are planned, not built.
- **Map**: the side is known and shown, but side-specific map facts aren't used. Objectives are
  only "which side has priority" plus static spawn timers. Vision and wards: generic only.
- **Fights**: poke vs dive vs front-to-back only partly (engage, frontline, dive counts); no
  burst vs sustained damage. "Bad into their comp" (one role against another) has no source yet.
- **Jungle**: time to level 3 and 4 is measured and quoted, but the jungle formulas don't use
  clear speed yet. No leash, scuttle timing, or camp steal risk beyond `invade_strong`.
- **Rank**: OP.GG's default bracket; measured data is Emerald+. Neither follows the player's
  own rank.
- **The weights are first guesses**: the backtest exists, but fitting (gold at 15 and lane push
  as outcomes) waits for a few thousand stored games.
- **Drafted values**: engage, spikes, style, most tags and the notes are unreviewed LLM drafts.
- **A miss found in testing** (fixed): champion traits said Kog'Maw/Braum win lane, but
  Sivir/Seraphine push them under tower all lane. The lane formula ignored wave control; the
  first outside review led to the Priority x Fight read and bot as one 2v2.

## 8. Questions for you
1. **What game-deciding factors are we still missing**, for each role (top, jungle, mid, ADC,
   support)? Rank them by how much they change the outcome or how the player should play.
2. For each: **can it be sourced or measured** (Riot's ability text and ratings, the wiki's
   categories, OP.GG's fields, or Riot's match timelines: positions and gold each minute, kills,
   items, levels, wards, objectives), or would it need a drafted note? Give the exact measure.
3. **Lane read**: with measured gold at 10/15 and lane push as outcomes, how should Priority and
   Fight be weighted and fitted? What should "even" and "quiet" mean at Emerald+?
4. **Which current rules or formulas are wrong or risky** as general advice?
5. Which drafted values (engage, power spikes, ganker/farmer, peel, dive, poke) could come from
   match data or a reputable source instead?
6. **What would a coach say first** in the 30-60 seconds of a loading screen, per role? Is our
   section order and length right?
7. Are our **grading measures** (section 4) right for each call? What else should be graded?
8. Anything **Riot's policy** would forbid among your suggestions, or in what we do now
   (players' records especially)? Flag it.
