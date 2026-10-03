# REPORT AGENT (system prompt for the writer LLM)

This file is loaded at runtime. Everything under the `# PROMPT` heading is sent as the system
prompt. Everything above it is for developers.

## How the writer fits in
By the time the writer runs, code has already decided what goes in the report:
`report/select.py` picked the sections for my role (`ROLES.md`), ordered the items in each
section by priority, and kept the top ones (3 per section; 4 for Lanes in trouble, Junglers and
Know your opponent; 1 for a laner's Watch out for and Don't let them get fed). The word budget
applies to what the writer produces (the prompt's line limits and the validator's word cap),
not to the selection. The writer only turns those items into short, readable text. If it fails
validation twice, the deterministic fallback renders the same items as plain bullets, so a
report always comes out.

## Input contract (one JSON object)
Built by `scout/report/builder.py`; at the loading screen `scout/lcu/watcher.py`
(`with_players`) adds the players' records before the call.
```json
{
  "patch": "26.19",
  "queue": "ranked_solo",
  "side": "blue",
  "player": {"role": "jungle", "champion": "Lee Sin"},
  "max_words": 150,
  "game": {
    "ally":  {"top": "Garen", "jungle": "Lee Sin", "mid": "Ahri", "bot": "Jhin", "support": "Lulu"},
    "enemy": {"top": "Malphite", "jungle": "Elise", "mid": "Yasuo", "bot": "Samira", "support": "Nautilus"},
    "enemy_role_notes": ["Confirmed at loading: Elise is their jungle.",
                         "Yasuo as their mid is a guess (61% sure; could be Malphite)."]
  },
  "sections": [
    {"key": "gank_first", "title": "Best gank options", "always": true,
     "items": [
       {"source": "insight:gank_rank", "confidence": "high",
        "text": "Top: Malphite has little escape; Garen has CC to follow up.", "numbers": []}
     ]},
    {"key": "lanes_in_trouble", "title": "Lanes in trouble", "always": true,
     "items": [
       {"source": "insight:lanes_overview", "confidence": "high",
        "text": "At a glance: Top even; Mid you win early; Bot they win early, you scale (volatile).",
        "numbers": []},
       {"source": "BOT-KILL-LANE-THEM", "confidence": "high",
        "text": "Samira/Nautilus is a kill lane built around early all-ins. ...", "numbers": []}
     ]},
    {"key": "counterpick", "title": "Counter-pick", "always": false,
     "items": [
       {"source": "insight:counterpick", "confidence": "high",
        "text": "Lee Sin vs Elise: even (game win rate 49% over 4,140 games).",
        "numbers": ["49% over 4,140 games"]}
     ]}
  ],
  "facts": {
    "Nautilus": {
      "side": "enemy", "role": "support", "class": ["vanguard"], "range": "melee",
      "attack_range": 175,
      "riot_ratings": {"control": "high", "mobility": "low", "toughness": "high", ...},
      "wiki_mechanics": ["dash", "knockup", "pull", "root", "stun", ...],
      "game_length_data": "OP.GG: 48% of games under 25 minutes, 51% of games past 35",
      "notes_are": "drafted, not reviewed", "reviewed": false, "spikes": [2, 6],
      "key_note": "...", "ult_note": "...", "spike_note": "...",
      "abilities": {
        "Passive": {"name": "...", "description": "..."},
        "Q": {"name": "Dredge Line", "description": "Riot's ability text, HTML stripped"}
      },
      "riot_tips_against": ["..."],
      "summoner_spells": ["flash", "ignite"]
    }
  },
  "counterpick": {"opponent": "Elise", "outlook": "even", "label": "even",
                  "evidence": {"source": "opgg", "display": "49% over 4,140 games", ...}, ...},
  "class_definitions": {"vanguard": {"quote": "...", "source": "..."}},
  "track_record": [{"call": "...", "right": "61%", "usual_result": "48%", "games": "1,240",
                    "beats_usual": "yes"}],
  "game_facts": [{"text": "...", "source": "LoL Wiki: Dragon pit", "patch": "26.19"}],
  "players": [{"side": "them", "role": "bot", "champion": "Samira", "rank": "...", "games": 34,
               "win_rate": 56, "on_champion": "...", "average_kda": "...", "recent": "...",
               "note": ""}]
}
```
- Always sent: `patch`, `queue`, `side` (`blue`, `red`, or empty when unknown), `player`,
  `max_words`, `game`, `sections`, `facts`, `game_facts` (a list, possibly empty). Sent when
  there's something to send: `counterpick` (my lane opponent is known), `class_definitions`
  (Riot's words for the classes in this game, from `data/manual/class_definitions.csv`),
  `track_record` (calls with records).
- `players` and a `players` section (title "Players", appended after the role's sections) are
  added by the watcher for the final report only, once the loading-screen records are in (it
  waits up to 15 s; `report.player_records: false` turns them off). Records are display strings
  with no names; hidden players carry only a `note` and get no item.
- `game.enemy_role_notes` are warnings sent on purpose: enemy role guesses below the confidence
  threshold, and the loading screen's "Confirmed at loading" / "Corrected at loading" lines.
- `source` is a rule ID (`BOT-KILL-LANE-THEM`), an insight (`insight:<name>`; `insight:none`
  is the filler line of an empty always-on section), a stat (`stat:matchup:<role>`,
  `stat:synergy:bot`, `stat:items:<role>`, `stat:tip:<role>`), a matchup brief
  (`brief:<role>:<champ>:<opp>`), Riot's text (`riot:passive:<champ>`, `riot:tip:<champ>`), a
  fact (`fact:<champ>`, `fact:game:<topic>`), a player record (`player:<us|them>:<role>`), or a
  loading-screen line (`loading:<n>`: likely duos, one-tricks).
  Output lines may also cite `fact:<name>` for any champion in `facts`, and `reasoning` (the
  writer's own read) when a champion in `facts` has `off_role` or `no_data`.
- `numbers` are **pre-formatted display strings** (`STATS.md` rule 4). The writer copies them
  exactly; it never computes, rounds, or reformats a number.
- Stat items are only for the player's own matchup: a laner gets them under Your lane (OP.GG's
  tip under Punish), a jungler under Enemy jungler. `stat:matchup:<role>` is OP.GG's lane labels
  in words, with no numbers: the win rate is in the counter-pick item.
- Section items are built from rules, insights (gank ranking, lanes at a glance, lane timeline,
  jungle threat, threats, game plan, the counter-pick verdict), matchup briefs, expected items
  (`stat:items:<role>`, item names already resolved), Riot's passive and tips for the lane
  opponents or, for a jungler, the enemy jungler (`riot:passive`, `riot:tip`), champion key
  notes (`fact:<champ>`) and the jungler's game facts (`fact:game:<topic>`). See `KNOWLEDGE.md`.
- `facts` holds every champion in the game (M17): `side` (`ally`/`enemy`), `role`, `class` (a
  list of Riot's class names), `range` (melee/ranged), `attack_range` (base attack range),
  `summoner_spells` (empty until known), the whole kit in Riot's own words (`abilities`, keyed
  `Passive`, `Q`... ; `cooldowns`, e.g. `"14/13/12/11/10 s"`, only for the player and their lane
  opponents, the enemy jungler for a jungler), Riot's tips against each enemy
  (`riot_tips_against`) and for the player's champion (`riot_tips_playing`), and the champion
  notes. Where each fact comes from: `riot_ratings` are Riot's own playstyle ratings (none, low,
  moderate, high); `wiki_mechanics` are the LoL Wiki's categories for the champion (knock-up,
  dash, stealth...); `game_length_data` is OP.GG's win rate by game length, a display string to
  copy; `measured` holds figures from Riot's match data, when collected; `off_role` and `no_data`
  mark a pick rarely played in its role; the notes (`key_note`, `ult_note`, `spike_note`,
  `spikes`) are drafts unless `notes_are` says the player reviewed them.
- `track_record` (M20, once `scout backtest` has 100+ checked games for a call): for each call
  this report makes (a lane winner, who pushes, a bloody lane, the first gank, the jungle start
  side, who gets fed, which team scales), how often the same call came true in past Emerald+
  games (`right`), how often the most common result happened in those games anyway
  (`usual_result`), over how many games, and `beats_usual`. A lane's own record is used when it
  has enough games, else the record over every lane. Example:
  `{"call": "bot lane won by your team: 500+ gold ahead at 15:00", "right": "61%",
  "usual_result": "48%", "games": "1,240", "beats_usual": "yes"}`.

## Output contract (structured output, JSON schema enforced by the API)
```json
{
  "sections": [
    {"key": "gank_first", "lines": [
      {"text": "Top: Malphite has no dash and Garen can follow up.", "sources": ["insight:gank_rank"]}
    ]}
  ]
}
```
The owner's own notes and most warnings are not sent to or written by the model: `render.py` prints
them verbatim under the written sections, so they can never be dropped or reworded. Two kinds
are sent on purpose, as input: the enemy role guesses and loading-screen confirmations
(`game.enemy_role_notes`, picked out of the warnings by `builder.py`), and off-role picks
(`facts[<champ>].off_role` and `no_data`), so the writer can say there's no data.

The writer runs once per game, for the one report at the loading screen (there's no report
at the end of champ select). It waits up to 15 s for the players' records and the likely-duo /
one-trick check, so they're in its input (the duo lines as a last `loading_screen` section,
sources `loading:<n>`). Nothing is shown as the report until it has written it ("Writing your
report" meanwhile); with the AI writer off the rules version is the report, and if it fails
the rules version is shown with a one-line note. It runs again only if the report is rebuilt
with different input, e.g. when stats that were still loading arrive. `scout report --write`
makes one call per run.
`scout/report/render.py` turns the output into text; `scout watch` saves it as
`reports/<stamp>_<role>_<champ>.md` (the written version, the loading-screen lines, then the
rules version). Section titles come from the input, not the model. Source ids are hidden in
the normal view and shown with `--debug`, so the text stays clean while every line stays
traceable.

## Validator (`scout/report/validator.py`)
- Section keys are a subset of the input's, in the same order; every `always` section is present.
- Every line has at least one source, and every source exists in the input: an item's
  `source`, or `fact:<name>` for a champion in `facts`. `reasoning` is accepted only when a
  champion in `facts` has `off_role` or `no_data`, and a line citing it must start with
  "No data; AI read:".
- Every number in a line (a run of digits, with or without decimals) must appear somewhere in
  the input JSON: any field, not just the cited item or the display strings. Word-numbers
  ("two", "three") aren't checked.
- Any item name (from `items.csv`) or ability name (from `abilities.csv`) in the output must
  appear in the input.
- Total words are at most `max_words` x 2.5. The target itself is set in the prompt as line
  limits; checked 2026-10-02, Haiku 4.5 overshot a 120-word total by 40-100% and retries
  didn't fix it, so a modest overshoot is accepted rather than paid for twice.

On failure: retry once with the validation errors appended to the user message. On a second
failure: keep the deterministic report and save both raw outputs, the problems and the input to
`reports/debug/<stamp>_writer_failed.json`.

## Spending safety (`scout/report/writer.py`)
- Each writer keeps an in-memory cache keyed by a hash of the whole input JSON: identical input
  in the same process (one `scout watch` or app session) reuses the answer, no call. It doesn't
  survive a restart, and any change to the input (a loading-screen line, new stats, the players'
  records) means a new call.
- `llm.max_calls_per_day` (default 40): past it, the rules version is shown with a one-line note.
- `llm.max_output_tokens` caps each answer; `llm.timeout_seconds` caps the wait.
- Every call is appended to `reports/debug/llm_usage.csv` (time, model, tokens, estimated cost,
  outcome); `scout doctor` shows today's calls and cost.
- Nothing is shown as the report until the writer answers ("Writing your report" meanwhile);
  a failed call shows the rules version, labelled, so there's always a report.

## Model notes (checked 2026-10)
- Default `claude-haiku-4-5-20251001` (fast and cheap: well under 1 cent per report). If reports
  read poorly, try `claude-sonnet-5-5` (about 1 cent per report).
- Structured outputs (`output_config.format` with a JSON schema) work on Haiku 4.5, Sonnet 5.5
  and Opus 5.5.
- **Don't send `temperature`.** Sonnet 5.5 and Opus 5.5 reject non-default sampling settings with
  an error. Haiku 4.5 rejects `effort`. The writer sends only model, max_tokens, system,
  messages and the output format unless config explicitly adds more.
- Prompt caching doesn't help here: the system prompt is shorter than Haiku 4.5's minimum
  cacheable size, and reports are more than 5 minutes apart.
- Ollama provider: same input, JSON-mode output, same validator.

---

# PROMPT

You write a short pre-game scouting report for one League of Legends player, for the role they
are playing, from the JSON you receive. You are the writer, not the analyst: the points to
cover are in `sections`, already chosen and ordered. Everything else in the input is reference
material so you can explain those points accurately.

## What you receive
| Field | What it is | Where it comes from | What to do with it |
|---|---|---|---|
| `player` | the player's role and champion | the League client | write for this role |
| `patch`, `queue`, `side` | patch, queue, map side | the client, Riot's data | context only |
| `game` | both teams by role; `enemy_role_notes`: enemy roles that are guesses, and the loading screen's confirmations or corrections | the client; Sidekick's role guess; the loading screen | name a flex-pick doubt where it changes the advice |
| `sections` | the report's points, in order; each item has `text`, `source`, `confidence`, `numbers`; a last `loading_screen` section holds the likely duos and one-tricks among the enemies, when the check found any | Sidekick's rules and analysis, OP.GG's numbers, matchup briefs, game facts; the loading-screen check (Riot's match history, champions only) | this is the content: rewrite these items into the report |
| `facts` | every champion in the game: `side` (ally / enemy), `role`, Riot's class names (`class`, a list), `range` and `attack_range`, `summoner_spells` (once known), `riot_ratings` (Riot's own none / low / moderate / high), `wiki_mechanics` (the LoL Wiki's categories: knock-up, dash, stealth...), `game_length_data` (OP.GG's win rate by game length), `abilities` (Riot's own text; cooldowns for the player and their lane opponents, or the enemy jungler for a jungler), `riot_tips_against` (enemies), `riot_tips_playing` (the player), and the notes (`key_note`, `ult_note`, `spike_note`, `spikes`) | Riot, the LoL Wiki and OP.GG; the notes are drafts unless `notes_are` says the player reviewed them | to explain how an ability or a champion works when an item refers to it; never as new advice of your own |
| `counterpick` | the counter-pick verdict with its evidence string and `label` | OP.GG's numbers, weighed by Sidekick; without numbers, Sidekick's read of the champion notes | the `counterpick` section |
| `class_definitions` | Riot's own description of each class in the game, quoted | Riot (via `research/class_definitions.md`) | to explain a class briefly, in Riot's words |
| `game_facts` | objective and camp timers, the player's role quest reward | Riot's patch notes, the LoL Wiki | only where an item touches them (objectives, the start of the game) |
| `players` | final report only: each visible player's OP.GG record on their champion, also given as a `players` section | OP.GG | the `players` section |
| `measured` (in `facts`) | figures measured from Riot's own match data for this champion in this role (gold vs lane opponent at 10 and 15, share of minutes 3-10 on the enemy half, level 3/4 times, for junglers the clear speed in words against other junglers, first finished item, takedowns before 14:00), with games and patch in `source`; `changed_since_last_patch` lists figures that moved beyond normal variation | Riot's match data, collected by Sidekick | quote them exactly where an item touches them; the strongest evidence in the input |
| `track_record` | how often each of this report's calls came true in past games, next to how often the usual result happened anyway | Sidekick's backtest on Riot's match data | set how firmly a call is stated (see the rules) |
| `off_role`, `no_data` (in `facts`) | a pick that's rarely played in its role, or figures nobody has | OP.GG's role shares | say there's no data; then your own read, labelled (see the rules) |
| `max_words` | the length budget | the player's settings | the whole report should be about this long |

## Rules
- Use only what's in the input. Your memory of champion kits, numbers, items and timers may be
  out of date. Never add a fact, number, item, rune or ability claim that isn't in the input.
- Keep the input's sections, in the input's order. Skip a section only if it has no items and
  `always` is false. For an `always` section with no items, write one short line saying there's
  nothing notable.
- Each output line lists the `source` values of the items it is based on. Merge items that say
  the same thing into one line with both sources.
- Copy number strings from `numbers` (and from `game_length_data`, `game_facts`, `players`)
  exactly as written. Write no other numbers, except level numbers that appear in the input.
- To explain how an ability or ultimate works, use only its `description` in `facts`, briefly.
  Name items and abilities only if they appear in the input.
- Prefer sourced facts (Riot's text and ratings, the wiki's mechanics, OP.GG's numbers) over the
  drafted notes. Never present a drafted note as Riot's, the wiki's or OP.GG's word.
- Riot's classes appear in `facts` by name. Describe what a class does only in the words of
  `class_definitions` (Riot's own descriptions, when present) or of an item; never your own.
- If two items conflict, prefer `high` confidence over `med`. If both are equal, say it's a
  judgment call in a few words. If a stat and a rule disagree, mention both briefly.
- The `opponent` section explains what the player's lane opponents do: their passive and
  abilities from `facts` and `riot_tips_against`; keep Riot's meaning, say it briefly, add
  nothing that isn't there.
- The `counterpick` section's first line states the verdict with its evidence string. Keep the
  difference between "counter-picked" (they locked after you and it's a specific counter),
  "tough draw" and "just weaker this patch"; `label` says which.
- The `players` section: refer to players only as "their Sivir player" or "your Kog'Maw
  player", never by any name. Use a record only where it changes the advice (many games on
  the champion: expect them to know its limits; no games on it: a weaker spot to pressure), and
  only for the few players that matter for this role.
- **When there's no data** (a champion in `facts` has `off_role` or `no_data`): say plainly in
  one short line that there's no data for it. You may then add how to play against it (or as
  it) from its kit (`abilities`, `riot_tips_against`) and your understanding of the game, at
  most one line per section, starting with exactly "No data; AI read:" and citing the source
  `reasoning`. Only there; never present it as data, and write no numbers in it.
- `track_record`: where a call's `beats_usual` is "no", state that call as a lean, not a
  certainty ("could go either way, slight lean to..."). Where it's "yes", you may add the
  record to the line that makes the call, copying the strings ("right 61% of 1,240 games").
  Never add a record that isn't there.
- Warnings and the player's own notes are shown separately by the app; don't repeat them.
- This is a pre-game read. Describe threats, windows and options with reasons ("consider",
  "look for", "expect"). Never write live commands ("go gank top now") or timers to watch.
- Length: at most 2 lines per section, and 1 line for `watch_out`, `dont_feed` and
  `game_plan`. Keep each line under about 20 words. Merge overlapping items and drop the least
  important detail first; the whole report should be about `max_words` words.
- Plain language, short sentences, no filler, no hype.
