# Game facts: re-check every timer and role quest line

Run each patch (the app says when), or when a timer looks wrong. Re-checks the objective and camp timers and role quest rewards that Sidekick shows, each against Riot's patch notes or the LoL Wiki.

**For the owner:** Copy everything from **Prompt** to the end of this file into an agent that can browse the web; there's nothing to fill in. Save the agent's whole reply as
`research/results/game_facts-<date>.md`, then in the app:
Settings, Data and updates, **Check research/results**, then **Apply**. Written by Sidekick from
the current data for patch 26.19, and rewritten by itself when that changes; don't edit by hand.

**Sidekick already has (don't ask for these):** Riot's ability text and tips (Data Dragon), Riot's playstyle ratings (damage, toughness, control, mobility, utility), the LoL Wiki's mechanic categories (dash, blink, knock-up, stun, stealth...), OP.GG's matchup win rates, lane-advantage labels, builds, synergies and win rate by game length.

## Prompt
You are collecting facts for Sidekick, a personal app that writes a short pre-game scouting report for League of Legends (Summoner's Rift, ranked solo/duo). It only states facts that come from a named, reputable source, so every value you send needs its source and patch.

These are the game facts Sidekick shows today, each one statement about Summoner's Rift (not
Swiftplay, ARAM or other modes), with its source and the patch it was checked for:

```csv
fact_id,topic,role,text,source,source_url,patch,checked_on
dragon_timers,objective,,"The first dragon spawns at 5:00, and the next one 5 minutes after a dragon dies. After a team's fourth dragon, the Elder Dragon spawns instead, with a 6-minute respawn.",LoL Wiki: Dragon pit,https://wiki.leagueoflegends.com/en-us/Dragon_pit,26.19,2026-10-03
grubs_timer,objective,,"Void Grubs spawn once, at 8:00, and don't respawn.","Riot: Patch 25.09 notes (no change since, per the wiki's Voidgrub camp history)",https://www.leagueoflegends.com/en-us/news/game-updates/patch-25-09-notes/,25.09,2026-10-03
herald_timer,objective,,"The Rift Herald spawns once, at 15:00, and leaves at 19:45 (19:55 if it's in a fight).",Riot: Patch 25.09 notes (spawn); LoL Wiki: Rift Herald (despawn),https://www.leagueoflegends.com/en-us/news/game-updates/patch-25-09-notes/,25.09,2026-10-03
baron_timer,objective,,Baron Nashor spawns at 20:00.,Riot: Patch 26.1 notes,https://www.leagueoflegends.com/en-us/news/game-updates/patch-26-1-notes/,26.1,2026-10-03
atakhan_removed,objective,,Atakhan has been removed from the game.,Riot: Patch 26.1 notes,https://www.leagueoflegends.com/en-us/news/game-updates/patch-26-1-notes/,26.1,2026-10-03
camp_timers,camps,,"Wolves, Blue Sentinel, Red Brambleback and Raptors spawn at 0:55; Krugs and Gromp at 1:07; the Scuttle Crabs at 2:55.",Riot: Patch 26.1 notes,https://www.leagueoflegends.com/en-us/news/game-updates/patch-26-1-notes/,26.1,2026-10-03
minion_timer,camps,,Minions spawn at 0:30.,Riot: Patch 26.1 notes,https://www.leagueoflegends.com/en-us/news/game-updates/patch-26-1-notes/,26.1,2026-10-03
quest_top,role_quest,top,"Top's role quest reward: Unleashed Teleport as a bonus summoner spell (390-second cooldown); if Teleport is already taken, it shields for 35% of maximum health for 10 seconds after the channel and its cooldown drops by 30 seconds. Also 600 experience, 11% bonus experience, 80 bonus experience per takedown, and a level cap of 20.",LoL Wiki: Role Quests (Riot: Patch 26.19 notes for the cooldown),https://wiki.leagueoflegends.com/en-us/Role_Quests,26.19,2026-10-03
quest_jungle,role_quest,jungle,"Jungle's role quest reward: Primal Smite, 10 bonus gold and 10 bonus experience per jungle camp, and 4% movement speed in the jungle or river (8% out of combat).",LoL Wiki: Role Quests,https://wiki.leagueoflegends.com/en-us/Role_Quests,26.19,2026-10-03
quest_mid,role_quest,mid,"Mid's role quest reward: 8% bonus AD and 8% bonus AP, and Tier 2 boots upgrade to exclusive Tier 3 boots for free.",LoL Wiki: Role Quests,https://wiki.leagueoflegends.com/en-us/Role_Quests,26.19,2026-10-03
quest_bot,role_quest,bot,"Bot's role quest reward: 300 gold, 2 bonus gold per minion, 40 bonus gold per champion takedown, and boots move to the role quest slot.",LoL Wiki: Role Quests,https://wiki.leagueoflegends.com/en-us/Role_Quests,26.19,2026-10-03
quest_support,role_quest,support,"Support's role quest reward: Runic Compass upgrades to Bounty of Worlds, and Control Wards cost 40 gold.",LoL Wiki: Role Quests,https://wiki.leagueoflegends.com/en-us/Role_Quests,26.19,2026-10-03
```

For every row, find the current answer for the live patch (patch 26.19 when this was
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
   `fact_id,topic,role,text,source,source_url,patch,checked_on`
   (The whole table, every row.)
2. `CHANGES:` each changed or added row's `fact_id` with the exact quote it's based on.
3. `SOURCES:` every page you used, one address per line.
4. `NOT FOUND:` what you looked for and couldn't find, and where you looked.
5. `NOTES:` anything unclear (optional).

The owner saves your whole reply as `research/results/game_facts-<date>.md`.
