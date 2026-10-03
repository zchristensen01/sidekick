# data/

| Folder | Owner | In git | What |
|---|---|---|---|
| `manual/` | **the owner** | yes | Traits, matchup briefs, your matchup notes, overrides. Code only appends drafted rows (marked `reviewed=n`) or edits through `scout review` with your OK. |
| `generated/` | code | no | Rebuilt by `scout refresh`: static data per patch, `stats.sqlite`, review queue, refresh log. Safe to delete. |
| `cache/` | code | no | Raw responses from data sources, per patch. Safe to delete. |
| `history/` | code | no | Post-game results (M10). Append-only and **not** rebuildable: don't delete. |

Schemas: `scout/data/schemas.py`. Meanings: `docs/DATA.md`, `docs/TRAITS.md`, `docs/KNOWLEDGE.md`.
