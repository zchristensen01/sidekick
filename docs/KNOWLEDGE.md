# KNOWLEDGE: what the report knows about champions and matchups

A good report needs more than "this lane is losing". It needs to know what each champion's key
abilities do, how ults like Shen's or Galio's let them join a fight in another lane, which
levels and items make a champion dangerous, when you're the stronger one and should trade, and
when to ask your jungler for help or tell them you're fine. This doc says where each piece of
that knowledge lives, where it comes from, and how it stays correct.

The rule from CLAUDE.md still holds: **no League facts invented in code or prompts.** Every piece
of knowledge below is either data from a source (Riot's ability text, OP.GG builds) or a written
judgment that the owner owns and reviews. The writer only sees what's in its input.

## The four layers
| Layer | Example | Lives in | Written by | Kept current by |
|---|---|---|---|---|
| 1. Ability facts | Shen's ult name, Riot's description of it, its cooldowns per rank | `data/generated/static/<v>/abilities.csv` | Data Dragon (Riot's own text) | every patch, automatically |
| 2. Champion brief | "Shen R shields an ally anywhere on the map and teleports him there after a delay. After his 6, check where he is before fighting in any lane." | `data/manual/champion_traits.csv` (text columns) | drafted from layer 1 by an LLM, reviewed by the owner | review queue when abilities change |
| 3. Matchup brief | Darius vs Teemo, top: who's stronger at 1-3, 3-6, after 6, after first item; how to trade; what to ask the jungler | `data/manual/matchup_briefs.csv` | drafted from layers 1, 2 and 4 in a Claude Code session, reviewed by the owner | `brief_stale` in the review queue when either champion's kit changes or OP.GG's lane advantage flips |
| 4. Matchup data | 47% over 4,140 games; "lane advantage: Elise"; the enemy's usual core build vs you; OP.GG's one-line tip | `data/generated/stats.sqlite` | OP.GG | lane stats daily (`stats.max_age_hours`); matchup tables, labels and builds kept 72 hours (`stats.matchup_max_age_hours`) (`DATA.md`) |
Plus the owner's own `matchup_notes.csv`, shown verbatim as "Your notes".

**Sourced facts beside the layers (M15):** Riot's playstyle ratings and the LoL Wiki's
mechanic categories per champion (`champion_meta.csv`: `rating_*`, `mechanics`), and game
facts (`data/manual/game_facts.csv`: objective and camp timers, role quest rewards, one cited
line each, from Riot's patch notes or the wiki). The jungler's "Start and objectives" shows
the timers as static pre-game facts (never live timers); the writer gets the timers and the
player's own role quest under `game_facts`, and each champion's `riot_ratings`,
`wiki_mechanics` and `game_length_data`. `docs/PATCH_UPDATE.md` says how each is kept current.

## Layer 2: champion briefs (columns in `champion_traits.csv`)
Besides the 0-3 scores (`TRAITS.md`), each champion row has short text fields, one or two
sentences each, in plain language, no numbers unless they're in `abilities.csv`:
| column | answers | example shape |
|---|---|---|
| `key_note` | the ability that matters most in lane and how to punish it | "<ability> is her only escape; trade or gank right after she uses it" |
| `ult_note` | what the ultimate does to the map and to fights, who it threatens, how to play around it | "<ult> lets him join a fight anywhere after a short delay; check where he is before diving" |
| `spike_note` | when they get strong, in words (levels from `spikes`, items in general terms) | "Big jump at 6; dangerous again once their first damage item is done" |
Cross-map threats are marked with tags (vocabulary in `TRAITS.md`): `global` (map-wide damage
or reach) and `ult_join` (ult brings them into a fight in another lane, e.g. Shen, Galio), plus
the `roam` score.

Drafting: `scout draft-traits` (or Claude Code in a session, at no API cost) drafts these from
the champion's Riot ability text. Every drafted row is `reviewed=n` and flagged in reports until
The owner accepts it.

## Layer 3: matchup briefs (`data/manual/matchup_briefs.csv`)
One row per (role, champion, opponent), written from my champion's side. Short sentences.
| column | answers |
|---|---|
| role, champ_id, opp_champ_id | the matchup |
| levels_1_3 | who's stronger, how to play the first levels |
| levels_3_6 | how it changes before ultimates |
| after_6 | how ultimates change it |
| first_item | how the first completed item changes it |
| trade_pattern | when to trade and when to back off (e.g. "trade when <ability> is down") |
| jungle_ask | what to ask the jungler: a gank and when, cover before a spike, or "I'm fine, play elsewhere" |
| reviewed, reviewed_patch, source, notes | same meaning as in traits |

As built (M9, `scout/data/briefs.py`): `levels_1_3` starts with `Favored:`, `Even:` or
`Unfavored:` (from my side) so the validator can compare it with OP.GG's lane-advantage label.
Every text column is required, at most 240 characters; numbers must appear in either
champion's ability text (or be levels); no item names. `source` is `owner`, `llm` or
`claude-code`. In the report a brief replaces the computed lane timeline: levels 1-3 and 3-6
in one line, trading, after 6 and first item, and `jungle_ask` under Junglers (laners) or Enemy
jungler (jungle). Unreviewed briefs show with medium confidence and a warning. A row that fails
the basic checks is skipped in reports. `scout doctor` checks the whole file, including the
lane-advantage check below; `scout refresh` queues `brief_stale` (see Keeping them current).

How they get written:
1. **In a Claude Code session.** There's no brief-drafting command. Briefs are drafted in a
   session (no API cost) and appended with `scout.data.briefs.append_briefs`, which adds rows at
   the end of the file and refuses a (role, champion, opponent) that's already there. It
   doesn't validate, so run `scout doctor` after appending.
2. **Champ pool first.** For each of the owner's pool champions, briefs against the most common
   opponents in that role (from `lane_stats`). So far: 15 jungle briefs, Lee Sin, Elise and
   Amumu against each one's 5 most-played opponents (`DECISIONS.md` #51).
3. **Inputs to the draft**: both champions' ability text and briefs, both trait rows, the matchup
   numbers and OP.GG's lane-advantage labels and tip. The draft must not contradict the data:
   if lane advantage says Elise and the draft says Lee wins early, `scout doctor` rejects it
   (`validate_brief`, against the label stored in `stats.sqlite`).
4. After a game, `scout postgame` offers a matchup note (`matchup_notes.csv`), not a brief.
5. Until a brief exists, the report builds the same sections from the computed lane timeline
   below plus the champion briefs, so nothing is blank.

Keeping them current: `scout refresh` queues `brief_stale` (`stale()` in
`scout/data/briefs.py`) in two cases only: either champion has an open kit-change entry in the
review queue (`abilities_changed`, `patch_changed`, `patch_notes`), or OP.GG's lane-advantage
label now points the other way from the brief's `levels_1_3`. The entry is filed under the
brief's own champion (`champ_id`). Briefs are reviewed by hand in
`data/manual/matchup_briefs.csv` (set `reviewed=y` and `reviewed_patch`): `scout review` walks
traits rows only, and accepting or editing a champion's traits closes all its open queue
entries, `brief_stale` included, even though the brief itself didn't change.

## Computed pieces that make this specific
These are insights (`ROLES.md`), computed in tested Python from traits and stats:
- **Lane timeline** (`lane_timeline[lane]`): for levels 1-3, 3-6, after 6, and after first item,
  who's favored and why. Uses `early`, `spikes`, `scaling`, ult tags, and stats when good enough
  (lane-advantage label for the early phases, game-length rates for later). This is what "when
  you're stronger, when to engage" comes from.
- **Jungle plan for laners** (`jungle_plan[lane]`): one of
  - `ask_gank`: you lose early but their laner is gankable (low escape, you have CC follow-up);
    best window is the phase where you're weakest or they're most pushed.
  - `ask_cover`: they spike before you (e.g. at 6); ask for the jungler nearby before that.
  - `self_sufficient`: you win or hold the lane and aren't very gankable; tell the jungler to
    play elsewhere.
  - `danger`: the enemy jungler's threat to your lane is high and your jungler is likely on the
    other side; play safe until you see their jungler.
  The jungler's report gets the mirror image (lanes asking for help, lanes that are fine).
- **Cross-map threats** (`cross_map[side]`): enemy champions with `ult_join`, `global`, or high
  `roam`, which of our lanes they can reach, and from when (usually after 6). Example output: "After
  6, check where Shen is before fighting bot: his ult can bring him in." Our own side gets the
  same ("your Galio can join bot fights after 6; fight near him").
- **Items to expect**: the usual core build of the enemy in my role into my champion, from
  OP.GG's matchup build data, with names from Data Dragon `item.json` (`items.csv`). Shown as
  "<enemy>'s usual build into <me>: <item>, <item>, <item>." and only when the data has it.
  Never hard-coded.

## What the writer receives
For every champion in the game (M17), the builder (`scout/report/builder.py`) sends under
`facts`: name, role, class, Riot's ratings and the wiki's mechanics, OP.GG's game-length
numbers, the figures measured from Riot's match data when there are enough games (`measured`:
source, figures, what changed since last patch), `key_note`, `ult_note`, `spike_note` (drafts
unless reviewed), every ability's name and Riot description, Riot's tips against each enemy
(and for playing my champion), and cooldowns as display strings for me and my lane opponents.
For my lane the report sections it sends carry the matchup brief if one exists, else the lane
timeline (a brief replaces it), plus the jungle plan, cross-map threats that reach my lane,
and expected items. Beside those: the `counterpick` block (`COUNTERPICK.md`),
`class_definitions` (Riot's words for each class in the game), `game_facts` (timers and my
role quest) and, once the backtest has run, `track_record` (how often each of this report's
calls came true in stored games, M20). See `REPORT_AGENT.md`.
