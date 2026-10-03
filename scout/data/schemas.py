"""Column lists for every CSV and the stats database schema: the single source of truth.

docs/DATA.md, docs/TRAITS.md and docs/KNOWLEDGE.md describe what each column means; if you
change a column here, update those docs in the same change.
"""

# ---------------------------------------------------------------- data/manual/ (hand-owned)

CHAMPION_TRAITS = (
    "champ_id", "role",
    "early", "engage", "cc", "escape", "scaling", "roam", "waveclear", "frontline",
    "spikes", "tags", "style",
    "key_note", "ult_note", "spike_note",
    "reviewed", "reviewed_patch", "source", "notes",
)  # fmt: skip

GAME_FACTS = (  # objective and camp timers, role quests: each line cited (KNOWLEDGE.md)
    "fact_id", "topic", "role", "text", "source", "source_url", "patch", "checked_on",
)  # fmt: skip

CLASS_DEFINITIONS = (  # Riot's own description of each champion class, quoted (M19)
    "class", "quote", "source", "source_url", "checked_on",
)  # fmt: skip

MATCHUP_BRIEFS = (
    "role", "champ_id", "opp_champ_id",
    "levels_1_3", "levels_3_6", "after_6", "first_item", "trade_pattern", "jungle_ask",
    "reviewed", "reviewed_patch", "source", "notes",
)  # fmt: skip

MATCHUP_NOTES = ("role", "champ_id", "opp_champ_id", "note", "date")

CHAMPION_OVERRIDES = ("champ_id", "field", "value", "reason")

MANUAL_FILES: dict[str, tuple[str, ...]] = {
    "champion_traits.csv": CHAMPION_TRAITS,
    "matchup_briefs.csv": MATCHUP_BRIEFS,
    "champion_overrides.csv": CHAMPION_OVERRIDES,
    "game_facts.csv": GAME_FACTS,
    "class_definitions.csv": CLASS_DEFINITIONS,
}

# Trait value rules (docs/TRAITS.md)
TRAIT_SCALES = ("early", "engage", "cc", "escape", "scaling", "roam", "waveclear", "frontline")
TRAIT_SCALE_RANGE = range(0, 4)  # 0-3
TRAIT_TAGS = frozenset({
    "airborne", "needs_airborne", "follows_cc", "peel", "disengage", "ult_engage", "global",
    "ult_join", "point_click_cc", "poke", "sustain", "stealth", "split_push", "invade_strong",
    "lane_bully", "dive", "anti_auto",
})  # fmt: skip
JUNGLE_STYLES = frozenset({"", "ganker", "farmer"})
TRAIT_SOURCES = frozenset({"owner", "prototype", "llm"})

# ---------------------------------------------------------------- data/generated/ (machine-owned)

CHAMPIONS = ("champ_id", "key", "name", "ddragon_version")

ABILITIES = (
    "champ_id", "slot", "name", "max_rank", "cooldowns", "description", "description_hash",
    "ddragon_version",
)  # fmt: skip

CHAMPION_META = (
    "champ_id", "range_type", "attack_range", "move_speed", "damage_type", "classes",
    "legacy_tags",
    "positions", "client_positions",
    "rating_damage", "rating_durability", "rating_cc", "rating_mobility", "rating_utility",
    "difficulty", "mechanics", "last_changed_patch", "opgg_name", "field_sources",
    "ddragon_version",
)  # fmt: skip

SUMMONER_SPELLS = ("key", "spell_id", "name")

ITEMS = ("item_id", "name", "gold_total", "depth", "boots", "ddragon_version")

# Riot's own tips per champion (Data Dragon `allytips` / `enemytips`): kind = ally | enemy.
TIPS = ("champ_id", "kind", "n", "text", "ddragon_version")

REVIEW_QUEUE = (
    "champ_id", "reason", "details", "patch_detected", "created_at", "resolved", "resolved_at",
)  # fmt: skip

REVIEW_REASONS = frozenset({
    "new_champion", "abilities_changed", "patch_changed", "traits_missing", "traits_unreviewed",
    "class_missing", "source_disagreement", "stats_disagree", "patch_notes", "brief_stale",
})  # fmt: skip

STATIC_FILES: dict[str, tuple[str, ...]] = {
    "champions.csv": CHAMPIONS,
    "abilities.csv": ABILITIES,
    "champion_meta.csv": CHAMPION_META,
    "summoner_spells.csv": SUMMONER_SPELLS,
    "items.csv": ITEMS,
    "tips.csv": TIPS,
}

# ---------------------------------------------------------------- data/generated/stats.sqlite

STATS_DB_SCHEMA = """
CREATE TABLE IF NOT EXISTS lane_stats (
    patch TEXT NOT NULL, rank_filter TEXT NOT NULL, role TEXT NOT NULL, champ_id TEXT NOT NULL,
    games INTEGER NOT NULL, wins INTEGER NOT NULL,
    pick_rate REAL, role_rate REAL, ban_rate REAL, tier INTEGER,
    source TEXT NOT NULL, fetched_at TEXT NOT NULL,
    PRIMARY KEY (patch, rank_filter, role, champ_id)
);
CREATE TABLE IF NOT EXISTS matchups (
    patch TEXT NOT NULL, rank_filter TEXT NOT NULL, role TEXT NOT NULL,
    champ_id TEXT NOT NULL, opp_champ_id TEXT NOT NULL,
    games INTEGER NOT NULL, wins INTEGER NOT NULL,
    source TEXT NOT NULL, fetched_at TEXT NOT NULL,
    PRIMARY KEY (patch, rank_filter, role, champ_id, opp_champ_id)
);
CREATE TABLE IF NOT EXISTS matchup_labels (
    patch TEXT NOT NULL, role TEXT NOT NULL, champ_id TEXT NOT NULL, opp_champ_id TEXT NOT NULL,
    lane_advantage TEXT, solo_kill_advantage TEXT, play_style TEXT, tip TEXT,
    source TEXT NOT NULL, fetched_at TEXT NOT NULL,
    PRIMARY KEY (patch, role, champ_id, opp_champ_id)
);
CREATE TABLE IF NOT EXISTS synergies (
    patch TEXT NOT NULL, rank_filter TEXT NOT NULL,
    champ_id TEXT NOT NULL, role TEXT NOT NULL,
    ally_champ_id TEXT NOT NULL, ally_role TEXT NOT NULL,
    games INTEGER NOT NULL, wins INTEGER NOT NULL, tier INTEGER,
    source TEXT NOT NULL, fetched_at TEXT NOT NULL,
    PRIMARY KEY (patch, rank_filter, champ_id, role, ally_champ_id, ally_role)
);
CREATE TABLE IF NOT EXISTS game_length (
    patch TEXT NOT NULL, rank_filter TEXT NOT NULL, role TEXT NOT NULL, champ_id TEXT NOT NULL,
    minute INTEGER NOT NULL, win_rate REAL NOT NULL,
    source TEXT NOT NULL, fetched_at TEXT NOT NULL,
    PRIMARY KEY (patch, rank_filter, role, champ_id, minute)
);
CREATE TABLE IF NOT EXISTS matchup_builds (
    patch TEXT NOT NULL, role TEXT NOT NULL, champ_id TEXT NOT NULL, opp_champ_id TEXT NOT NULL,
    kind TEXT NOT NULL, rank INTEGER NOT NULL, ids TEXT NOT NULL,
    games INTEGER NOT NULL, wins INTEGER NOT NULL,
    source TEXT NOT NULL, fetched_at TEXT NOT NULL,
    PRIMARY KEY (patch, role, champ_id, opp_champ_id, kind, rank)
);
CREATE TABLE IF NOT EXISTS fetch_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT NOT NULL, tool TEXT NOT NULL, args TEXT NOT NULL, fetched_at TEXT NOT NULL,
    ok INTEGER NOT NULL, error TEXT, elapsed_ms INTEGER,
    format_fingerprint TEXT, patch_seen TEXT
);
-- M19: figures measured from Riot's match data (scout/data/measure.py). Totals only: the mean
-- is total / n; no player or game ids (games are remembered by a one-way hash).
CREATE TABLE IF NOT EXISTS measured (
    patch TEXT NOT NULL, champ_id TEXT NOT NULL, role TEXT NOT NULL, metric TEXT NOT NULL,
    n INTEGER NOT NULL, total REAL NOT NULL, total_sq REAL NOT NULL,
    PRIMARY KEY (patch, champ_id, role, metric)
);
CREATE TABLE IF NOT EXISTS collected (
    game_hash TEXT PRIMARY KEY, patch TEXT NOT NULL, collected_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS collector_state (key TEXT PRIMARY KEY, value TEXT NOT NULL);
-- M20: one small record per collected game for the backtest: each side's draft (champions by
-- role) and what happened from that side (scout/postgame/grade.py outcome()); no ids.
CREATE TABLE IF NOT EXISTS games (
    game_hash TEXT PRIMARY KEY, patch TEXT NOT NULL, record TEXT NOT NULL
);
-- The same totals per matchup: a champion against its lane opponent in a role (a few metrics,
-- scout/data/measure.py MATCHUP_METRICS). docs/MATCH_DATA.md.
CREATE TABLE IF NOT EXISTS measured_matchups (
    patch TEXT NOT NULL, champ_id TEXT NOT NULL, role TEXT NOT NULL, opp_champ_id TEXT NOT NULL,
    metric TEXT NOT NULL, n INTEGER NOT NULL, total REAL NOT NULL, total_sq REAL NOT NULL,
    PRIMARY KEY (patch, champ_id, role, opp_champ_id, metric)
);
"""
