# SPEC: what we're building

## One-line goal
When champion select ends, show a short, accurate scouting report **for the role I'm playing**:
how my lane (or, for jungle, the whole map) will go, whether I got counter-picked and how to
play into it, what the enemy jungler means for me, enemy combos, who must not get fed, and a
one-line game plan.

## Users
- Whoever installed it. Players get filled, so **all five roles must produce a good report**, not
  just jungle. `ROLES.md` is the per-role spec.
- Runs on the player's Windows PC next to the League client, as the Sidekick app, installed
  with `SidekickSetup.exe` from the repo's releases (README; no commands). Personal use shared
  with friends: each person's settings, keys and champion lists (one per League account) stay
  on their own PC.

## When it runs
| Moment | What it does | Milestone |
|---|---|---|
| During the draft | Pick options for my assigned role: from my champion list (with comfort stars), else my most-played champions, else strong picks outside my list; ranked against locked enemies and with locked allies (synergy), with reasons. Pre-fetch matchup stats as picks lock. | M9b, M8, M18 |
| End of champion select (all picks locked) | No report (2026-10-03): "Picks locked, your report comes at the loading screen". Trades still count. | M6 |
| Loading screen | **The one report**, as soon as the roster shows everyone's summoner spells: enemy roles confirmed (who has Smite), the players' records and likely duos / one-tricks gathered, then written by the LLM ("Writing your report" until it's in). With the AI writer off, or if it fails, the rules version (labelled). | M6, M7, M11, M16 |
| After the game | Post-game check: compare the report's predictions with what happened. History keeps each game's report to open again. | M10, M23 |
| In the background (never in champ select or a game) | Data refresh every 6 hours, Riot match data measured, update check. | M19, M21 |

Never during the game. No overlays, timers, or live prompts (see `POLICY.md`).

## What the report covers
Every role gets these building blocks, framed for that role (full detail in `ROLES.md`; where
the champion and matchup knowledge comes from: `KNOWLEDGE.md`):

| Section | top | jungle | mid | bot (ADC) | support |
|---|---|---|---|---|---|
| Your lane: who's stronger at 1-3, 3-6, after 6, after first item; when to trade | yes | no (see Gank first) | yes | yes (2v2) | yes (2v2) |
| Gank first / lanes in trouble | no | **yes** | no | no | no |
| Counter-pick check | yes | yes (jungle matchup) | yes | yes | yes |
| Punish (their key ability) | yes | via Watch out for | yes | yes | yes |
| Junglers: their threat to me, and what to ask mine (gank when, cover before a spike, or "I'm fine") | yes | Enemy jungler + Lanes in trouble | yes | yes | yes |
| Watch the map: ults or roamers that join fights in my lane (e.g. Shen, Galio) | yes | yes (in ganks) | yes | yes | yes |
| Roams | no | no | yes | no | yes |
| Fights / your job later | split or group | objectives side | no | who dives you | protect or engage |
| Watch out for (enemy combos) | if relevant | yes | if relevant | if relevant | if relevant |
| Don't let them get fed | short | yes | short | short | short |
| Game plan (one line) | yes | yes | yes | yes | yes |
| Your notes | if any | if any | if any | if any | if any |
| Warnings (unreviewed data, role guesses) | if any | if any | if any | if any | if any |

### Always
- Every claim traces to a fired rule ID, a computed insight, a data fact, or a stat with its
  sample size.
- Missing or unreviewed champion data is flagged, never hidden. Low-confidence enemy role
  guesses are named ("Sylas might be top, not mid").
- Short: jungle about 150 words, laners about 120.
- Advice is framed as options with reasons ("consider covering bot; their lane wins level 2"),
  not commands. That's both Riot policy and better advice.

## Out of scope (do not build)
- Anything in-game: overlays, timers, cooldown tracking, live "do X now" prompts.
- Any write action against the League client (no auto-accept, auto-pick, runes, nothing).
- Looking up or showing players the game hides (ranked champ select names, streamer mode).
- Player skill ratings, MMR or Elo estimates (Riot bans these). Players' own records on their
  champion at the loading screen (OP.GG: rank, games, win rate) are a separate, switchable
  feature (M16, Settings; `POLICY.md` has Riot's position; the owner decides).
- A server, sign-ups or a public release (friends install from the public repo).
- Using data from sites whose terms forbid it (U.GG, Lolalytics, Mobalytics). See `DATA.md`.

## Acceptance criteria (v1 = milestones M0 to M10 in `TASKS.md`, including M6b and M9b)
- [ ] The Sidekick app shows the written report within about 30 s of the loading screen showing
      the summoner spells, with no crash across 20 real games (ranked and normal draft),
      covering at least 3 different roles.
- [ ] Enemy roles are inferred correctly in at least 90% of recorded fixtures (checked against
      each recording's `game_start` answer key); low-confidence guesses are labelled in the report.
- [ ] Counter-pick verdicts match the owner's judgment on at least 16 of 20 hand-labelled fixtures.
- [x] Every rule in `league_rules.yaml` has a test where it fires and one where it doesn't
      (`tests/test_rules.py`, from each rule's `tests` block).
- [x] Each of the five roles has at least 2 golden game fixtures with the expected sections and
      fired rules (`tests/golden/`).
- [x] The writer validator passes: every cited source exists in the input, every number in the
      report comes from a pre-formatted input string (`scout/report/validator.py`, tested).
- [x] `scout refresh` on a new patch updates static data and stats, lists changed champions in
      the review queue, logs a summary, and never touches `data/manual/` (tested offline).
- [ ] The post-game check runs after a game and records which predictions held (built and
      tested on a recorded game; waiting on a live game).
- [ ] the owner reads 10 reports (at least 3 not jungle) and rates at least 8 "useful and not wrong".

## Quality bar for advice
- Concrete over generic: "Samira dashes onto whatever Nautilus hooks; ganking bot is risky
  until his hook is down" beats "be careful bot".
- Honest about uncertainty: thin samples, unreviewed traits, flex-pick role guesses, and
  last-patch data are all visible.
- No hedging walls. One caveat line per section at most.
- When stats and trait-based rules disagree, the report says so in one line, and the
  disagreement goes to the review queue so the traits get fixed.
