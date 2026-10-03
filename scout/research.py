"""The research prompts in research/ (M15, trimmed in M19), with their data inside them.

Numbers come from Riot's match data (scout/data/collector.py), so agents are only asked for
facts that exist as words: a patch's notes, the game facts, Riot's class definitions.
The prompts are rewritten from the current data (the champion list, today's game facts, the
patch, what research is due) so an agent with web browsing can work from the prompt alone, with
nothing to fill in; each prompt ends with exactly what to send back. `regenerate` runs after
each data refresh and each applied research reply on the PC that does the research (research
reminders on), and with `scout research`. A mid-patch hotfix turns the patch notes prompt into
one about that update only (scout/data/patch_updates.py).
"""

import csv
import io
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from scout import research_import
from scout.data.patch import display_patch, short_patch
from scout.data.patch_updates import page_url
from scout.data.store import Row, current_version, load_static, read_csv
from scout.paths import Paths


@dataclass(frozen=True)
class Champ:
    n: int
    champ_id: str
    name: str
    roles: tuple[str, ...]


def champions(tables: Mapping[str, Sequence[Row]]) -> list[Champ]:
    meta = {r["champ_id"]: r for r in tables.get("champion_meta.csv", [])}
    rows = sorted(tables.get("champions.csv", []), key=lambda r: r["champ_id"].lower())
    return [Champ(i, r["champ_id"], r["name"],
                  tuple(x for x in (meta.get(r["champ_id"], {}).get("positions") or "").split("|")
                        if x))
            for i, r in enumerate(rows, 1)]  # fmt: skip


# ---------------------------------------------------------------- shared pieces

def _table(champs: Sequence[Champ], roles: bool = True) -> str:
    head = "| # | champ_id | name | roles |\n|---|---|---|---|" if roles else \
        "| # | champ_id | name |\n|---|---|---|"
    lines = [head]
    for c in champs:
        cells = [str(c.n), c.champ_id, c.name] + (["/".join(c.roles) or "-"] if roles else [])
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)


RULES = """### Rules (follow every one)
- **Sources:** only Riot (patch notes, dev blogs, champion pages, Data Dragon), the LoL Wiki
  (wiki.leagueoflegends.com), and the big stats sites (OP.GG, U.GG, Lolalytics, League of
  Graphs).{coaching}
- **Only what you saw:** cite only pages you actually opened, and only figures or words you saw
  on them; put each page's address in `source_url`. If you can't browse the web, or a page
  won't load, say so and stop. Never fill anything in from memory.
- **No source, no value:** leave the cell blank. Never estimate, average, guess, or fill a row
  just to complete the table. A short table that's all true beats a full one.
- **No ratings of your own:** collect the sources' figures and words. Don't turn them into
  scores, tiers or labels unless the source itself gives that score, tier or label.
- **Patch:** the current live patch is the newest "Patch X.Y Notes" on
  https://www.leagueoflegends.com/en-us/news/game-updates/ (when this prompt was written it was
  {patch}). Write the patch your figure is for in every row; prefer the current patch.{stats}
- **Champion ids:** use the `champ_id` column of the list in this prompt exactly (Wukong is
  `MonkeyKing`, Nunu & Willump is `Nunu`). If a champion isn't in the list (a brand-new one),
  use Data Dragon's id: https://ddragon.leagueoflegends.com/api/versions.json gives the newest
  version, then https://ddragon.leagueoflegends.com/cdn/<version>/data/en_US/champion.json.
- **CSV:** exactly the columns shown, one header row; put double quotes around any cell that
  contains a comma."""

STATS = """
- **Stats filter:** ranked solo/duo, Emerald and above, the row's role, the current patch. If a
  site can't filter that way, use its default and write the filter you used in `rank_filter`."""

COACHING = (" Well-known coaching sites (published, measured numbers) only where this prompt"
            " says so; write `coaching:` before their name in `source`.")


def _rules(patch: str, stats: bool = True, coaching: bool = False) -> str:
    return RULES.format(patch=patch, stats=STATS if stats else "",
                        coaching=COACHING if coaching else "")  # fmt: skip


def _send_back(topic: str, columns: str, *, about: str = "", second: str = "",
               example: str = "") -> str:
    """The reply format. `about` explains the columns; `second` adds another table;
    `example` is a real batch line (batched prompts only)."""
    items = []
    if example:
        items.append("`BATCH:` the batch number you did and its first and last champion, for "
                     f"example\n   `{example}`.")
    table = ("One CSV code block (start it with three backticks and `csv`) with exactly these "
             f"columns:\n   `{columns}`")
    items.append(table + (f"\n   {about}" if about else ""))
    if second:
        items.append(second)
    items += ["`SOURCES:` every page you used, one address per line.",
              "`NOT FOUND:` what you looked for and couldn't find, and where you looked.",
              "`NOTES:` anything unclear (optional)."]
    numbered = "\n".join(f"{i}. {text}" for i, text in enumerate(items, 1))
    name = f"{topic}-batch<N>-<date>.md" if example else f"{topic}-<date>.md"
    return f"""## What to send back
Reply with these parts, in this order, and nothing else:
{numbered}

The owner saves your whole reply as `research/results/{name}`."""


def _head(title: str, why: str, have: str, result_topic: str, batched: bool,
          patch: str = "") -> str:  # fmt: skip
    copy = ("Copy everything from **Prompt** to the end of this file into an agent that can "
            "browse the web; there's nothing to fill in.")
    how = (f"{copy} Change `<BATCH>` to the batch number (start with 1, then 2, ...)."
           if batched else copy)
    made = f" for patch {patch}" if patch else ""
    return f"""# {title}

{why}

**For the owner:** {how} Save the agent's whole reply as
`research/results/{result_topic}{'-batch<N>' if batched else ''}-<date>.md`, then in the app:
Settings, Data and updates, **Check research/results**, then **Apply**. Written by Sidekick from
the current data{made}, and rewritten by itself when that changes; don't edit by hand.

**Sidekick already has (don't ask for these):** {have}
"""


ALREADY = ("Riot's ability text and tips (Data Dragon), Riot's playstyle ratings (damage, "
           "toughness, control, mobility, utility), the LoL Wiki's mechanic categories (dash, "
           "blink, knock-up, stun, stealth...), OP.GG's matchup win rates, lane-advantage labels, "
           "builds, synergies and win rate by game length.")
APP = ("You are collecting facts for Sidekick, a personal app that writes a short pre-game "
       "scouting report for League of Legends (Summoner's Rift, ranked solo/duo). It only "
       "states facts that come from a named, reputable source, so every value you send needs "
       "its source and patch.")


# ---------------------------------------------------------------- the prompts


def prompts(champs: Sequence[Champ], facts: Sequence[Row], version: str,
            updates: Sequence[str] = (), done_on: str = "") -> dict[str, str]:  # fmt: skip
    """Every prompt and the README. `updates`: mid-patch updates that appeared after this
    patch's notes were researched on `done_on`; the patch notes prompt then asks only for them."""
    patch = display_patch(version)
    wiki = page_url(version)
    out: dict[str, str] = {}

    facts_csv = _csv(["fact_id", "topic", "role", "text", "source", "source_url", "patch",
                      "checked_on"], facts)  # fmt: skip
    ids = _table(champs, roles=False)

    if updates:
        listed = "\n".join(f"- {u}" for u in updates)
        read = f"""Sidekick already has patch {patch}'s notes (researched {done_on}). Since then, the LoL
Wiki's page for the patch ({wiki}) lists these mid-patch updates:
{listed}

Read them there, and in Riot's own words where Riot posted them (Riot adds hotfixes to the
"Patch {patch} Notes" page on https://www.leagueoflegends.com/en-us/news/game-updates/, or posts
them separately). Report only the changes these updates make; leave out everything from the
original patch notes. If an update changes nothing on Summoner's Rift (a queue time, another
mode), say so under NOTES. Use only what Riot and the wiki say: quote them, never add your own
knowledge. Then make two tables."""
        why = (f"Run now: patch {patch} got a mid-patch update after its notes were researched. "
               "Finds what the update changed (champions, game facts).")
    else:
        read = f"""Read the official patch notes for patch {patch} on
https://www.leagueoflegends.com/en-us/news/game-updates/ ("Patch {patch} Notes"). If a newer
"Patch X.Y Notes" is already out, use the newest one and say which under NOTES. Include any
hotfix or mid-patch update listed on that page or on the LoL Wiki's page for the patch
({wiki}). Use only what Riot and the wiki say: quote them, never add your own knowledge. Then
make two tables."""
        why = ("Run at each new patch (the app says when). Finds the champions whose kit changed "
               "(so their notes get re-checked) and any change to the game facts Sidekick shows.")

    out["patch_notes.md"] = _head(
        "Patch notes: kit changes and game facts", why, ALREADY, "patch_notes", batched=False,
        patch=patch) + f"""
## Prompt
{APP}

{read}

**Table A: champions whose kit changed.** Ability, passive, base stat, range, crowd control,
dash, cooldown or cost changes; not skins, and not bug fixes that don't change how they play.
One row per champion, with the notes' own lines as the quote.

**Table B: game facts that changed.** Sidekick shows these facts today:

```csv
{facts_csv}```

Add a row (same columns) for each one the notes change, and for anything new of the same kind:
when objectives or camps spawn or respawn (dragons, Elder Dragon, Void Grubs, Rift Herald, Baron
Nashor, jungle camps, Scuttle Crab, minions), anything added to or removed from Summoner's Rift,
and role quest rewards. Keep the `fact_id` of a row you change; make a new short id for a new
fact. `text` is one or two plain sentences saying only what the notes say. `topic` is
`objective`, `camps` or `role_quest`; `role` is blank, or `top`, `jungle`, `mid`, `bot` or
`support` for a role quest; `checked_on` is today's date. If nothing changed, write
"No game fact changes." instead of Table B.

**Champion ids** for Table A:

{ids}

{_rules(patch, stats=False)}

{_send_back("patch_notes", "champ_id,patch,what_changed,quote",
            about="(Table A: one row per champion whose kit changed.)",
            second="A second CSV code block for Table B with exactly the game facts' columns "
                   "(`fact_id,topic,role,text,source,source_url,patch,checked_on`), or the "
                   'line "No game fact changes."')}
"""

    out["game_facts.md"] = _head(
        "Game facts: re-check every timer and role quest line",
        "Run each patch (the app says when), or when a timer looks wrong. Re-checks the "
        "objective and camp timers and role quest rewards that Sidekick shows, each against "
        "Riot's patch notes or the LoL Wiki.", ALREADY, "game_facts", batched=False,
        patch=patch) + f"""
## Prompt
{APP}

These are the game facts Sidekick shows today, each one statement about Summoner's Rift (not
Swiftplay, ARAM or other modes), with its source and the patch it was checked for:

```csv
{facts_csv}```

For every row, find the current answer for the live patch (patch {patch} when this was
written), using only:
1. Riot's official patch notes (https://www.leagueoflegends.com/en-us/news/game-updates/),
   newest first, hotfixes included: has any later patch or hotfix changed it?
2. The LoL Wiki page for that objective or camp (for example "Dragon pit", "Voidgrub camp",
   "Rift Herald", "Baron Nashor", "Monster"), or "Role Quests", including the page's patch
   history, where Riot's notes don't state it.

Return the whole table: unchanged rows with the same text and `checked_on` set to today;
changed rows with the new `text` (plain sentences, only what the source says), `source`,
`source_url` and `patch`; new rows for anything new of the same kind (a new objective, a new
role quest reward); a removed thing as a row like "X has been removed from the game.". If you
couldn't confirm a row, keep it unchanged and say so under NOT FOUND.

{_rules(patch, stats=False)}

{_send_back("game_facts", "fact_id,topic,role,text,source,source_url,patch,checked_on",
            about="(The whole table, every row.)",
            second="`CHANGES:` each changed or added row's `fact_id` with the exact quote it's "
                   "based on.")}
"""

    out["class_definitions.md"] = _head(
        "Riot's champion class definitions",
        "Run once (again only if Riot changes its classes). Sidekick knows each champion's Riot "
        "class (Vanguard, Catcher...) but not Riot's own words for what each class does, so the "
        "report can't explain a class without making it up.", ALREADY, "class_definitions",
        batched=False, patch=patch) + f"""
## Prompt
{APP}

Find Riot's own description of each League of Legends champion class and subclass: Controller
(Enchanter, Catcher), Fighter (Juggernaut, Diver), Mage (Burst, Battlemage, Artillery),
Marksman, Slayer (Assassin, Skirmisher), Tank (Vanguard, Warden), and Specialist. Quote Riot's
words exactly, one row per class and subclass. Where to look: Riot's champion class articles and
pages on https://www.leagueoflegends.com (news and dev posts about champion classes), and the
LoL Wiki's "Champion classes" page where it quotes Riot (cite the Riot page it quotes when you
can open it).

{_rules(patch, stats=False)}

{_send_back("class_definitions", "class,quote,source,source_url",
            about="One row per class and subclass; `class` exactly as named above (for example "
                  "`Vanguard`); `quote` Riot's words.")}
"""

    out["README.md"] = _readme(patch, len(champs))
    return out


def _readme(patch: str, n: int) -> str:
    return f"""# research/: prompts for what only exists as text

Sidekick measures the numbers itself from Riot's match data (the app does it in the
background), so agents are only needed for facts that exist as words on a page. Everything the
agent needs is inside each prompt (the champion list: {n} champions, patch {patch}; today's game
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
"""


def _csv(columns: Sequence[str], rows: Sequence[Row]) -> str:
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=list(columns), lineterminator="\n",
                            extrasaction="ignore")  # fmt: skip
    writer.writeheader()
    writer.writerows(rows)
    return buffer.getvalue()


def write(folder: Path, files: Mapping[str, str]) -> list[Path]:
    """Write the files whose text changed (the others are left alone); returns those written."""
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "results").mkdir(exist_ok=True)
    written = []
    for name, text in files.items():
        path = folder / name
        text = text.rstrip("\n") + "\n"
        if path.exists() and path.read_text(encoding="utf-8") == text:
            continue
        path.write_text(text, encoding="utf-8", newline="\n")
        written.append(path)
    return written


def regenerate(paths: Paths) -> list[Path]:
    """Rewrite research/*.md from the current data and research status (what's due, a
    mid-patch update); only changed files are written. [] before there's any champion data."""
    version = current_version(paths)
    if not version:
        return []
    tables = load_static(paths, version)
    facts = [r for r in read_csv(paths.manual_dir / "game_facts.csv") if r.get("text")]
    updates = research_import.new_updates(paths, short_patch(version))
    row = research_import.done_rows(paths).get("patch_notes") or {}
    files = prompts(champions(tables), facts, version, updates,
                    row.get("done_on", "") if updates else "")  # fmt: skip
    return write(paths.research_dir, files)
