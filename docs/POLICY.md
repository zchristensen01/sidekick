# POLICY: what Riot allows, and what that means for this app

Checked 2026-10-02. Riot's policies change; re-check the sources when adding a feature that
touches other players, the game client, or in-game time. When in doubt, don't build it.

## The rules that matter (quoted)
From the League section of Riot's developer policies (https://developer.riotgames.com/docs/lol#game-policy)
and the general policies (https://developer.riotgames.com/policies/general, updated 2025-05-29):
- "Products should not remove game decisions, but may highlight decisions that are important and
  give multiple choices to help players make good decisions."
- Unapproved: "Apps that dictate player decisions."
- Approved: "Game overlays that provide static data that is available prior to the game."
- "Products must not use or incorporate information not present in the game client that would
  give players a competitive edge (e.g., automatically or manually allowing tracking enemy
  ultimate cooldowns)."
- "Products cannot identify or analyze players who are deliberately hidden by the game."
- "Products cannot create alternatives for official skill ranking systems such as the ranked
  ladder. Prohibited alternatives include MMR or ELO calculators."
- Unapproved: "Products may not provide any game-session-specific information that would be
  previously unknown to the player."
- "If your product serves players, you must register it ... regardless of whether or not your
  product uses official documented APIs."

Riot Support's "Third Party Applications" page (Feb 2025) also lists as prohibited: "Exposing
information that's intentionally obfuscated" and "Drawing conclusions for you during gameplay".

## Timeline of changes worth knowing
- 2022-11: no player names or stats in Ranked Solo/Duo champ select.
- 2025-03-13: enemy ultimate timers banned (automatic or manual).
- 2025-10 (patch 25.20): streamer mode can hide a player's name "in third party apps".
- 2025-10: Spectator API results respect streamer mode; live spectating removed.
- 2026-10-06: game-memory access blocked for unknown third-party apps (irrelevant: we never read memory).

## What this means for us
| Allowed (and what we do) | Not allowed (and never build) |
|---|---|
| A pre-game report from champion picks and public stats | Anything computed from the game itself; live advice during it |
| Highlighting threats and options with reasons | Commands ("go gank top now"), live prompts |
| Our own team's picks, positions, and spells in champ select | Names or lookups of players in Ranked Solo/Duo champ select |
| Loading-screen info Riot shows (names appear there) for duo / one-trick notes (M11) and players' public OP.GG records (M16, below) | Analysing anyone in streamer mode or with a hidden identity |
| The owner's own match history (post-game check; their recent games and mastery for champion suggestions, M22) | Per-player skill, MMR, or Elo estimates |
| Reading the client's local API with GET | Any write to the client; reading game memory |
| Static, sourced timers in the pre-game report: objective and camp spawn times (`data/manual/game_facts.csv`), ability cooldowns (Riot's data) | Live or tracked timers: counting down or tracking anything once the game runs (enemy ultimates, summoner spells, objectives) |

Practical rules for code:
- Champ select code never reads `gameName`, `tagLine`, or `puuid` of other players. Recorded
  fixtures scrub them (`LCU.md`).
- At game start the recorder keeps each player's champion, position and summoner spells (what
  the loading screen shows) as a test answer key, with no identities. `scout watch` uses the
  same roster once to confirm enemy roles in the final report (M6). Results computed from
  pre-game data (the written report, players' records, likely duos, one-tricks, stats that
  were still loading) can finish arriving shortly after the game starts. Nothing is
  computed from the game itself, and no live advice is given.
- Pick suggestions (M9b) are options with reasons, never a single "pick this": up to 3, and at
  least 2 whenever two candidates exist (a pool with fewer than 2 available champions is topped
  up from most-played, then from easy champions strong this patch). With one candidate in all
  of those, that one is shown; with none, the list says there's nothing to suggest yet.
- Loading-screen features (M11) skip any player whose identity is hidden (null puuid, streamer
  mode) and say the result is partial. They never try to work out a hidden player from
  teammates' histories.
- Rule text is phrased as options with reasons (`RULES.md`).
- Don't send other players' identifiers to the LLM. Send derived facts only ("likely duo with
  their jungler").
- Players' records at the loading screen (M16, the owner's decision 2026-10-03, personal use with a
  friend): each visible player's public OP.GG record (solo rank as shown, ranked games, wins
  and average kills / deaths / assists on the champion they're playing, recent results). No
  MMR or skill estimate of our own, never in champ select, hidden players skipped, Riot IDs
  kept in memory only; reports say "their Sivir player". The outside review (2026-10-02) read
  Riot's developer policy as discouraging showing other players' rank or win rate; the owner chose
  to keep the feature, switchable in Settings (`report.player_records`, on by default), and
  it's the owner's call.

## Registration
Register a **personal API key** product on the Riot Developer Portal before M10 (post-game
check) or M11 (loading screen). Personal keys are for "products that are intended for just the
developer or a small private community", don't expire daily (dev keys do, every 24 h), and League
ones were being auto-approved in 2025-2026. In the product description, list the read-only LCU
endpoints we use (`LCU.md` section 2) and the Riot API endpoints. Limits: 20 requests per second
and 100 per 2 minutes, per region.

## If this ever goes beyond personal use
Sharing with friends would mean: a production key or staying within "small private community",
each user's own Anthropic key or a local model, Windows packaging, and trait data that doesn't
depend on the owner reviewing everything. Out of scope for v1 (`SPEC.md`).
