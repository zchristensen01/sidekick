"""Stats math: expected matchup result, shrinkage, previous-patch blending, display strings.

Every formula and default is in docs/STATS.md. The math is pure functions, tested with synthetic
numbers; `game_stats` reads the stats database once per report and returns plain values.
"""

import math
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from scout.data.patch import display_patch, previous_patch, short_patch
from scout.data.stats_db import Counts, Labels, StatsDb
from scout.model.game import GameState
from scout.model.roles import Role

LATE_MINUTES = (35, 40)  # OP.GG's game-length buckets: 0 (under 25), 25, 30, 35, 40 (40+)
EARLY_MINUTE = 0
SCALING_MEANINGFUL = 3.0  # points; smaller scaling-index gaps are noise (STATS.md)


@dataclass(frozen=True)
class StatsSettings:
    prior_games: int = 1000
    synergy_prior_games: int = 500
    previous_patch_weight: float = 0.5
    min_games_display: int = 500


# ---------------------------------------------------------------- the math (STATS.md rules 1-3)


def logit(p: float) -> float:
    p = min(max(p, 1e-6), 1 - 1e-6)
    return math.log(p / (1 - p))


def expit(x: float) -> float:
    return 1 / (1 + math.exp(-x))


def expected_matchup(p_me: float, p_opp: float) -> float:
    """What this matchup should be from the two base win rates alone (Elo-style)."""
    return expit(logit(p_me) - logit(p_opp))


def expected_duo(p_a: float, p_b: float) -> float:
    """What two allies should win together from their base win rates alone."""
    return expit(logit(p_a) + logit(p_b))


def shrink(wins: float, games: float, expected: float, prior_games: float) -> float:
    """Few games stay near the expected result; many move toward the observed rate."""
    return (wins + prior_games * expected) / (games + prior_games)


@dataclass(frozen=True)
class Blend:
    counts: Counts
    previous_share: float  # how much of the games came from the previous patch


def blend(this: Counts | None, previous: Counts | None, weight: float) -> Blend | None:
    """This patch plus `weight` x the previous patch (weight 0 for a changed champion)."""
    prev_games = weight * previous.games if previous else 0.0
    games = (this.games if this else 0.0) + prev_games
    if games <= 0:
        return None
    wins = (this.wins if this else 0.0) + (weight * previous.wins if previous else 0.0)
    return Blend(Counts(games, wins), prev_games / games)


def scaling_index(rates: Mapping[int, float]) -> float | None:
    """Points: win rate in 35+ minute games minus under 25 minutes. Coarse (no game counts)."""
    late = [rates[m] for m in LATE_MINUTES if m in rates]
    if not late or EARLY_MINUTE not in rates:
        return None
    return round((sum(late) / len(late) - rates[EARLY_MINUTE]) * 100, 1)


def scaling_level(index: float) -> int:
    """OP.GG's game-length swing on the 0-3 `scaling` scale (docs/STATS.md, Scaling): +6 points
    or more = 3 (keeps climbing), -3 to +6 = 2 (scales normally), -3 to -6 = 1 (early or mid
    game peak), -6 or less = 0 (falls off). 3 points is the noise level (SCALING_MEANINGFUL)."""
    m = SCALING_MEANINGFUL
    if index >= 2 * m:
        return 3
    if index > -m:
        return 2
    if index > -2 * m:
        return 1
    return 0


def length_rates(rates: Mapping[int, float]) -> tuple[float, float] | None:
    """(win rate in games under 25 minutes, in 35+ minute games), as scaling_index sees them."""
    late = [rates[m] for m in LATE_MINUTES if m in rates]
    if not late or EARLY_MINUTE not in rates:
        return None
    return rates[EARLY_MINUTE], sum(late) / len(late)


def length_note(short: float, long: float) -> str:
    """'OP.GG: 45% of games under 25 minutes, 56% of games past 35' (copied, never reformatted)."""
    return f"OP.GG: {percent(short)} of games under 25 minutes, {percent(long)} of games past 35"


def percent(rate: float) -> str:
    return f"{round(rate * 100)}%"


def display(rate: float, games: float, patch_label: str = "", mostly_previous: bool = False) -> str:
    """'47% over 4,140 games', plus '(26.18)' when it isn't the current patch's data
    (STATS.md rule 4: the writer copies these strings, never formats numbers itself)."""
    text = f"{percent(rate)} over {round(games):,} games"
    if patch_label:
        text += f" ({patch_label})"
    elif mostly_previous:
        text += " (mostly last patch's data)"
    return text


def patch_pair(available: list[str], current: str) -> tuple[str | None, str | None]:
    """(this patch, previous patch) among the patches with data. If OP.GG is ahead of our
    static data, its newest patch counts as this one. The previous patch is only the one right
    before (after a break, older data isn't blended in as "last patch")."""
    key = _version_key
    newer = [p for p in available if key(p) >= key(current)]
    this = current if current in available else (max(newer, key=key) if newer else None)
    before = previous_patch(this or current)
    return this, (before if before in available else None)


# ---------------------------------------------------------------- one game's stats


@dataclass(frozen=True)
class MatchupStat:
    """One champion against its lane opponent, from that champion's side."""

    role: Role
    champ: str
    opp: str
    games: int  # after blending
    rate: float  # shrunk toward the expected result
    raw_rate: float
    expected: float
    delta: float  # rate - expected: how much this opponent changes things
    shown: bool  # enough games to show the number (stats.min_games_display)
    display: str
    patch_label: str  # "" when it's this patch's data
    labels: Labels | None
    mostly_previous: bool = False  # more than half the games are from the previous patch


@dataclass(frozen=True)
class DuoStat:
    side: str  # us | them
    a: str
    b: str
    games: int
    rate: float
    expected: float
    delta: float
    shown: bool
    display: str


@dataclass(frozen=True)
class GameStats:
    matchups: dict[Role, MatchupStat] = field(default_factory=dict)  # ally role -> ally's side
    duos: dict[str, DuoStat] = field(default_factory=dict)  # bot lane duo per side
    builds: dict[Role, tuple[str, ...]] = field(default_factory=dict)  # enemy role -> items
    scaling: dict[str, float] = field(default_factory=dict)  # champ_id -> scaling index
    notice: str = ""  # one line when stats are missing or stale
    alternatives: dict[str, MatchupStat] = field(default_factory=dict)  # opp -> my matchup
    lengths: dict[str, tuple[float, float]] = field(default_factory=dict)  # champ -> short, long
    role_shares: dict[str, dict[Role, float]] = field(default_factory=dict)  # OP.GG, per pick
    measured: dict[tuple[str, Role], Any] = field(default_factory=dict)  # M19: Figures per pick

    @property
    def any(self) -> bool:
        return bool(self.matchups or self.duos)


NO_STATS = GameStats()


class Lookup:
    """Blended, shrunk numbers from the database for one Data Dragon version: the patch pair,
    base win rates, matchups. Shared by reports (`game_stats`) and pick suggestions."""

    def __init__(self, db: StatsDb, version: str, settings: StatsSettings,
                 changed: frozenset[str] = frozenset()) -> None:  # fmt: skip
        self.db, self.settings, self.changed = db, settings, changed
        current = short_patch(version)
        self.this, self.previous = patch_pair(db.patches(), current)
        self.label = "" if self.this == current else display_patch(
            self.this or self.previous or current)  # fmt: skip

    @property
    def available(self) -> bool:
        return self.this is not None or self.previous is not None

    def blended(self, get, champs: tuple[str, ...]) -> Blend | None:  # noqa: ANN001
        weight = 0.0 if set(champs) & self.changed else self.settings.previous_patch_weight
        this, prev = self.this, self.previous
        return blend(get(this) if this else None, get(prev) if prev else None, weight)

    def base(self, role: Role, champ: str) -> float:
        found = self.blended(lambda p: self.db.lane(p, role, champ), (champ,))
        return found.counts.rate if found else 0.5

    def base_counts(self, role: Role, champ: str) -> Blend | None:
        return self.blended(lambda p: self.db.lane(p, role, champ), (champ,))

    def matchup(self, role: Role, a: str, e: str) -> "MatchupStat | None":
        found = self.blended(lambda p: self.db.matchup(p, role, a, e), (a, e))
        if found is None:
            return None
        expected = expected_matchup(self.base(role, a), self.base(role, e))
        n, w = found.counts.games, found.counts.wins
        rate = shrink(w, n, expected, self.settings.prior_games)
        labels = next((x for p in (self.this, self.previous) if p
                       for x in [self.db.labels(p, role, a, e)] if x), None)  # fmt: skip
        return MatchupStat(
            role=role, champ=a, opp=e, games=round(n), rate=rate, raw_rate=w / n,
            expected=expected, delta=rate - expected,
            shown=n >= self.settings.min_games_display,
            display=display(rate, n, self.label, found.previous_share > 0.5),
            patch_label=self.label, labels=labels, mostly_previous=found.previous_share > 0.5,
        )  # fmt: skip

    def duo(self, a: str, a_role: Role, b: str, b_role: Role, side: str = "us") -> DuoStat | None:
        """Two allies together (OP.GG synergies, either direction), shrunk toward what their
        base win rates predict (docs/STATS.md rule 2)."""
        found = self.blended(lambda p: self.db.synergy(p, a, a_role, b, b_role), (a, b))
        if found is None:
            return None
        expected = expected_duo(self.base(a_role, a), self.base(b_role, b))
        n, w = found.counts.games, found.counts.wins
        rate = shrink(w, n, expected, self.settings.synergy_prior_games)
        return DuoStat(side, a, b, round(n), rate, expected, rate - expected,
                       n >= self.settings.min_games_display,
                       display(rate, n, self.label, found.previous_share > 0.5))  # fmt: skip

    def most_played(self, role: Role, limit: int = 10) -> list[str]:
        """The role's most-played champions (lane stats), most games first."""
        patch = self.this or self.previous
        if patch is None:
            return []
        rates = self.db.role_rates(patch)
        games = {c: (self.db.lane(patch, role, c) or Counts(0, 0)).games
                 for c, r in rates.items() if role in r}  # fmt: skip
        return sorted(games, key=lambda c: -games[c])[:limit]


def game_stats(
    db: StatsDb,
    game: GameState,
    settings: StatsSettings,
    changed: frozenset[str] = frozenset(),
    items: Mapping[int, str] | None = None,
    notice: str = "",
    cache: dict[str, Any] | None = None,
) -> GameStats:
    """Matchup numbers for every lane, the bot duos, the enemy's usual build into me.
    `cache`: a dict kept across calls (the backtest) so per-patch tables load once."""
    look = Lookup(db, game.ddragon_version, settings, changed)

    def cached(key: str, load: Any) -> Any:
        if cache is None:
            return load()
        if key not in cache:
            cache[key] = load()
        return cache[key]

    if not look.available:  # no OP.GG numbers yet: Riot's measured figures still count
        return GameStats(notice=notice, measured=_measured(db, game, {}, cached))
    this, previous, label = look.this, look.previous, look.label
    blended, base, pair = look.blended, look.base, look.matchup

    matchups: dict[Role, MatchupStat] = {}
    for role, mine in game.ally.items():
        theirs = game.enemy.get(role)
        stat = pair(role, mine.champ_id, theirs.champ_id) if theirs else None
        if stat is not None:
            matchups[role] = stat

    # Other champions that might be my lane opponent (unsure role guess): my own matchup
    # table already has them, so no extra fetch.
    alternatives: dict[str, MatchupStat] = {}
    mine = game.ally.get(game.my_role)
    guessed = game.enemy.get(game.my_role)
    for champ, _ in game.enemy_role_odds.get(game.my_role, []) if mine else []:
        if guessed is None or champ != guessed.champ_id:
            stat = pair(game.my_role, mine.champ_id, champ)
            if stat is not None:
                alternatives[champ] = stat

    duos: dict[str, DuoStat] = {}
    for side, team in (("us", game.ally), ("them", game.enemy)):
        adc, sup = team.get(Role.BOT), team.get(Role.SUPPORT)
        if adc is None or sup is None:
            continue
        a, b = adc.champ_id, sup.champ_id
        found = blended(lambda p, a=a, b=b: db.synergy(p, a, Role.BOT, b, Role.SUPPORT), (a, b))
        if found is None:
            continue
        expected = expected_duo(base(Role.BOT, a), base(Role.SUPPORT, b))
        n, w = found.counts.games, found.counts.wins
        rate = shrink(w, n, expected, settings.synergy_prior_games)
        duos[side] = DuoStat(
            side,
            a,
            b,
            round(n),
            rate,
            expected,
            rate - expected,
            n >= settings.min_games_display,
            display(rate, n, label, found.previous_share > 0.5),
        )

    builds: dict[Role, tuple[str, ...]] = {}  # my opponent's most common build into me
    me, opp = game.ally.get(game.my_role), game.enemy.get(game.my_role)
    for p in (this, previous) if me and opp and items else ():
        core = db.builds(p, game.my_role, opp.champ_id, me.champ_id, "core") if p else []
        names = tuple(items[i] for i in core[0][0] if i in items) if core else ()
        if names:
            builds[game.my_role] = names
            break

    scaling: dict[str, float] = {}
    lengths: dict[str, tuple[float, float]] = {}
    for team in (game.ally, game.enemy):
        for role, pick in team.items():
            for p in (this, previous):
                rates = db.game_length(p, role, pick.champ_id) if p else {}
                index, pair = scaling_index(rates), length_rates(rates)
                if index is not None and pair is not None:
                    scaling[pick.champ_id], lengths[pick.champ_id] = index, pair
                    break

    first = this or previous
    shares = cached(f"shares:{first}", lambda: db.role_rates(first)) if first else {}
    picked = {p.champ_id for p in (*game.ally.values(), *game.enemy.values())}
    role_shares = {c: dict(shares[c]) for c in picked if c in shares}

    return GameStats(matchups, duos, builds, scaling, notice, alternatives, lengths, role_shares,
                     _measured(db, game, shares, cached))  # fmt: skip


def _measured(db: StatsDb, game: GameState, shares: Mapping[str, Mapping[Role, float]],
              cached: Any) -> dict[tuple[str, Role], Any]:  # fmt: skip
    """M19: figures measured from Riot's match data, this patch first, else the one right
    before. By Riot's own patch (the game's Data Dragon version, what the collector stores
    games under), not OP.GG's, so they count even while OP.GG still serves last patch."""
    import dataclasses as dc

    from scout.analysis.measured import changes, figures_for  # measured.py imports this module

    now = short_patch(game.ddragon_version)
    tables = [(p, cached(f"measured:{p}", lambda p=p: db.measured(p)))
              for p in (now, previous_patch(now))]  # fmt: skip
    measured: dict[tuple[str, Role], Any] = {}
    for team in (game.ally, game.enemy):
        for role, pick in team.items():
            for i, (patch, table) in enumerate(tables):
                found = figures_for(table, pick.champ_id, role, patch, shares)
                if found is not None:
                    if i == 0:  # this patch: what moved since the last one
                        moved = changes(table, tables[1][1], tables[1][0], (pick.champ_id, role))
                        found = dc.replace(found, changes=tuple(c.text() for c in moved))
                    measured[(pick.champ_id, role)] = found
                    break
    return measured


def lane_advantage(stat: MatchupStat | None) -> str | None:
    """'us' / 'them' / 'even' from OP.GG's lane label, only when the sample is big enough."""
    if stat is None or not stat.shown or stat.labels is None:
        return None
    return stat.labels.lane_advantage or None


def _version_key(version: str) -> tuple[int, ...]:
    return tuple(int(p) for p in version.split(".") if p.isdigit())
