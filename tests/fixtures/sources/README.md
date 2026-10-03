# Source fixtures

Small real responses from each external data source, captured 2026-10-02 (Data Dragon
16.19.1, in-game patch 26.19). Parsers are built and tested against these. Do not edit by
hand; re-capture instead. Field names and nesting are untouched; "trimmed" means list
entries or bulky subtrees were dropped.

| File | Source URL | Captured | Trimmed |
|---|---|---|---|
| `ddragon/versions.json` | https://ddragon.leagueoflegends.com/api/versions.json | 2026-10-02 | First 5 of the version list |
| `ddragon/champion.json` | https://ddragon.leagueoflegends.com/cdn/16.19.1/data/en_US/champion.json | 2026-10-02 | `data` cut to LeeSin, Nautilus, Gnar, Jayce, Lillia, MonkeyKing, Chogath (7 of 173) |
| `ddragon/champion_LeeSin.json` | https://ddragon.leagueoflegends.com/cdn/16.19.1/data/en_US/champion/LeeSin.json | 2026-10-02 | Removed `skins`, `lore`, `allytips`, `enemytips`, `recommended` |
| `ddragon/championFull_sample.json` | https://ddragon.leagueoflegends.com/cdn/16.19.1/data/en_US/championFull.json | 2026-10-02 | `data` cut to Elise, Gnar, LeeSin, Nautilus (4 of 173), `keys` to match; removed `skins`, `lore`, `allytips`, `enemytips`, `recommended` |
| `ddragon/item_sample.json` | https://ddragon.leagueoflegends.com/cdn/16.19.1/data/en_US/item.json | 2026-10-02 | `data` cut to 8 of 870 items (6 buyable on Summoner's Rift, Emberknife (not on the map), Fortification (on the map, not buyable)); removed each item's `description` and the top-level `tree`, `groups`, `basic` |
| `ddragon/summoner.json` | https://ddragon.leagueoflegends.com/cdn/16.19.1/data/en_US/summoner.json | 2026-10-02 | `data` cut to Flash, Smite, Ignite, Teleport, Exhaust, Heal, Barrier, Ghost, Cleanse (9 of 34) |
| `cdragon/champion-summary.json` | https://raw.communitydragon.org/latest/plugins/rcp-be-lol-game-data/global/default/v1/champion-summary.json | 2026-10-02 | 9 of 246 entries: id -1, the 7 champs above, and `Jade_LeeSin` (60064) as an example of a non-standard entry to filter out |
| `cdragon/champion_64.json` | https://raw.communitydragon.org/latest/plugins/rcp-be-lol-game-data/global/default/v1/champions/64.json | 2026-10-02 | Removed `skins`, `shortBio` |
| `cdragon/champion_111.json` | https://raw.communitydragon.org/latest/plugins/rcp-be-lol-game-data/global/default/v1/champions/111.json | 2026-10-02 | Removed `skins`, `shortBio` |
| `cdragon/champion_60.json` | https://raw.communitydragon.org/16.19/plugins/rcp-be-lol-game-data/global/default/v1/champions/60.json | 2026-10-02 | Removed `skins`, `shortBio` (Elise) |
| `cdragon/champion_150.json` | https://raw.communitydragon.org/16.19/plugins/rcp-be-lol-game-data/global/default/v1/champions/150.json | 2026-10-02 | Removed `skins`, `shortBio` (Gnar: ranged here, though Data Dragon's attack range says melee) |
| `cdragon/content-metadata.json` | https://raw.communitydragon.org/latest/content-metadata.json | 2026-10-02 | None (shows which game version `latest` points at) |
| `wiki/ChampionData_sample.lua` | https://wiki.leagueoflegends.com/en-us/Module:ChampionData/data?action=raw | 2026-10-02 | 5 of 175 entries (Elise, Gnar, Mega Gnar, Lee Sin, Nautilus); one source/license comment line added at the top. CC BY-SA 3.0 |
| `wiki/attributes.json` | https://wiki.leagueoflegends.com/en-us/api.php?action=query&list=categorymembers&cmtitle=Category:Advanced+attributes&cmtype=subcat&cmlimit=max&format=json | 2026-10-03 | None (the wiki's list of mechanic categories). CC BY-SA 3.0 |
| `wiki/categories_sample.json` | api.php?action=query&prop=categories&titles=Elise\|Gnar\|Lee+Sin\|Nautilus&cllimit=max&redirects=1&format=json | 2026-10-03 | None. CC BY-SA 3.0 |
| `wiki/categories_redirect.json` | the same, titles=Nunu+&+Willump\|Kai'Sa | 2026-10-03 | None (shows a redirected title: the page is "Nunu"). CC BY-SA 3.0 |
| `wiki/patch_page_sections_26_19.json` | https://wiki.leagueoflegends.com/en-us/api.php?action=parse&page=V26.19&prop=sections&format=json | 2026-10-03 | `servedby` dropped. A mid-patch update as its own section ("October 2nd Queue Update"). CC BY-SA 3.0 |
| `wiki/patch_page_sections_26_10.json` | the same, page=V26.10 | 2026-10-03 | `servedby` dropped. A "Hotfixes" section with a dated entry ("May 14th Hotfix"). CC BY-SA 3.0 |
| `wiki/patch_page_missing.json` | the same, page=V26.30 | 2026-10-03 | `servedby` dropped. The answer for a patch with no page yet (`missingtitle`) |
| `opgg/initialize.json` | MCP `initialize` at https://mcp-api.op.gg/mcp | 2026-10-02 | None |
| `opgg/tools_list.json` | MCP `tools/list` | 2026-10-02 | None (all 29 tools, full schemas) |
| `opgg/lane_meta_jungle.json` | `lol_list_lane_meta_champions` position=jungle | 2026-10-02 | None |
| `opgg/lane_meta_all.json` | `lol_list_lane_meta_champions` position=all | 2026-10-02 | None |
| `opgg/champion_analysis_LeeSin_jungle.json` | `lol_get_champion_analysis` LEE_SIN jungle, stats/counters/synergy fields only | 2026-10-02 | None |
| `opgg/champion_analysis_LeeSin_jungle_allfields.json` | same, without `desired_output_fields` (server returns every field) | 2026-10-02 | None |
| `opgg/champion_analysis_LeeSin_jungle_challenger.json` | same, `tier=challenger` (shows `CountersMeta` when counters are empty) | 2026-10-02 | None |
| `opgg/champion_analysis_MonkeyKing_jungle.json` | same, `champion=MONKEY_KING` (name normalization, two positions) | 2026-10-02 | None |
| `opgg/lane_matchup_guide_LeeSin_vs_Elise_jungle.json` | `lol_get_lane_matchup_guide` LEE_SIN vs ELISE jungle | 2026-10-02 | Inside the JSON text: build lists (items, runes, skills, rune_pages, single/combination items, single_runes, trends) cut to 2-3 entries. `counters` (59), `game_lengths`, `summary` and the advantage/tip strings are complete |
| `opgg/lane_matchup_guide_Darius_vs_Swain_mid.json` | `lol_get_lane_matchup_guide` DARIUS vs SWAIN mid | 2026-10-03 | None (the whole answer). An off-role pick: every `game_lengths` rate is null |
| `opgg/champion_synergies_Samira_bot.json` | `lol_get_champion_synergies` SAMIRA adc + support | 2026-10-02 | None |
| `opgg/list_champions.json` | `lol_list_champions` | 2026-10-02 | None |
| `opgg/summoner_profile.json` | `lol_get_summoner_profile` in OP.GG's real answer format, rank/champion fields only | 2026-10-03 | A made-up player: rank, records and champions are invented; no names, tags or ids |
| `opgg/error_unknown_champion.json` | `lol_get_lane_matchup_guide` with my_champion=NOT_A_CHAMP | 2026-10-02 | None (JSON-RPC error shape) |
| `opgg/requests.json` | Exact tool name and arguments behind each OP.GG fixture | 2026-10-02 | n/a |
| `riot/queues.json` | https://static.developer.riotgames.com/docs/lol/queues.json | 2026-10-02 | Queue ids 0, 400, 420, 430, 440, 450, 480, 490, 700, 1700, 2400 (11 of 99) |

OP.GG files store the full JSON-RPC response message (`jsonrpc`, `id`, `result` or `error`).
Tool output is in `result.content[0].text`.
