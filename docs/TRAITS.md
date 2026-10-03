# TRAITS: the hand-owned judgment layer

Stats say *that* a matchup is bad. Traits say *why* ("no dash, so gank him with CC"), and they
still work when stats are thin: new champions, off-role picks, early patch. Rules run on traits.
Traits live in `data/manual/champion_traits.csv`, which is the owner's file: code only appends
drafted rows or edits through `scout review` with confirmation.

**Sourced values win (M15, M19; 2026-10-03: no conclusions of our own).** When reports
are built, these columns are replaced in memory by a source, and the CSV keeps the old draft
(`scout/data/sourced.py`, `scout/analysis/players.py`):
- `cc`, `escape`, `frontline` = Riot's own playstyle ratings (Control, Mobility, Toughness:
  1 Low, 2 Moderate, 3 High). `escape` is 0 when Riot says Low and the LoL Wiki lists no dash
  or blink. A "frontliner" is High toughness.
- Tags `airborne` and `stealth` = the LoL Wiki's mechanic categories (airborne = knock-up,
  knock-back, knock-aside or pull); `needs_airborne` = Riot's ability text.
- `scaling` = OP.GG's win rate by game length, per game, when the draft has the numbers.
- `early`, `waveclear`, `roam` = measured from Riot's match data (`scout/analysis/measured.py`):
  gold vs the lane opponent at 10 minutes, time on the enemy half in minutes 3-10, and
  takedowns outside the lane before 14:00. Within the role, among champions with 50+ measured
  games that really play it, the champion's quarter sets the level (top quarter 3, bottom
  quarter 0). Only when the champion has 50+ games and the role has 8+ such champions;
  otherwise the drafted value stays.
A row with `source=owner` keeps every value as written, these included: The owner's word beats every
source. The measured figures and OP.GG's game-length numbers still go to the writer, so the
report can quote them. A row accepted as is in `scout review` keeps its source, so sources
still replace its values (see Reviewing). The rubric below still describes every column;
`engage`, `spikes`, `style`, the other tags and the notes have no source and stay as drafted
until the owner reviews them.

## Columns
| column | type | meaning |
|---|---|---|
| champ_id | str | Data Dragon id (`LeeSin`, `MonkeyKing`) |
| role | str | blank = applies to every role. A row with a role set (e.g. `support`) fully overrides the blank row when the champion plays that role |
| early | 0-3 | kill pressure, levels 1-5 |
| engage | 0-3 | can start a fight on their own **before level 6** (ult engages go in tags as `ult_engage`) |
| cc | 0-3 | best hard CC **before level 6** |
| escape | 0-3 | ways to get out |
| scaling | 0-3 | late-game strength relative to early |
| roam | 0-3 | ability to affect other lanes early (move fast, impact on arrival) |
| waveclear | 0-3 | how fast they push a wave early, which gives lane priority |
| frontline | 0-3 | can absorb damage and stand in front in fights |
| spikes | `2\|6` | levels with big power jumps, pipe-separated |
| tags | `airborne\|peel` | pipe-separated, from the vocabulary below |
| style | str | junglers only: `ganker`, `farmer`, or blank |
| key_note | str | one sentence: the ability that matters most in lane and how to punish it |
| ult_note | str | one or two sentences: what the ultimate does to the map and to fights, who it threatens, how to play around it |
| spike_note | str | one sentence: when they get strong, in words (levels from `spikes`, items in general terms) |
| reviewed | y/n | `y` once the owner checked it |
| reviewed_patch | str | Data Dragon version it was last checked on |
| source | str | who wrote the current values: `owner`, `prototype`, `llm` |
| notes | str | free text |

Primary key: `(champ_id, role)`. Text fields are plain language, no numbers unless they come
from `abilities.csv`, and no item names (items come from data, see `KNOWLEDGE.md`).

## Scales (rubric)
Use whole numbers. When unsure between two values, pick the lower and say why in `notes`.
Anchor examples come from the hand-made prototype rows; add your own anchors as you review.

**early**: 0 none, 1 weak, 2 solid, 3 wins most lanes early.
Anchors: 3 Samira, Nautilus, Darius, Lee Sin, Elise. 0 Karthus.

**engage**: 0 can't start fights, 1 situational, 2 one real engage tool, 3 strong repeatable engage.
Anchors: 3 Nautilus, Leona, Thresh, Alistar, Amumu. 0 Jhin, Ashe, Teemo.

**cc**: 0 none or slows only, 1 short or unreliable, 2 one reliable stun/root/knock-up,
3 multiple or point-and-click. Anchors: 3 Nautilus, Leona, Thresh, Alistar, Amumu. 0 Zed, Teemo.

**escape**: 0 Flash only, 1 movement speed or minor, 2 one real dash or blink, 3 multiple,
resettable, or untargetable. Anchors: 3 Ezreal, Yasuo, Ahri, Zed, Lee Sin. 0 Jhin, Ashe, Nautilus.

**scaling**: 0 falls off, 1 early/mid peak, 2 scales normally, 3 hypercarry.
Anchors: 3 Jinx, Cho'Gath, Karthus. 1 Lee Sin, Elise, Nautilus.

**roam**: 0 rarely leaves lane usefully, 1 can roam with setup, 2 good roamer, 3 roams are core
to the champion.

**waveclear**: 0 struggles to push early, 1 slow, 2 good, 3 shoves waves almost instantly.

**frontline**: 0 squishy, 1 can take a few hits, 2 solid frontline, 3 dedicated tank.

## Tag vocabulary
The validator rejects anything else. Add a tag here first, then use it.
`airborne` (has a knock-up or knock-back), `needs_airborne` (ult needs airborne targets),
`follows_cc` (dives onto allied CC), `peel`, `disengage`, `ult_engage`, `global` (map-wide
damage or reach), `ult_join` (ult brings them into a fight in another lane, e.g. Shen, Galio),
`point_click_cc`, `poke`, `sustain`, `stealth`, `split_push`, `invade_strong` (strong level 1-2
invader), `lane_bully`, `dive` (dives the backline or under tower), `anti_auto` (shuts
down or punishes basic attacks: an ability that blocks, dodges, blinds, slows attack speed
or returns damage to attackers, so it's strong into marksmen and auto-attack skirmishers;
used by pick suggestions, M9b).

## Seeding every champion (M3)
A test version needs a row for every champion on day one: with only the 23 prototype rows,
almost every real game has unknown champions.
1. **Convert the prototype rows** (`prototype/jungle_scout.py` CHAMPS) to Data Dragon ids,
   `source=prototype`. The new columns (`roam`, `waveclear`, `frontline`) are blank, so these rows
   stay `reviewed=n` until the owner fills them in.
2. **Show Riot's own ratings as hints.** CommunityDragon has Riot's 1-3 ratings per champion
   (`playstyleInfo`: damage, durability, crowdControl, mobility, utility). They land in
   `champion_meta.csv` (generated). They're whole-kit ratings including ultimates. At seeding
   they were only hints for `cc`, `escape` and `frontline`. Superseded by M15: they now
   replace those columns in memory when reports are built (top of this doc).
3. **LLM drafts the rest**, scores and text fields (`key_note`, `ult_note`, `spike_note`):
   `scout draft-traits --all-missing` sends, per champion, the ability text (`abilities.csv`),
   class, range, damage type, Riot's ratings, this rubric, and the owner's reviewed rows (then
   prototype rows) as examples.
   It asks for one row as structured JSON, validates it, and appends it with `reviewed=n,
   source=llm`. Rough cost: 170 champions x about 1-2 cents on a small model. The first full
   pass can instead be drafted by Claude Code in a session (no API cost), same validation.
4. Reports warn about every unreviewed champion in the game.

**Done 2026-10-02 (16.19.1):** all 173 champions have a row. 150 were drafted in a Claude Code
session (7 parallel batches from `abilities.csv` and `champion_meta.csv`, each checked with the
validator below); the 23 prototype rows kept every original value and got only `roam`,
`waveclear`, `frontline`, `ult_note`, `spike_note` drafted (`source=prototype`, with a note).
Where a draft used League knowledge beyond the ability text, or the drafter wasn't sure, the
row's `notes` says so; read those first when reviewing. Four champions were new to the drafter
and are scored from ability text only (Locke, Shyvana's new kit, Yunara, Zaahen).

## Validation (`scout/data/store.py`, `validate_traits`)
All the checks below run before `scout draft-traits` appends a row and when `scout review`
saves one. When traits load for reports, the same checks run without the static data, so the
three that need it (champion exists, numbers, item names) are skipped: a patch that rewords
ability text must not stop reports.
- columns match the schema; `(champ_id, role)` unique; `champ_id` exists in `champions.csv`;
  `role` blank or a valid role
- scales are 0-3; drafted (`source=llm`) and reviewed rows need every scale and text field
- `spikes` are ascending levels 1-18; `tags` from the vocabulary; `style` is `ganker`,
  `farmer` or blank, and is rejected on a row whose role is set to a non-jungle role (an
  any-role row may have it)
- `reviewed` is y/n and `reviewed=y` needs `reviewed_patch`; `source` is owner, prototype or llm
- text fields within length (key_note 240, ult_note 320, spike_note 200 characters)
- no numbers except level mentions ("level 6", "levels 1-3"), spike levels, and numbers that
  appear in that champion's ability text or cooldowns
- no item names (from `items.csv`); the champion's own ability names are exempt, since some
  contain item names (Mel's "Golden Eclipse", Renekton's "Cull the Meek")

## Reviewing (`scout review`, or `scout review <ChampId>` for one)
Walks the review queue in this order: champions from the owner's recent games (recorded champ
selects, newest first), then the champ pool, then everything else alphabetically. For each, it
shows ability text, static facts, Riot's ratings, the current row, and any stats
disagreement, then accept / edit / skip. Accepting writes `reviewed=y` and
`reviewed_patch=<current>` and keeps the row's `source` (say `llm`), so Riot's ratings, the
wiki's mechanics, the measured values and OP.GG's scaling keep replacing those columns in
reports. Edit walks every field (Enter keeps a value, `-` clears it), validates, shows the row
and asks before saving; nothing is written without that yes. A row with any field changed
becomes `source=owner`, and then its values beat every source. Saving either way resolves all
the champion's open review queue entries (`brief_stale` included). It covers each champion's
any-role row; role-specific rows are edited by hand. About 2-3 minutes per champion, so
reviewing the whole roster is about 6-8 hours spread over normal play.

## Keeping traits current over time
Traits describe a kit, which changes rarely. A row is flagged for review when:
- a champion's ability text or cooldowns changed (`abilities_changed`, `scout refresh`),
- the wiki's "last changed" patch equals the current patch (`patch_changed`, `scout refresh`),
- patch notes change the champion's kit (`patch_notes`: the `research/patch_notes.md` reply,
  applied by `scout import-research`),
- OP.GG's numbers disagree with the traits in a game Sidekick reports on (`stats_disagree`,
  see `STATS.md`): the lane-advantage label points the other way, or traits say `scaling` 0-1
  but the win rate climbs a lot from short to long games (or 3 and it falls a lot). One game
  is enough to queue it; an entry with the same details isn't added again while it's open.
Code never changes the CSV on its own. It only queues the row and proposes the change.

## Other hand-owned files
**`data/manual/matchup_notes.csv`**: `role, champ_id, opp_champ_id, note, date`. The owner's own
experience, shown verbatim as "Your notes". `scout postgame` offers to append one after it
checks a game. The app's automatic post-game check doesn't offer one, and it marks the report
checked, so a plain `scout postgame` skips that game afterwards.

**`data/manual/matchup_briefs.csv`**: per-matchup briefs (who's stronger by phase, how to trade,
what to ask the jungler). Format and how they're drafted and kept current: `KNOWLEDGE.md`.

**`data/manual/champion_overrides.csv`**: `champ_id, field, value, reason`. Fixes a wrong
generated fact (e.g. `range_type`, `damage_type`, `classes`) without editing generated files.
Applied by `scout refresh` when it builds static data (`scout/data/static.py`): the value is
written into `champion_meta.csv` and marked `<field>:override` in its `field_sources`. Refresh
skips a version that's already built, so run `scout refresh --force` after editing. Any
`champion_meta.csv` column except `champ_id`, `field_sources` and `ddragon_version` can be
overridden; an unknown champion or column is skipped with a warning in the refresh log. The
`reason` column is for the owner: nothing shows it.

**`data/manual/game_facts.csv`** (`fact_id, topic, role, text, source, source_url, patch,
checked_on`) and **`data/manual/class_definitions.csv`** (`class, quote, source, source_url,
checked_on`): cited game facts (objective and camp timers, role quests) and Riot's own
description of each champion class. Written only by `scout import-research` (or in the app:
Settings, Data and updates, Check research/results, then Apply) from the replies in
`research/results/`, after the owner confirms. How they're used: `KNOWLEDGE.md`; how they're kept
current: `PATCH_UPDATE.md`.
