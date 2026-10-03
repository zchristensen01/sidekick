"""Pick suggestions while drafting (M9b): 2-3 options for my assigned role, with reasons.

docs/COUNTERPICK.md (Pick suggestions). Same data and bands as the counter-pick verdict, used
before the pick: against my lane opponent once they've locked (by the role guess), or by
blind safety before that. Candidates: my champ pool for the role (pool.yaml, each champion
rated 1-5 for comfort; scout/pool.py), else my most-played champions there (champion mastery
bucketed by role rates), else champions that are strong this patch and easy to play,
labelled "outside your pool". Options, never "pick X" (docs/POLICY.md).
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

from scout.analysis.stats import Lookup, display, shrink
from scout.analysis.team import FRONTLINE_AT
from scout.counterpick import DEFAULT_BANDS, Bands, outlook_from_rate
from scout.data.store import Knowledge, Row, traits_for
from scout.model.game import GameState
from scout.model.roles import Role

# A preference, not a League fact: per comfort star of difference, how many points of win rate
# a more comfortable champion may trail by and still rank first (equal stars: 1 point).
COMFORT_MARGIN = 1.0
MAX_OPTIONS = 3
MIN_OPTIONS = 2  # POLICY.md: options with reasons, never a single "pick this"
MASTERY_ROLE_SHARE = 0.25  # a mastery champion counts for roles it plays at least this often
MASTERY_PER_ROLE = 5
COMMON_OPPONENTS = 10  # blind safety: the role's most-played champions
MIN_CHECKED = 5  # matchups with numbers needed before calling a blind pick safe or risky
HARD_COUNTER_COST = 10.0  # blind score: points off per 100% of common opponents that hard-counter
META_TIER = 2  # OP.GG tier 1-2 = strong this patch
META_DIFFICULTY = 1  # CommunityDragon difficulty rating 1 = easy
WORDS = {"favorable": "favored", "even": "even", "soft_counter": "slight disadvantage",
         "hard_counter": "hard matchup"}  # fmt: skip
SYNERGY_NOTE_AT = 0.01  # a pairing is named when it moves the shrunk rate by 1 point or more
AIRBORNE = frozenset({"knockup", "knockback", "knock_aside", "pull"})  # the wiki's Airborne
MAX_REASONS = 2


@dataclass(frozen=True)
class Candidate:
    champ: str
    source: str  # pool | mastery | meta
    comfort: int  # 0 = most comfortable (order in the pool)
    stars: int = 0  # my 1-5 comfort rating from pool.yaml; 0 = not rated


@dataclass(frozen=True)
class Option:
    candidate: Candidate
    name: str
    outlook: str  # favorable | even | soft_counter | hard_counter | unknown
    rate: float | None  # shrunk matchup rate (or blind score as a rate)
    display: str
    blind: tuple[int, int] | None = None  # (hard counters, common opponents checked)
    own: float | None = None  # the champion's own shrunk win rate in this role
    reason: str = ""
    synergy: float = 0.0  # M18: summed shrunk duo deltas with the locked allies (rate units)
    synergy_text: str = ""  # the best-supported pairing, named, with OP.GG's display string

    @property
    def score(self) -> float | None:
        """DraftGap-style: the lane (matchup, or blind safety) plus how much better or worse
        than expected the champion does with each locked ally."""
        if self.blind is None:
            return None if self.rate is None else self.rate + self.synergy
        if self.own is None:
            return None
        hard, checked = self.blind
        share = hard / checked if checked else 0.0
        return self.own - HARD_COUNTER_COST / 100 * share + self.synergy


@dataclass(frozen=True)
class Suggestions:
    role: Role
    opponent: str  # display name; "" when picking blind
    opponent_confidence: float
    options: tuple[Option, ...]
    note: str = ""


def parse_mastery(raw: object, by_key: Mapping[int, str]) -> list[tuple[str, int]]:
    """(champ_id, points) from the client's champion-mastery answer; unknown keys skipped."""
    found = []
    for entry in raw if isinstance(raw, list) else []:
        if isinstance(entry, dict) and entry.get("championId") in by_key:
            found.append((by_key[entry["championId"]], int(entry.get("championPoints") or 0)))
    return found


def mastery_by_role(
    mastery: Sequence[tuple[str, int]], rates: Mapping[str, Mapping[Role, float]]
) -> dict[Role, list[str]]:
    """Most-played champions per role: mastery points, bucketed by role rates."""
    by_role: dict[Role, list[str]] = {role: [] for role in Role}
    for champ, _ in sorted(mastery, key=lambda m: -m[1]):
        for role, share in rates.get(champ, {}).items():
            if share >= MASTERY_ROLE_SHARE and len(by_role[role]) < MASTERY_PER_ROLE:
                by_role[role].append(champ)
    return by_role


def candidates(
    role: Role,
    pool: Mapping[Role, Sequence[str] | Mapping[str, int]],
    mastery: Mapping[Role, Sequence[str]],
    look: Lookup | None,
    meta_rows: Sequence[Row],
    unavailable: set[str],
) -> list[Candidate]:
    """Pool first (best rated first); else mastery; else easy, strong-this-patch champions.
    A pool with one champion left is topped up from the next source, so there are options."""
    rated = _rated(pool.get(role, ()))
    found = [Candidate(c, "pool", i, stars) for i, (c, stars) in enumerate(rated)
             if c not in unavailable]  # fmt: skip
    if len(found) >= MIN_OPTIONS:
        return found
    seen = {c.champ for c in found}
    found += [Candidate(c, "mastery", i) for i, c in enumerate(mastery.get(role, ()))
              if c not in unavailable and c not in seen]  # fmt: skip
    if len(found) >= MIN_OPTIONS:
        return found
    if look is None or look.this is None and look.previous is None:
        return found
    easy = {r["champ_id"] for r in meta_rows if r.get("difficulty") == str(META_DIFFICULTY)}
    patch = look.this or look.previous
    strong = []
    for champ in look.most_played(role, limit=60):
        tier = look.db.tier(patch, role, champ) if patch else None
        if champ in easy and champ not in unavailable and tier is not None and tier <= META_TIER:
            strong.append(champ)
    seen = {c.champ for c in found}
    return found + [Candidate(c, "meta", i) for i, c in enumerate(strong[:MAX_OPTIONS])
                    if c not in seen]  # fmt: skip


def _rated(champs: Sequence[str] | Mapping[str, int]) -> list[tuple[str, int]]:
    """(champ, stars), best rated first; a plain list is unrated, in its own order."""
    if isinstance(champs, Mapping):
        return sorted(champs.items(), key=lambda item: -item[1])
    return [(c, 0) for c in champs]


def suggest(
    game: GameState,
    knowledge: Knowledge,
    cands: Sequence[Candidate],
    look: Lookup | None,
    bands: Bands = DEFAULT_BANDS,
) -> Suggestions:
    role = game.my_role
    opp = game.enemy.get(role)
    opp_name = knowledge.facts(opp.champ_id).name if opp else ""
    options = []
    for cand in cands:
        name = knowledge.facts(cand.champ).name
        reason = "; ".join(team_reasons(cand.champ, game, knowledge)[:MAX_REASONS])
        syn, syn_text = _synergy(look, role, cand.champ, game, knowledge)
        extra = {"reason": reason, "synergy": syn, "synergy_text": syn_text}
        if opp is not None:
            stat = look.matchup(role, cand.champ, opp.champ_id) if look else None
            if stat is not None and stat.shown:
                outlook = outlook_from_rate(stat.rate, bands)
                options.append(Option(cand, name, outlook, stat.rate, stat.display, **extra))
            else:
                options.append(Option(cand, name, "unknown", None, "", **extra))
            continue
        hard, checked, own, shown = _blind(look, role, cand.champ, bands)
        options.append(Option(cand, name, "unknown", None, shown, (hard, checked), own, **extra))
    ranked = _rank(options)[:MAX_OPTIONS]
    note = ""
    if not cands:
        note = (f"No champion pool for {role.value} and no stats to suggest from yet "
                "(the Champions button sets one).")  # fmt: skip
    elif cands[0].source == "mastery":
        note = f"No pool set for {role.value}: these are your most-played there."
    elif cands[0].source == "meta":
        note = f"No pool or history for {role.value}: strong, easy champions this patch."
    return Suggestions(role, opp_name, opp.role_confidence if opp else 1.0, tuple(ranked), note)


def _synergy(look: Lookup | None, role: Role, champ: str, game: GameState,
             knowledge: Knowledge) -> tuple[float, str]:  # fmt: skip
    """(summed shrunk duo deltas with each locked ally, the best-supported pairing named)."""
    if look is None:
        return 0.0, ""
    total, best = 0.0, None
    for ally_role, pick in game.ally.items():
        if ally_role is role:
            continue
        stat = look.duo(champ, role, pick.champ_id, ally_role)
        if stat is None:
            continue
        total += stat.delta
        if stat.shown and (best is None or abs(stat.delta) > abs(best[0].delta)):
            best = (stat, knowledge.facts(pick.champ_id).name)
    if best is None or abs(best[0].delta) < SYNERGY_NOTE_AT:
        return total, ""
    stat, ally = best
    word = "pairs well with" if stat.delta > 0 else "pairs poorly with"
    return total, f"{word} your {ally} (together {stat.display})"


def _blind(look: Lookup | None, role: Role, champ: str,
           bands: Bands) -> tuple[int, int, float | None]:  # fmt: skip
    """(hard counters, common opponents with numbers, own shrunk win rate)."""
    if look is None:
        return 0, 0, None
    hard = checked = 0
    common = [c for c in look.most_played(role, COMMON_OPPONENTS + 1) if c != champ]
    for opp in common[:COMMON_OPPONENTS]:
        stat = look.matchup(role, champ, opp)
        if stat is not None and stat.shown:
            checked += 1
            hard += outlook_from_rate(stat.rate, bands) == "hard_counter"
    base = look.base_counts(role, champ)
    own, shown = None, ""
    if base is not None:
        c = base.counts
        own = shrink(c.wins, c.games, 0.5, look.settings.prior_games)
        shown = display(own, c.games, look.label, base.previous_share > 0.5)  # games and patch
    return hard, checked, own, shown


def _rank(options: list[Option]) -> list[Option]:
    """By score, best first; unknowns last in comfort order. A more comfortable champion moves
    above one that scores higher by less than COMFORT_MARGIN points per star of difference."""
    known = sorted((o for o in options if o.score is not None), key=lambda o: -(o.score or 0))
    unknown = sorted((o for o in options if o.score is None), key=lambda o: o.candidate.comfort)
    changed = True
    while changed:  # a few adjacent swaps: lists are short
        changed = False
        for i in range(len(known) - 1):
            a, b = known[i], known[i + 1]
            more = b.candidate.stars - a.candidate.stars
            margin = COMFORT_MARGIN * max(1, more) / 100
            comfier = more > 0 or (more == 0 and b.candidate.comfort < a.candidate.comfort)
            if comfier and (a.score or 0) - (b.score or 0) < margin:
                known[i], known[i + 1] = b, a
                changed = True
    return known + unknown


# ---------------------------------------------------------------- team fit


def team_reasons(champ: str, game: GameState, knowledge: Knowledge) -> list[str]:
    """Team-fit reasons from sourced facts (M18), most specific first: knock-ups for an ally
    whose ultimate needs airborne targets (Riot's text, the wiki's mechanics), the damage mix
    (Riot's damage type), a frontliner or crowd control the team lacks (Riot's ratings: High).
    Drafted tags (anti_auto, engage) count only once the owner has reviewed them."""
    me = knowledge.facts(champ)
    mine = dict(me.ratings)
    traits = traits_for(knowledge.traits, champ, game.my_role)
    allies = [(r, p) for r, p in game.ally.items() if r is not game.my_role]
    reasons = []
    for r, p in allies:
        t = traits_for(knowledge.traits, p.champ_id, r)
        if t and "needs_airborne" in t.tags and me.mechanics & AIRBORNE:
            name = knowledge.facts(p.champ_id).name
            reasons.append(f"has knock-ups for your {name}'s ultimate, which needs airborne "
                           "targets")  # fmt: skip
    attackers = [knowledge.facts(p.champ_id).name for p in game.enemy.values()
                 if "marksman" in knowledge.facts(p.champ_id).classes]  # fmt: skip
    reviewed = traits is not None and (traits.reviewed or traits.source == "owner")
    if reviewed and "anti_auto" in traits.tags and len(attackers) >= 2:
        reasons.append(f"strong into their auto-attackers ({', '.join(attackers[:3])})")
    facts = [knowledge.facts(p.champ_id) for _, p in allies]
    if len(facts) >= 2:
        physical = sum(1 for a in facts if a.damage_type == "physical")
        magic = sum(1 for a in facts if a.damage_type == "magic")
        if me.damage_type == "magic" and physical >= magic + 2:
            reasons.append("adds magic damage to a mostly physical team")
        if me.damage_type == "physical" and magic >= physical + 2:
            reasons.append("adds physical damage to a mostly magic team")
        def best(rating: str) -> int:
            return max((dict(a.ratings).get(rating, 0) for a in facts), default=0)

        if mine.get("durability", 0) >= FRONTLINE_AT and best("durability") < FRONTLINE_AT:
            reasons.append("adds a frontliner (Riot rates its toughness high; your team has none)")
        if mine.get("cc", 0) >= 3 and best("cc") < 3:
            reasons.append("adds crowd control (Riot rates its control high; your team has none)")
        ally_traits = [traits_for(knowledge.traits, p.champ_id, r) for r, p in allies]
        engage = max((t.engage or 0 for t in ally_traits if t), default=0)
        if reviewed and (traits.engage or 0) >= 3 and engage < 3:
            reasons.append("adds the engage your team lacks")
    return reasons


# ---------------------------------------------------------------- text


def render(s: Suggestions, low_confidence: float = DEFAULT_BANDS.low_confidence) -> str:
    """The lines shown in the window and terminal before I lock."""
    if s.opponent:
        head = f"Pick options for {s.role.value} into {s.opponent}"
        if s.opponent_confidence < low_confidence:
            head += f" (a guess, {round(s.opponent_confidence * 100)}% sure they're your laner)"
    else:
        head = f"Pick options for {s.role.value} (their {s.role.value} isn't locked yet)"
    lines = [head, ""]
    for o in s.options:
        lines.append(f"- {option_text(o, s.opponent, s.role)}")
    if not s.options:
        lines.append("- Nothing to suggest yet.")
    if s.note:
        lines += ["", s.note]
    lines += ["", "Options, not orders: comfort matters as much as the numbers."]
    return "\n".join(lines) + "\n"


def option_text(o: Option, opponent: str, role: Role) -> str:
    if opponent:
        if o.outlook == "unknown":
            text = f"{o.name}: no reliable numbers into {opponent}"
        else:
            text = f"{o.name}: {WORDS[o.outlook]} into {opponent} ({o.display})"
    elif o.own is None:
        text = f"{o.name}: no numbers yet"
    else:
        hard, checked = o.blind or (0, 0)
        safety = "safe" if hard == 0 else "fairly safe" if hard <= checked / 5 else "risky"
        if checked >= MIN_CHECKED:
            text = (f"{o.name}: {safety} blind ({o.display}; hard-countered "
                    f"by {hard} of {checked} common {role.value} picks)")  # fmt: skip
        else:
            text = f"{o.name}: {o.display} (few matchups known yet)"
    if o.candidate.stars:
        text += f"; comfort {o.candidate.stars}/5"
    elif o.candidate.source == "pool" and o.candidate.comfort == 0:
        text += "; your main"
    elif o.candidate.source == "mastery":
        text += "; you play it a lot"
    elif o.candidate.source == "meta":
        text += "; outside your pool"
    if o.synergy_text:
        text += f"; {o.synergy_text}"
    if o.reason:
        text += f"; {o.reason}"
    return text


# ---------------------------------------------------------------- live helper for scout watch


@dataclass
class Picker:
    """What `scout watch` needs to suggest picks: knowledge, the pool, mastery, stats."""

    knowledge: Knowledge
    pool: Mapping[Role, Sequence[str] | Mapping[str, int]]  # pool.yaml: {role: {champ: stars}}
    meta_rows: Sequence[Row] = ()
    mastery: Sequence[tuple[str, int]] = ()  # (champ_id, points), from the client
    role_rates: Mapping[str, Mapping[Role, float]] = field(default_factory=dict)
    lookup: object = None  # callable returning a Lookup, or None (traits only)
    bands: Bands = DEFAULT_BANDS

    def suggest(self, game: GameState) -> Suggestions:
        look = self.lookup() if callable(self.lookup) else None
        taken = {p.champ_id for p in (*game.ally.values(), *game.enemy.values())}
        cands = candidates(game.my_role, self.pool, mastery_by_role(self.mastery, self.role_rates),
                           look, self.meta_rows, taken | set(game.bans))  # fmt: skip
        return suggest(game, self.knowledge, cands, look, self.bands)

    def champions_to_fetch(self, game: GameState) -> list[str]:
        """Candidates whose matchup tables a draft-time prefetch should get."""
        taken = {p.champ_id for p in (*game.ally.values(), *game.enemy.values())}
        look = self.lookup() if callable(self.lookup) else None
        cands = candidates(game.my_role, self.pool, mastery_by_role(self.mastery, self.role_rates),
                           look, self.meta_rows, taken | set(game.bans))  # fmt: skip
        return [c.champ for c in cands]
