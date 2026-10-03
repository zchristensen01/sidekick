"""The stats database (data/generated/stats.sqlite): OP.GG numbers per patch, with fetch times.

Every table stores wins and games, not just a rate, keyed by OP.GG's patch label ("16.19").
Champions are stored by Data Dragon id (e.g. "LeeSin"). Upserts replace a row with the same key.
Schema: scout/data/schemas.py (STATS_DB_SCHEMA); docs/DATA.md (Stats database). Safe to delete:
only previous-patch history is lost (OP.GG doesn't serve old patches).
"""

import json
import sqlite3
import threading
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from scout.data.measure import MATCHUP_METRICS
from scout.data.opgg import SOURCE, Guide, LaneRow, SynergyRow
from scout.data.schemas import STATS_DB_SCHEMA
from scout.model.roles import Role

DEFAULT_RANK = "opgg_default"


@dataclass(frozen=True)
class Counts:
    games: float
    wins: float

    @property
    def rate(self) -> float:
        return self.wins / self.games if self.games else 0.5


@dataclass(frozen=True)
class Labels:
    lane_advantage: str  # us | them | even | "" (from the first champion's side)
    solo_kill_advantage: str
    play_style: str
    tip: str


class StatsDb:
    """Thread-safe: the watcher's prefetch threads write while reports read."""

    def __init__(self, path: Path | str, rank_filter: str = DEFAULT_RANK) -> None:
        if isinstance(path, Path):
            path.parent.mkdir(parents=True, exist_ok=True)
        self.rank = rank_filter
        self._db = sqlite3.connect(str(path), check_same_thread=False)
        self._lock = threading.Lock()
        with self._lock:
            self._db.executescript(STATS_DB_SCHEMA)

    def close(self) -> None:
        with self._lock:
            self._db.close()

    # ------------------------------------------------------------ writes

    def put_lane_meta(self, patch: str, rows: Iterable[tuple[str, LaneRow]], at: str) -> int:
        """(champ_id, row) pairs from lane meta. Returns rows written."""
        values = [
            (
                patch,
                self.rank,
                r.role.value,
                champ,
                r.games,
                r.wins,
                r.pick_rate,
                r.role_rate,
                r.ban_rate,
                r.tier,
                SOURCE,
                at,
            )
            for champ, r in rows
        ]
        self._write("INSERT OR REPLACE INTO lane_stats VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", values)
        return len(values)

    def put_guide(
        self, guide: Guide, champ: str, opp: str, champ_by_key: Mapping[int, str], at: str
    ) -> None:
        """My full matchup table, the pair's labels, my game-length rates and the builds."""
        role, patch = guide.role.value, guide.patch
        table = [
            (patch, self.rank, role, champ, champ_by_key[key], games, wins, SOURCE, at)
            for key, games, wins in guide.counters
            if key in champ_by_key
        ]
        self._write("INSERT OR REPLACE INTO matchups VALUES (?,?,?,?,?,?,?,?,?)", table)
        self._write(
            "INSERT OR REPLACE INTO matchup_labels VALUES (?,?,?,?,?,?,?,?,?,?)",
            [
                (
                    patch,
                    role,
                    champ,
                    opp,
                    guide.lane_advantage,
                    guide.solo_kill_advantage,
                    guide.play_style,
                    guide.tip,
                    SOURCE,
                    at,
                )
            ],
        )
        self._write(
            "INSERT OR REPLACE INTO game_length VALUES (?,?,?,?,?,?,?,?)",
            [
                (patch, self.rank, role, champ, minute, rate, SOURCE, at)
                for minute, rate in guide.game_lengths.items()
            ],
        )
        self._write(
            "DELETE FROM matchup_builds WHERE patch=? AND role=? AND champ_id=? AND opp_champ_id=?",
            [(patch, role, champ, opp)],
        )
        self._write(
            "INSERT OR REPLACE INTO matchup_builds VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            [
                (
                    patch,
                    role,
                    champ,
                    opp,
                    kind,
                    rank,
                    "|".join(map(str, b.ids)),
                    b.games,
                    b.wins,
                    SOURCE,
                    at,
                )
                for kind, builds in guide.builds.items()
                for rank, b in enumerate(builds, 1)
            ],
        )
        if guide.my_games and guide.my_win_rate is not None:  # base rate, if lane meta lacks it
            self._write(
                "INSERT OR IGNORE INTO lane_stats VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                [
                    (
                        patch,
                        self.rank,
                        role,
                        champ,
                        guide.my_games,
                        round(guide.my_games * guide.my_win_rate),
                        None,
                        None,
                        None,
                        None,
                        SOURCE,
                        at,
                    )
                ],
            )

    def put_synergies(
        self,
        patch: str,
        champ: str,
        role: Role,
        ally_role: Role,
        rows: Iterable[SynergyRow],
        champ_by_key: Mapping[int, str],
        at: str,
    ) -> None:
        self._write(
            "INSERT OR REPLACE INTO synergies VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            [
                (
                    patch,
                    self.rank,
                    champ,
                    role.value,
                    champ_by_key[r.ally_key],
                    ally_role.value,
                    r.games,
                    r.wins,
                    r.tier,
                    SOURCE,
                    at,
                )
                for r in rows
                if r.ally_key in champ_by_key
            ],
        )

    def log_fetch(
        self,
        tool: str,
        args: Mapping[str, Any],
        at: str,
        ok: bool,
        error: str = "",
        elapsed_ms: int = 0,
        format_fingerprint: str = "",
        patch_seen: str = "",
    ) -> None:
        self._write(
            "INSERT INTO fetch_log (source, tool, args, fetched_at, ok, error, elapsed_ms,"
            " format_fingerprint, patch_seen) VALUES (?,?,?,?,?,?,?,?,?)",
            [
                (
                    SOURCE,
                    tool,
                    json.dumps(args, sort_keys=True),
                    at,
                    int(ok),
                    error or None,
                    elapsed_ms,
                    format_fingerprint or None,
                    patch_seen or None,
                )
            ],
        )

    # ------------------------------------------------------------ reads

    def patches(self) -> list[str]:
        """Every patch with data, oldest first."""
        found = {
            row[0]
            for table in ("lane_stats", "matchups")
            for row in self._read(f"SELECT DISTINCT patch FROM {table}")
        }
        return sorted(found, key=_version_key)

    def opgg_patch(self) -> str | None:
        """OP.GG's current patch: the newest one a matchup guide reported."""
        rows = self._read(
            "SELECT DISTINCT patch_seen FROM fetch_log WHERE ok=1 AND patch_seen IS NOT NULL"
        )
        patches = [r[0] for r in rows]
        return max(patches, key=_version_key) if patches else None

    def lane_fetched_at(self) -> datetime | None:
        """When lane meta (role rates) was last stored."""
        rows = self._read("SELECT MAX(fetched_at) FROM lane_stats WHERE pick_rate IS NOT NULL")
        return _time(rows[0][0]) if rows and rows[0][0] else None

    def guide_fetched_at(self, role: Role, champ: str, opp: str) -> datetime | None:
        rows = self._read(
            "SELECT MAX(fetched_at) FROM matchup_labels WHERE role=? AND "
            "champ_id=? AND opp_champ_id=?",
            (role.value, champ, opp),
        )
        return _time(rows[0][0]) if rows and rows[0][0] else None

    def synergy_fetched_at(self, champ: str, role: Role, ally_role: Role) -> datetime | None:
        rows = self._read(
            "SELECT MAX(fetched_at) FROM synergies WHERE champ_id=? AND role=? AND ally_role=?",
            (champ, role.value, ally_role.value),
        )
        return _time(rows[0][0]) if rows and rows[0][0] else None

    def role_rates(self, patch: str) -> dict[str, dict[Role, float]]:
        """champ_id -> {role: share of its games}, from lane meta for this patch."""
        rates: dict[str, dict[Role, float]] = {}
        for role, champ, rate in self._read(
            "SELECT role, champ_id, role_rate FROM lane_stats WHERE patch=? AND rank_filter=? "
            "AND role_rate IS NOT NULL",
            (patch, self.rank),
        ):
            rates.setdefault(champ, {})[Role(role)] = float(rate)
        return rates

    def lane(self, patch: str, role: Role, champ: str) -> Counts | None:
        rows = self._read(
            "SELECT games, wins FROM lane_stats WHERE patch=? AND rank_filter=? "
            "AND role=? AND champ_id=?",
            (patch, self.rank, role.value, champ),
        )
        return Counts(rows[0][0], rows[0][1]) if rows else None

    def lane_counts(self, patch: str) -> dict[tuple[str, Role], tuple[int, int]]:
        """(champ, role) -> (games, wins) from OP.GG's lane stats, for the cross-check."""
        rows = self._read(
            "SELECT champ_id, role, games, wins FROM lane_stats WHERE patch=? AND rank_filter=?",
            (patch, self.rank),
        )
        return {(c, Role(r)): (int(g), int(w)) for c, r, g, w in rows}

    def tier(self, patch: str, role: Role, champ: str) -> int | None:
        """OP.GG's tier for this champion in this role (1 = strongest ... 5)."""
        rows = self._read(
            "SELECT tier FROM lane_stats WHERE patch=? AND rank_filter=? AND role=? AND champ_id=?",
            (patch, self.rank, role.value, champ),
        )
        return int(rows[0][0]) if rows and rows[0][0] is not None else None

    def matchup(self, patch: str, role: Role, champ: str, opp: str) -> Counts | None:
        """From champ's side. Falls back to the opponent's table, flipped."""
        query = (
            "SELECT games, wins FROM matchups WHERE patch=? AND rank_filter=? AND role=? "
            "AND champ_id=? AND opp_champ_id=?"
        )
        rows = self._read(query, (patch, self.rank, role.value, champ, opp))
        if rows:
            return Counts(rows[0][0], rows[0][1])
        rows = self._read(query, (patch, self.rank, role.value, opp, champ))
        return Counts(rows[0][0], rows[0][0] - rows[0][1]) if rows else None

    def labels(self, patch: str, role: Role, champ: str, opp: str) -> Labels | None:
        """From champ's side; the opponent's labels flipped if only those exist."""
        query = (
            "SELECT lane_advantage, solo_kill_advantage, play_style, tip FROM "
            "matchup_labels WHERE patch=? AND role=? AND champ_id=? AND opp_champ_id=?"
        )
        rows = self._read(query, (patch, role.value, champ, opp))
        if rows:
            return Labels(*(v or "" for v in rows[0]))
        rows = self._read(query, (patch, role.value, opp, champ))
        if not rows:
            return None
        flip = {"us": "them", "them": "us"}
        lane, solo, style, _ = (v or "" for v in rows[0])
        return Labels(flip.get(lane, lane), flip.get(solo, solo), "", "")

    def game_length(self, patch: str, role: Role, champ: str) -> dict[int, float]:
        rows = self._read(
            "SELECT minute, win_rate FROM game_length WHERE patch=? AND "
            "rank_filter=? AND role=? AND champ_id=?",
            (patch, self.rank, role.value, champ),
        )
        return {int(m): float(r) for m, r in rows}

    def builds(
        self, patch: str, role: Role, champ: str, opp: str, kind: str
    ) -> list[tuple[tuple[int, ...], int, int]]:
        rows = self._read(
            "SELECT ids, games, wins FROM matchup_builds WHERE patch=? AND role=? "
            "AND champ_id=? AND opp_champ_id=? AND kind=? ORDER BY rank",
            (patch, role.value, champ, opp, kind),
        )
        return [(tuple(int(i) for i in ids.split("|") if i), g, w) for ids, g, w in rows]

    def synergy(self, patch: str, a: str, a_role: Role, b: str, b_role: Role) -> Counts | None:
        query = (
            "SELECT games, wins FROM synergies WHERE patch=? AND rank_filter=? AND "
            "champ_id=? AND role=? AND ally_champ_id=? AND ally_role=?"
        )
        for x, xr, y, yr in ((a, a_role, b, b_role), (b, b_role, a, a_role)):
            rows = self._read(query, (patch, self.rank, x, xr.value, y, yr.value))
            if rows:
                return Counts(rows[0][0], rows[0][1])
        return None

    # ------------------------------------------------------------ measured figures (M19)

    def add_game(self, game_hash: str, patch: str, players: Sequence[Any], at: str,
                 record: Mapping[str, Any] | None = None) -> bool:
        """One collected game's figures (and its backtest record), counted once (False if it
        was already counted)."""
        rows = [(patch, p.champ_id, p.role.value, metric, value, value * value)
                for p in players for metric, value in p.figures.items()]  # fmt: skip
        pairs = [(patch, p.champ_id, p.role.value, p.opp, metric, value, value * value)
                 for p in players if getattr(p, "opp", "")
                 for metric, value in p.figures.items() if metric in MATCHUP_METRICS]  # fmt: skip
        with self._lock, self._db:
            done = self._db.execute(
                "INSERT OR IGNORE INTO collected VALUES (?,?,?)", (game_hash, patch, at)
            )
            if done.rowcount == 0:
                return False
            self._db.executemany(
                "INSERT INTO measured VALUES (?,?,?,?,1,?,?) ON CONFLICT"
                "(patch, champ_id, role, metric) DO UPDATE SET n = n + 1, "
                "total = total + excluded.total, total_sq = total_sq + excluded.total_sq",
                rows,
            )
            self._db.executemany(
                "INSERT INTO measured_matchups VALUES (?,?,?,?,?,1,?,?) ON CONFLICT"
                "(patch, champ_id, role, opp_champ_id, metric) DO UPDATE SET n = n + 1, "
                "total = total + excluded.total, total_sq = total_sq + excluded.total_sq",
                pairs,
            )
            if record is not None:
                self._db.execute("INSERT OR IGNORE INTO games VALUES (?,?,?)",
                                 (game_hash, patch, json.dumps(record)))  # fmt: skip
        return True

    def games(self, patches: Sequence[str] | None = None, limit: int | None = None
              ) -> list[dict[str, Any]]:  # fmt: skip
        """Stored game records, the most recently stored first, for the backtest."""
        sql, args = "SELECT patch, record FROM games", ()
        if patches:
            sql += f" WHERE patch IN ({','.join('?' * len(patches))})"
            args = tuple(patches)
        sql += " ORDER BY rowid DESC" + (f" LIMIT {int(limit)}" if limit else "")
        return [{**json.loads(record), "patch": patch} for patch, record in self._read(sql, args)]

    def measured_matchups(
        self, patch: str, min_games: int = 1
    ) -> dict[tuple[str, Role, str], dict[str, tuple[int, float, float]]]:
        """(champ, role, opp) -> metric -> (games, mean, standard deviation), for matchups with
        at least `min_games` games."""
        out: dict[tuple[str, Role, str], dict[str, tuple[int, float, float]]] = {}
        for champ, role, opp, metric, n, total, total_sq in self._read(
            "SELECT champ_id, role, opp_champ_id, metric, n, total, total_sq FROM "
            "measured_matchups WHERE patch=? AND n>=?", (patch, min_games),
        ):  # fmt: skip
            mean = total / n
            spread = max(0.0, total_sq / n - mean * mean) ** 0.5
            out.setdefault((champ, Role(role), opp), {})[metric] = (int(n), mean, spread)
        return out

    def prune(self, keep: Sequence[str], seen_before: str) -> dict[str, int]:
        """Drop measured data for patches other than `keep` (the current and previous one), and
        the "already counted" marks older than `seen_before` (an ISO time: past the
        collector's look-back, those games can't come up again). Returns rows deleted."""
        if not keep:
            return {}
        marks = ",".join("?" * len(keep))
        done: dict[str, int] = {}
        with self._lock, self._db:
            for table in ("measured", "measured_matchups", "games"):
                cur = self._db.execute(f"DELETE FROM {table} WHERE patch NOT IN ({marks})",
                                       tuple(keep))  # fmt: skip
                done[table] = cur.rowcount
            cur = self._db.execute(f"DELETE FROM collected WHERE patch NOT IN ({marks}) "
                                   "AND collected_at < ?", (*keep, seen_before))  # fmt: skip
            done["collected"] = cur.rowcount
        return done

    def seen(self, game_hash: str) -> bool:
        return bool(self._read("SELECT 1 FROM collected WHERE game_hash=?", (game_hash,)))

    def collected_games(self, patch: str) -> int:
        rows = self._read("SELECT COUNT(*) FROM collected WHERE patch=?", (patch,))
        return int(rows[0][0]) if rows else 0

    def measured(self, patch: str) -> dict[tuple[str, Role], dict[str, tuple[int, float, float]]]:
        """(champ, role) -> metric -> (games, mean, standard deviation)."""
        out: dict[tuple[str, Role], dict[str, tuple[int, float, float]]] = {}
        for champ, role, metric, n, total, total_sq in self._read(
            "SELECT champ_id, role, metric, n, total, total_sq FROM measured WHERE patch=?",
            (patch,),
        ):
            mean = total / n
            spread = max(0.0, total_sq / n - mean * mean) ** 0.5
            out.setdefault((champ, Role(role)), {})[metric] = (int(n), mean, spread)
        return out

    def state(self, key: str) -> str | None:
        rows = self._read("SELECT value FROM collector_state WHERE key=?", (key,))
        return rows[0][0] if rows else None

    def set_state(self, key: str, value: str) -> None:
        self._write("INSERT OR REPLACE INTO collector_state VALUES (?,?)", [(key, value)])

    # ------------------------------------------------------------ plumbing

    def _write(self, sql: str, rows: list[tuple[Any, ...]]) -> None:
        if not rows:
            return
        with self._lock, self._db:
            self._db.executemany(sql, rows)

    def _read(self, sql: str, args: tuple[Any, ...] = ()) -> list[tuple[Any, ...]]:
        with self._lock:
            return self._db.execute(sql, args).fetchall()


def _version_key(version: str) -> tuple[int, ...]:
    return tuple(int(p) for p in version.split(".") if p.isdigit())


def _time(text: str) -> datetime | None:
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None
