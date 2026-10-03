# data/

Only `manual/` lives here. The other data folders are in each user's own Sidekick folder,
`%LOCALAPPDATA%\Sidekick\data\` (`scout/paths.py`), never in the repo.

| Folder | Where | Owner | In git | What |
|---|---|---|---|---|
| `manual/` | here | **the owner** | yes | Traits, matchup briefs, overrides, game facts, class definitions. Code only appends drafted rows (marked `reviewed=n`) or edits through `scout review` with your OK. |
| `generated/` | your Sidekick folder | code | no | Rebuilt by `scout refresh`: static data per patch, `stats.sqlite`, review queue, refresh log. Safe to delete, except that `stats.sqlite` also holds collected match data. |
| `cache/` | your Sidekick folder | code | no | Raw responses from data sources, champion pictures, update downloads. Safe to delete. |
| `history/` | your Sidekick folder | code | no | Post-game results (M10) and the backtest (M20). Post-game results are append-only and **not** rebuildable: don't delete. |

Schemas: `scout/data/schemas.py`. Meanings: `docs/DATA.md`, `docs/TRAITS.md`, `docs/KNOWLEDGE.md`.
