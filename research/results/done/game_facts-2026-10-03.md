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

CHANGES:
None. No row changed, and nothing new of the same kind (a new objective or a new role quest reward) was added between the patches each row was last confirmed on and the current live patch, 26.19. The newest "Patch X.Y Notes" on Riot's game-updates page is still "League of Legends Patch 26.19 Notes" (2026-09-22). Every row was re-checked against these pages:
- dragon_timers: Dragon pit wiki: "At 5 minutes into the game, an elemental drake ... of a random type spawns in the dragon pit. When a drake is slain, the next drake will respawn after 5 minutes elapse" and "Once a team has killed their fourth drake, the camp will now instead spawn the Elder Dragon with a 6 minute respawn timer." Elder Dragon wiki infobox: "Respawn 6:00".
- grubs_timer: Voidgrub camp wiki: "Initial 8:00"; "The camp spawns only once per game"; patch history V25.09: "Removed: Voidgrubs no longer respawn ... Spawn time increased to 8:00 from 6:00." The only later entry, V26.01, changes stats and rewards, not timers.
- herald_timer: Rift Herald wiki: "Initial 15:00"; "The Rift Herald only spawns once per game, and despawns permanently at 19:45, or 19:55 if in combat." Patch history V25.09: "Spawn time reduced to 15:00 from 16:00." Later entries (V26.01, V26.06, V26.12) are stats and bugfixes only.
- baron_timer: Riot 26.1: "Baron Nashor: 25:00 ⇒ 20:00". Baron Nashor wiki infobox: "Initial 20:00".
- atakhan_removed: Riot 26.1: "Atakhan has been removed from the game and will no longer spawn."
- camp_timers: Riot 26.1: "Murk Wolf, Blue Sentinel, Red Brambleback, Raptor Camps: Spawn at 55 seconds"; "Krug, Gromp Camps: Spawn at 1:07"; "River Scuttler Camps: Spawn at 2:55".
- minion_timer: Riot 26.1: "Minion spawn time: 1:05 ⇒ 30 seconds".
- quest_top: Riot 26.19: "Top Role Quest's Free Teleport Cooldown: 420 seconds ⇒ 390 seconds". Role Quests wiki: "Gain Unleashed Teleport as a bonus summoner spell in the Role Quest slot (390 second cooldown). If Teleport was already equipped as a summoner spell, empower it to grant a shield after the channel that lasts for 10 seconds and absorbs damage equal to 35% maximum health, and Unleashed Teleport's cooldown is reduced by 30 seconds. Gain 600 experience. Gain 11% bonus experience from all sources. Gain 80 bonus experience on champion takedown. Increase the level cap to 20."
- quest_jungle: Role Quests wiki: "Upgrade Unleashed Smite into Primal Smite. Gain 10 bonus gold and 10 bonus experience from jungle camps. Gain 4% bonus movement speed while in the jungle or river, increased to 8% while out of combat."
- quest_mid: Role Quests wiki: "Gain 8% bonus AD and 8% AP. Tier 2 Boots are upgraded to exclusive Tier 3 Boots at no cost."
- quest_bot: Role Quests wiki: "Gain 300. Minion kills grant 2 bonus gold. Champion takedowns grant 40 bonus gold. The Role Quest slot is now reserved for any equipped Boots item."
- quest_support: Role Quests wiki: "Upgrade Runic Compass into Bounty of Worlds ... Control Ward cost at the shop reduced to 40."

SOURCES:
https://www.leagueoflegends.com/en-us/news/game-updates/
https://www.leagueoflegends.com/en-us/news/game-updates/league-of-legends-patch-26-19-notes/
https://www.leagueoflegends.com/en-us/news/game-updates/league-of-legends-patch-26-18-notes/
https://www.leagueoflegends.com/en-us/news/game-updates/league-of-legends-patch-26-17-notes/
https://www.leagueoflegends.com/en-us/news/game-updates/league-of-legends-patch-26-9-notes/
https://www.leagueoflegends.com/en-us/news/game-updates/patch-26-1-notes/
https://wiki.leagueoflegends.com/en-us/Role_Quests
https://wiki.leagueoflegends.com/en-us/Dragon_pit
https://wiki.leagueoflegends.com/en-us/Elder_Dragon
https://wiki.leagueoflegends.com/en-us/Voidgrub_camp
https://wiki.leagueoflegends.com/en-us/Rift_Herald
https://wiki.leagueoflegends.com/en-us/Baron_pit
https://wiki.leagueoflegends.com/en-us/Baron_Nashor

NOT FOUND:
- Patch 26.20 notes: not published. As of 2026-10-03, the newest notes on https://www.leagueoflegends.com/en-us/news/game-updates/ are 26.19, so 26.19 is the live patch.
- Riot notes not opened: 26.2–26.8 and 26.10–26.16, plus the 25.09 notes page cited in the grubs_timer and herald_timer rows (25.10–25.24 were not opened either). For the patches in between, I relied on the patch-history sections of the wiki pages I opened (Role Quests, Voidgrub camp, Rift Herald). None of them lists a timer or reward change in that window other than the ones already in the table.
- Dragon pit and Baron Nashor wiki pages: the patch-history sections didn't load (page cut off). The current spawn values I report were read from the body and infobox of each page.
- Jungle camp and minion wiki pages (Murk Wolf camp, Raptor camp, Krug camp, Gromp, Blue Sentinel, Red Brambleback, Rift Scuttler camp, Minion): seen only as search-result snippets, never opened. The snippets show V26.01 (0:55 / 1:07 / 2:55 / 0:30) as the latest timer change. The camp_timers and minion_timer rows rest on Riot's 26.1 notes, which I did open.

NOTES:
- Riot's 26.9 and 26.18 notes were opened by a research helper during this check, not by me directly. 26.9 holds the role quest changes the wiki history lists under V26.09 (top: "+80 flat XP on champion takedown; +11% from all other sources"; mid: "+6% Bonus AD and 6% Bonus AP"; bot: "Bonus Takedown Gold: 50g ⇒ 40g"). The wiki shows later updates (mid 8%/8% in V26.11, the top shield in V26.12, the top cooldown in V26.19), and the table already reflects all of them. 26.18 changed no role quest or objective timer on Summoner's Rift; its "modern jungle timers" Council result applies to League Classic only.
- Conflict on the wiki: the Baron pit page still says "The Voidgrubs spawn at 6:00 game time". The Voidgrub camp page says "Initial 8:00", and its V25.09 history entry reads "Spawn time increased to 8:00 from 6:00". I kept 8:00 and treat the Baron pit line as stale.
- Patch 26.19 also changed World Atlas and Runic Compass health and health regeneration ("Health: 30 / 100 / 200 ⇒ 0 / 60 / 200"). That is a support item stat change, not a change to the support role quest reward, so quest_support is unchanged.
- Patch columns were left as they were for unchanged rows, since none of those figures changed in a later patch.
