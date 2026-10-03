# Patch notes: kit changes and game facts

Run at each new patch (the app says when). Finds the champions whose kit changed (so their notes get re-checked) and any change to the game facts Sidekick shows.

**For the owner:** Copy everything from **Prompt** to the end of this file into an agent that can browse the web; there's nothing to fill in. Save the agent's whole reply as
`research/results/patch_notes-<date>.md`, then in the app:
Settings, Data and updates, **Check research/results**, then **Apply**. Written by Sidekick from
the current data for patch 26.19, and rewritten by itself when that changes; don't edit by hand.

**Sidekick already has (don't ask for these):** Riot's ability text and tips (Data Dragon), Riot's playstyle ratings (damage, toughness, control, mobility, utility), the LoL Wiki's mechanic categories (dash, blink, knock-up, stun, stealth...), OP.GG's matchup win rates, lane-advantage labels, builds, synergies and win rate by game length.

## Prompt
You are collecting facts for Sidekick, a personal app that writes a short pre-game scouting report for League of Legends (Summoner's Rift, ranked solo/duo). It only states facts that come from a named, reputable source, so every value you send needs its source and patch.

Read the official patch notes for patch 26.19 on
https://www.leagueoflegends.com/en-us/news/game-updates/ ("Patch 26.19 Notes"). If a newer
"Patch X.Y Notes" is already out, use the newest one and say which under NOTES. Include any
hotfix or mid-patch update listed on that page or on the LoL Wiki's page for the patch
(https://wiki.leagueoflegends.com/en-us/V26.19). Use only what Riot and the wiki say: quote them, never add your own knowledge. Then
make two tables.

**Table A: champions whose kit changed.** Ability, passive, base stat, range, crowd control,
dash, cooldown or cost changes; not skins, and not bug fixes that don't change how they play.
One row per champion, with the notes' own lines as the quote.

**Table B: game facts that changed.** Sidekick shows these facts today:

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

Add a row (same columns) for each one the notes change, and for anything new of the same kind:
when objectives or camps spawn or respawn (dragons, Elder Dragon, Void Grubs, Rift Herald, Baron
Nashor, jungle camps, Scuttle Crab, minions), anything added to or removed from Summoner's Rift,
and role quest rewards. Keep the `fact_id` of a row you change; make a new short id for a new
fact. `text` is one or two plain sentences saying only what the notes say. `topic` is
`objective`, `camps` or `role_quest`; `role` is blank, or `top`, `jungle`, `mid`, `bot` or
`support` for a role quest; `checked_on` is today's date. If nothing changed, write
"No game fact changes." instead of Table B.

**Champion ids** for Table A:

| # | champ_id | name |
|---|---|---|
| 1 | Aatrox | Aatrox |
| 2 | Ahri | Ahri |
| 3 | Akali | Akali |
| 4 | Akshan | Akshan |
| 5 | Alistar | Alistar |
| 6 | Ambessa | Ambessa |
| 7 | Amumu | Amumu |
| 8 | Anivia | Anivia |
| 9 | Annie | Annie |
| 10 | Aphelios | Aphelios |
| 11 | Ashe | Ashe |
| 12 | AurelionSol | Aurelion Sol |
| 13 | Aurora | Aurora |
| 14 | Azir | Azir |
| 15 | Bard | Bard |
| 16 | Belveth | Bel'Veth |
| 17 | Blitzcrank | Blitzcrank |
| 18 | Brand | Brand |
| 19 | Braum | Braum |
| 20 | Briar | Briar |
| 21 | Caitlyn | Caitlyn |
| 22 | Camille | Camille |
| 23 | Cassiopeia | Cassiopeia |
| 24 | Chogath | Cho'Gath |
| 25 | Corki | Corki |
| 26 | Darius | Darius |
| 27 | Diana | Diana |
| 28 | Draven | Draven |
| 29 | DrMundo | Dr. Mundo |
| 30 | Ekko | Ekko |
| 31 | Elise | Elise |
| 32 | Evelynn | Evelynn |
| 33 | Ezreal | Ezreal |
| 34 | Fiddlesticks | Fiddlesticks |
| 35 | Fiora | Fiora |
| 36 | Fizz | Fizz |
| 37 | Galio | Galio |
| 38 | Gangplank | Gangplank |
| 39 | Garen | Garen |
| 40 | Gnar | Gnar |
| 41 | Gragas | Gragas |
| 42 | Graves | Graves |
| 43 | Gwen | Gwen |
| 44 | Hecarim | Hecarim |
| 45 | Heimerdinger | Heimerdinger |
| 46 | Hwei | Hwei |
| 47 | Illaoi | Illaoi |
| 48 | Irelia | Irelia |
| 49 | Ivern | Ivern |
| 50 | Janna | Janna |
| 51 | JarvanIV | Jarvan IV |
| 52 | Jax | Jax |
| 53 | Jayce | Jayce |
| 54 | Jhin | Jhin |
| 55 | Jinx | Jinx |
| 56 | Kaisa | Kai'Sa |
| 57 | Kalista | Kalista |
| 58 | Karma | Karma |
| 59 | Karthus | Karthus |
| 60 | Kassadin | Kassadin |
| 61 | Katarina | Katarina |
| 62 | Kayle | Kayle |
| 63 | Kayn | Kayn |
| 64 | Kennen | Kennen |
| 65 | Khazix | Kha'Zix |
| 66 | Kindred | Kindred |
| 67 | Kled | Kled |
| 68 | KogMaw | Kog'Maw |
| 69 | KSante | K'Sante |
| 70 | Leblanc | LeBlanc |
| 71 | LeeSin | Lee Sin |
| 72 | Leona | Leona |
| 73 | Lillia | Lillia |
| 74 | Lissandra | Lissandra |
| 75 | Locke | Locke |
| 76 | Lucian | Lucian |
| 77 | Lulu | Lulu |
| 78 | Lux | Lux |
| 79 | Malphite | Malphite |
| 80 | Malzahar | Malzahar |
| 81 | Maokai | Maokai |
| 82 | MasterYi | Master Yi |
| 83 | Mel | Mel |
| 84 | Milio | Milio |
| 85 | MissFortune | Miss Fortune |
| 86 | MonkeyKing | Wukong |
| 87 | Mordekaiser | Mordekaiser |
| 88 | Morgana | Morgana |
| 89 | Naafiri | Naafiri |
| 90 | Nami | Nami |
| 91 | Nasus | Nasus |
| 92 | Nautilus | Nautilus |
| 93 | Neeko | Neeko |
| 94 | Nidalee | Nidalee |
| 95 | Nilah | Nilah |
| 96 | Nocturne | Nocturne |
| 97 | Nunu | Nunu & Willump |
| 98 | Olaf | Olaf |
| 99 | Orianna | Orianna |
| 100 | Ornn | Ornn |
| 101 | Pantheon | Pantheon |
| 102 | Poppy | Poppy |
| 103 | Pyke | Pyke |
| 104 | Qiyana | Qiyana |
| 105 | Quinn | Quinn |
| 106 | Rakan | Rakan |
| 107 | Rammus | Rammus |
| 108 | RekSai | Rek'Sai |
| 109 | Rell | Rell |
| 110 | Renata | Renata Glasc |
| 111 | Renekton | Renekton |
| 112 | Rengar | Rengar |
| 113 | Riven | Riven |
| 114 | Rumble | Rumble |
| 115 | Ryze | Ryze |
| 116 | Samira | Samira |
| 117 | Sejuani | Sejuani |
| 118 | Senna | Senna |
| 119 | Seraphine | Seraphine |
| 120 | Sett | Sett |
| 121 | Shaco | Shaco |
| 122 | Shen | Shen |
| 123 | Shyvana | Shyvana |
| 124 | Singed | Singed |
| 125 | Sion | Sion |
| 126 | Sivir | Sivir |
| 127 | Skarner | Skarner |
| 128 | Smolder | Smolder |
| 129 | Sona | Sona |
| 130 | Soraka | Soraka |
| 131 | Swain | Swain |
| 132 | Sylas | Sylas |
| 133 | Syndra | Syndra |
| 134 | TahmKench | Tahm Kench |
| 135 | Taliyah | Taliyah |
| 136 | Talon | Talon |
| 137 | Taric | Taric |
| 138 | Teemo | Teemo |
| 139 | Thresh | Thresh |
| 140 | Tristana | Tristana |
| 141 | Trundle | Trundle |
| 142 | Tryndamere | Tryndamere |
| 143 | TwistedFate | Twisted Fate |
| 144 | Twitch | Twitch |
| 145 | Udyr | Udyr |
| 146 | Urgot | Urgot |
| 147 | Varus | Varus |
| 148 | Vayne | Vayne |
| 149 | Veigar | Veigar |
| 150 | Velkoz | Vel'Koz |
| 151 | Vex | Vex |
| 152 | Vi | Vi |
| 153 | Viego | Viego |
| 154 | Viktor | Viktor |
| 155 | Vladimir | Vladimir |
| 156 | Volibear | Volibear |
| 157 | Warwick | Warwick |
| 158 | Xayah | Xayah |
| 159 | Xerath | Xerath |
| 160 | XinZhao | Xin Zhao |
| 161 | Yasuo | Yasuo |
| 162 | Yone | Yone |
| 163 | Yorick | Yorick |
| 164 | Yunara | Yunara |
| 165 | Yuumi | Yuumi |
| 166 | Zaahen | Zaahen |
| 167 | Zac | Zac |
| 168 | Zed | Zed |
| 169 | Zeri | Zeri |
| 170 | Ziggs | Ziggs |
| 171 | Zilean | Zilean |
| 172 | Zoe | Zoe |
| 173 | Zyra | Zyra |

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
   `champ_id,patch,what_changed,quote`
   (Table A: one row per champion whose kit changed.)
2. A second CSV code block for Table B with exactly the game facts' columns (`fact_id,topic,role,text,source,source_url,patch,checked_on`), or the line "No game fact changes."
3. `SOURCES:` every page you used, one address per line.
4. `NOT FOUND:` what you looked for and couldn't find, and where you looked.
5. `NOTES:` anything unclear (optional).

The owner saves your whole reply as `research/results/patch_notes-<date>.md`.
