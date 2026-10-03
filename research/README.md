# research/: prompts for what only exists as text

Sidekick measures the numbers itself from Riot's match data (the app does it in the
background), so agents are only needed for facts that exist as words on a page. Everything the
agent needs is inside each prompt (the champion list: 173 champions, patch 26.19; today's game
facts), with the rules and exactly what to send back. The whole picture (what updates by
itself, every source, the patch checklist): `docs/PATCH_UPDATE.md`.

## The prompts
| File | When | What it brings back | Where it goes |
|---|---|---|---|
| `patch_notes.md` | each new patch, and again after a mid-patch hotfix (the app notices both) | Champions whose kit changed, and changed game facts, quoted from Riot's patch notes; after a hotfix, only what it changed | the review queue; `data/manual/game_facts.csv` |
| `game_facts.md` | each new patch, or when a timer looks wrong | Every objective and camp timer and role quest line, re-checked, hotfixes included | `data/manual/game_facts.csv` |
| `class_definitions.md` | once (done 2026-10-03) | Riot's own description of each champion class | `data/manual/class_definitions.csv` (the writer explains classes in Riot's words) |

`status.csv` records which prompt was done for which patch (Data Dragon's patch number: 16.19
is Riot's 26.19). After a new patch the app's top bar shows "Research due" until both per-patch
prompts are applied, for whoever has research reminders on (Settings, Data and updates; only the
person who runs the research needs them). Everyone else gets the results with the next update.

## How to run one
1. Open the prompt file and copy from **Prompt** to the end of the file. There's nothing to
   fill in: the app rewrites the prompts by itself for each new patch, after each applied
   reply, and for a hotfix (then the patch notes prompt asks only about that update).
2. Paste it into an agent with web browsing on (for example Claude with web search).
3. Paste the agent's **whole reply** into a new file in `research/results/` (any name ending in
   `.md`; the file name doesn't matter, the importer reads the tables inside).
4. In the app: Settings, Data and updates, **Check research/results**, then **Apply** (or run
   `scout import-research`, or ask Claude Code). It checks every row (champion ids, a source and
   an https link, a patch), shows exactly what would change, and changes nothing until you say
   yes. If the game facts reply and the patch notes reply both give the same fact, the game
   facts reply wins (it re-checks every fact in full; the patch notes reply only has what that
   patch changed). Replies it applied move to `research/results/done/` and stay there as the
   record of where each fact came from.
5. Claude Code commits `data/manual/`, `status.csv` and `results/done/`, and pushes.

`scout research` rewrites them by hand; the app does it on the PC with research reminders on.
Claude Code commits the rewritten prompts with the results.

## Known gaps
- Catcher and Specialist: Riot never published a description, so they have none
  (`results/done/class_definitions-2026-10-03.md`, NOT FOUND).
- The class quotes are Riot's 2016 dev blog wording as the LoL Wiki reproduces it: Riot's own
  pages couldn't be opened (same file, NOTES).
