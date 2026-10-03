"""Reading the measured figures (M19): coverage, the OP.GG cross-check, display strings, and the
one written rule that turns figures into the 0-3 values the lane model uses.

The figures themselves are counts (scout/data/measure.py). The rule below is the only judgment:
within each role, among the champions really played there (role pools) with enough games, a
champion's rank on a figure sets its level by quarter (top quarter = 3 ... bottom quarter = 0).
It's checked and tuned against real games in M20 (backtesting); docs/DECISIONS.md #86.
"""

from collections.abc import Mapping
from dataclasses import dataclass

from scout.analysis import role_pool
from scout.model.roles import Role

MIN_GAMES = 50  # a champion-role needs this many measured games before its figures are used
CLEAR_WORDS = {3: "among the fastest (top quarter)", 2: "faster than most",
               1: "slower than most", 0: "among the slowest (bottom quarter)"}  # fmt: skip
CHANGE_Z = 3.0  # a figure "changed since last patch" only past 3 standard errors (few false alarms)
# figure -> (words, kind): how a change is said
CHANGES = {"level4_s": ("reaches level 4", "time"), "level3_s": ("reaches level 3", "time"),
           "first_item_s": ("finishes their first item", "time"),
           "gold_diff_10": ("gold vs lane opponent at 10", "gold"),
           "push_3_10": ("time on the enemy half, minutes 3-10", "share"),
           "win": ("win rate", "share")}  # fmt: skip
MIN_FIELD = 8  # and its role needs this many such champions before levels are ranked
# value used by the lane model <- measured figure (higher figure = higher level, unless noted)
LEVELS = {"early": "gold_diff_10", "waveclear": "push_3_10", "roam": "roam_takedowns_14"}
CLEAR = "level4_s"  # junglers: lower is faster

Table = Mapping[tuple[str, Role], Mapping[str, tuple[int, float, float]]]


@dataclass(frozen=True)
class Figures:
    """One champion in one role, as measured."""

    games: int
    means: dict[str, float]
    levels: dict[str, int]  # early, waveclear, roam (0-3); jungle clear as "clear"
    patch: str
    changes: tuple[str, ...] = ()  # what moved since last patch, beyond normal variation

    def lines(self) -> list[str]:
        """Plain display strings (the writer copies them; nothing to reformat)."""
        m, out = self.means, []
        if "gold_diff_10" in m and "gold_diff_15" in m:
            out.append(f"gold vs lane opponent: {m['gold_diff_10']:+,.0f} at 10 minutes, "
                       f"{m['gold_diff_15']:+,.0f} at 15")  # fmt: skip
        if "cs_diff_10" in m:
            out.append(f"CS vs lane opponent at 10: {m['cs_diff_10']:+.1f}")
        if "push_3_10" in m:
            out.append(f"on the enemy's half of the map {round(m['push_3_10'] * 100)}% of "
                       "minutes 3-10")  # fmt: skip
        for level in (3, 4):
            key = f"level{level}_s"
            if key in m:
                out.append(f"level {level} at {_clock(m[key])}")
        if "clear" in self.levels:  # junglers: level 4 is a full clear, ranked among junglers
            out.append(f"jungle clear: {CLEAR_WORDS[self.levels['clear']]} (time to level 4, "
                       f"among junglers with {MIN_GAMES}+ games)")  # fmt: skip
        if "first_item_s" in m:
            out.append(f"first finished item at {_clock(m['first_item_s'])}")
        if "kp_14" in m:
            out.append(f"in {round(m['kp_14'] * 100)}% of their team's kills before 14:00")
        if "roam_takedowns_14" in m:
            out.append(f"{m['roam_takedowns_14']:.1f} takedowns outside their lane before 14:00")
        if "win" in m:
            out.append(f"won {round(m['win'] * 100)}%")
        return out

    def source(self) -> str:
        return f"Riot match data, Emerald+, patch {self.patch}, {self.games:,} games"


def figures_for(table: Table, champ: str, role: Role, patch: str,
                shares: Mapping[str, Mapping[Role, float]]) -> Figures | None:  # fmt: skip
    """The champion's measured figures in this role, with levels, if there are enough games."""
    found = table.get((champ, role))
    if not found or found.get("win", (0, 0.0, 0.0))[0] < MIN_GAMES:
        return None
    means = {metric: mean for metric, (_, mean, _) in found.items()}
    return Figures(found["win"][0], means, _levels(table, champ, role, shares), patch)


@dataclass(frozen=True)
class Change:
    champ: str
    role: Role
    metric: str
    before: float
    after: float
    patch: str  # the previous patch

    def text(self) -> str:
        words, kind = CHANGES[self.metric]
        d = self.after - self.before
        if kind == "time":
            way = "sooner" if d < 0 else "later"
            return (f"{words} at {_clock(self.after)}, {abs(d):.0f} seconds {way} than patch "
                    f"{self.patch} ({_clock(self.before)})")  # fmt: skip
        if kind == "gold":
            return f"{words}: {self.after:+,.0f}, was {self.before:+,.0f} on patch {self.patch}"
        return (f"{words}: {round(self.after * 100)}%, was {round(self.before * 100)}% on "
                f"patch {self.patch}")  # fmt: skip


def changes(this: Table, previous: Table, previous_patch: str,
            only: tuple[str, Role] | None = None) -> list[Change]:  # fmt: skip
    """Figures that moved between two patches by more than normal game-to-game variation:
    |difference| > CHANGE_Z standard errors, with MIN_GAMES+ games in both. Biggest first."""
    found = []
    keys = [only] if only else list(this)
    for key in keys:
        now, before = this.get(key), previous.get(key)
        if not now or not before:
            continue
        if min(now.get("win", (0,))[0], before.get("win", (0,))[0]) < MIN_GAMES:
            continue
        for metric in CHANGES:
            if metric not in now or metric not in before:
                continue
            (na, ma, sa), (nb, mb, sb) = now[metric], before[metric]
            error = (sa * sa / na + sb * sb / nb) ** 0.5 if na and nb else 0.0
            if error > 0 and abs(ma - mb) > CHANGE_Z * error:
                found.append(((abs(ma - mb) / error), Change(key[0], key[1], metric, mb, ma,
                                                             previous_patch)))  # fmt: skip
    return [c for _, c in sorted(found, key=lambda x: -x[0])]


def _levels(table: Table, champ: str, role: Role,
            shares: Mapping[str, Mapping[Role, float]]) -> dict[str, int]:  # fmt: skip
    field = {c: m for (c, r), m in table.items() if r is role
             and m.get("win", (0, 0.0, 0.0))[0] >= MIN_GAMES
             and not role_pool.is_off_role(c, role, shares)}  # fmt: skip
    levels: dict[str, int] = {}
    if len(field) < MIN_FIELD or champ not in field:
        return levels
    clear = (("clear", CLEAR),) if role is Role.JUNGLE else ()  # a clear is a jungler's
    for name, metric in (*LEVELS.items(), *clear):
        values = sorted(m[metric][1] for m in field.values() if metric in m)
        mine = field[champ].get(metric)
        if mine is None or len(values) < MIN_FIELD:
            continue
        below = sum(1 for v in values if v < mine[1]) / len(values)
        rank = 1 - below if metric == CLEAR else below  # faster clears rank higher
        levels[name] = 3 if rank >= 0.75 else 2 if rank >= 0.5 else 1 if rank >= 0.25 else 0
    return levels


def coverage(table: Table, shares: Mapping[str, Mapping[Role, float]]
             ) -> tuple[int, int, list[str]]:  # fmt: skip
    """(champion-roles really played that have enough games, all really played, the missing)."""
    wanted = [(c, r) for c in shares for r in role_pool.roles_played(c, shares)]
    have = [(c, r) for c, r in wanted if table.get((c, r), {}).get("win", (0,))[0] >= MIN_GAMES]
    missing = sorted(f"{c} {r.value}" for c, r in set(wanted) - set(have))
    return len(have), len(wanted), missing


def cross_check(table: Table, opgg: Mapping[tuple[str, Role], tuple[int, int]]
                ) -> list[tuple[str, Role, float, float, int]]:  # fmt: skip
    """(champ, role, our win rate, OP.GG's, our games) for pairs both have, biggest gap first.
    Different samples and ranks make a few points normal; a big gap means something's off."""
    rows = []
    for (champ, role), metrics in table.items():
        n, ours, _ = metrics.get("win", (0, 0.0, 0.0))
        theirs = opgg.get((champ, role))
        if n >= MIN_GAMES and theirs and theirs[0]:
            rows.append((champ, role, ours, theirs[1] / theirs[0], n))
    return sorted(rows, key=lambda r: -abs(r[2] - r[3]))


def _clock(seconds: float) -> str:
    return f"{int(seconds // 60)}:{int(seconds % 60):02d}"
