# Riot's champion class definitions

Run once (again only if Riot changes its classes). Sidekick knows each champion's Riot class (Vanguard, Catcher...) but not Riot's own words for what each class does, so the report can't explain a class without making it up.

**For the owner:** Copy everything from **Prompt** to the end of this file into an agent that can browse the web; there's nothing to fill in. Save the agent's whole reply as
`research/results/class_definitions-<date>.md`, then in the app:
Settings, Data and updates, **Check research/results**, then **Apply**. Written by Sidekick from
the current data for patch 26.19, and rewritten by itself when that changes; don't edit by hand.

**Sidekick already has (don't ask for these):** Riot's ability text and tips (Data Dragon), Riot's playstyle ratings (damage, toughness, control, mobility, utility), the LoL Wiki's mechanic categories (dash, blink, knock-up, stun, stealth...), OP.GG's matchup win rates, lane-advantage labels, builds, synergies and win rate by game length.

## Prompt
You are collecting facts for Sidekick, a personal app that writes a short pre-game scouting report for League of Legends (Summoner's Rift, ranked solo/duo). It only states facts that come from a named, reputable source, so every value you send needs its source and patch.

Find Riot's own description of each League of Legends champion class and subclass: Controller
(Enchanter, Catcher), Fighter (Juggernaut, Diver), Mage (Burst, Battlemage, Artillery),
Marksman, Slayer (Assassin, Skirmisher), Tank (Vanguard, Warden), and Specialist. Quote Riot's
words exactly, one row per class and subclass. Where to look: Riot's champion class articles and
pages on https://www.leagueoflegends.com (news and dev posts about champion classes), and the
LoL Wiki's "Champion classes" page where it quotes Riot (cite the Riot page it quotes when you
can open it).

### Rules (follow every one)
- **Sources:** only Riot (patch notes, dev blogs, champion pages, Data Dragon), the LoL Wiki
  (wiki.leagueoflegends.com), and the big stats sites (OP.GG, U.GG, Lolalytics, League of
  Graphs).
- **Only what you saw:** cite only pages you actually opened, and only figures or words you saw
  on them; put each page's address in `source_url`. If you can't browse the web, or a page
  won't load, say so and stop. Never fill anything in from memory.
- **No source, no value:** leave the cell blank. Never estimate, average, guess, or fill a row
  just to complete the table. A short table that's all true beats a full one.
- **No ratings of your own:** collect the sources' figures and words. Don't turn them into
  scores, tiers or labels unless the source itself gives that score, tier or label.
- **Patch:** the current live patch is the newest "Patch X.Y Notes" on
  https://www.leagueoflegends.com/en-us/news/game-updates/ (when this prompt was written it was
  26.19). Write the patch your figure is for in every row; prefer the current patch.
- **Champion ids:** use the `champ_id` column of the list in this prompt exactly (Wukong is
  `MonkeyKing`, Nunu & Willump is `Nunu`). If a champion isn't in the list (a brand-new one),
  use Data Dragon's id: https://ddragon.leagueoflegends.com/api/versions.json gives the newest
  version, then https://ddragon.leagueoflegends.com/cdn/<version>/data/en_US/champion.json.
- **CSV:** exactly the columns shown, one header row; put double quotes around any cell that
  contains a comma.

## What to send back
Reply with these parts, in this order, and nothing else:
1. One CSV code block (start it with three backticks and `csv`) with exactly these columns:
   `class,quote,source,source_url`
   One row per class and subclass; `class` exactly as named above (for example `Vanguard`); `quote` Riot's words.
2. `SOURCES:` every page you used, one address per line.
3. `NOT FOUND:` what you looked for and couldn't find, and where you looked.
4. `NOTES:` anything unclear (optional).

The owner saves your whole reply as `research/results/class_definitions-<date>.md`.
