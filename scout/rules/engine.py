"""Load league_rules.yaml, validate it, and evaluate it against a game's contexts.

The engine refuses to load a rules file with a duplicate id, an unknown scope, section, role,
op or placeholder, a path outside its scope's schema, a missing `tests` block, or `excludes`
pointing at an unknown id. Any comparison against a missing value is false, so missing
traits or stats can never make a rule fire. docs/RULES.md.
"""

import re
import string
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from scout.analysis.insights import Insights
from scout.model.roles import LANE_ROLES, Lane, Role, lane_of, roles_in
from scout.rules.context import PLACEHOLDERS, SCHEMA, Context, contexts

SECTIONS = frozenset({
    "gank_first", "lanes_in_trouble", "enemy_jungler", "start_objectives", "your_lane",
    "counterpick", "punish", "jungle", "map_threats", "roams", "your_job", "fights",
    "protect_or_engage", "watch_out", "dont_feed", "game_plan",
})  # fmt: skip
OPS = frozenset({"==", "!=", ">=", "<=", ">", "<", "in", "not_in", "has", "lacks", "has_any"})
CONFIDENCE_PRIORITY = {"high": 70, "med": 50}
ID_PATTERN = re.compile(r"[A-Z][A-Z0-9]*(-[A-Z0-9]+)+")
ALL_ROLES = frozenset(Role)


class RulesError(ValueError):
    """The rules file is invalid; the message lists every problem."""


@dataclass(frozen=True)
class Rule:
    id: str
    scope: str
    lanes: tuple[Lane, ...] | None
    audience: frozenset[Role] | None  # None = the scope's default
    their_lane: bool  # audience is the champion's lane opponents plus the jungler
    sections: Mapping[str, str]  # role value or "default" -> section key
    priority: int
    confidence: str
    when: tuple[tuple[str, str, Any], ...]
    say: str
    excludes: tuple[str, ...]
    tests: Mapping[str, Mapping[str, Any]]

    def section_for(self, role: Role) -> str:
        return self.sections.get(role.value, self.sections["default"])


@dataclass(frozen=True)
class Fired:
    rule: Rule
    lane: Lane | None
    subject: str
    audience: frozenset[Role]
    text: str
    team: str = ""  # pair scope: us | them

    @property
    def id(self) -> str:
        return self.rule.id


def load_rules(path: Path) -> list[Rule]:
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise RulesError(f"{path}: can't read it: {exc}") from None
    items = raw.get("rules") if isinstance(raw, dict) else None
    if not isinstance(items, list):
        raise RulesError(f"{path}: expected a top-level `rules:` list")
    rules, problems = [], []
    for n, item in enumerate(items, 1):
        rule, errors = _parse(item, n)
        problems += errors
        if rule:
            rules.append(rule)
    ids = [r.id for r in rules]
    problems += [f"duplicate id {i}" for i in sorted({i for i in ids if ids.count(i) > 1})]
    known = set(ids)
    for rule in rules:
        problems += [f"{rule.id}: excludes unknown id {x}" for x in rule.excludes if x not in known]
    if problems:
        raise RulesError(f"{path} has problems:\n  " + "\n  ".join(problems))
    return rules


def _parse(item: Any, n: int) -> tuple[Rule | None, list[str]]:
    if not isinstance(item, dict):
        return None, [f"rule #{n} isn't a mapping"]
    rid = str(item.get("id", f"#{n}"))
    problems: list[str] = []

    def bad(text: str) -> None:
        problems.append(f"{rid}: {text}")

    if not ID_PATTERN.fullmatch(rid):
        bad("id must be UPPER-KEBAB like LANE-WINNING")
    known_keys = {"id", "scope", "lanes", "audience", "section", "priority", "confidence",
                  "when", "say", "excludes", "tests"}  # fmt: skip
    for key in set(item) - known_keys:
        bad(f"unknown key {key!r}")
    scope = item.get("scope")
    if scope not in SCHEMA:
        bad(f"unknown scope {scope!r} (one of {', '.join(SCHEMA)})")
        return None, problems
    schema = SCHEMA[scope]

    lanes = None
    if "lanes" in item:
        if scope != "lane":
            bad("`lanes` is only for lane scope")
        try:
            lanes = tuple(Lane(x) for x in item["lanes"])
        except (ValueError, TypeError):
            bad(f"lanes must be a list of {', '.join(lane.value for lane in Lane)}")

    audience = None
    their_lane = item.get("audience") == "their_lane"
    if their_lane and scope not in ("champ", "ally"):
        bad("audience their_lane is only for champ and ally scope")
    if "audience" in item and not their_lane:
        raw = item["audience"]
        raw = [raw] if isinstance(raw, str) else raw
        try:
            audience = frozenset(Role(x) for x in raw)
        except (ValueError, TypeError):
            bad(f"audience must be roles from {', '.join(r.value for r in Role)}")

    section = item.get("section")
    sections = section if isinstance(section, dict) else {"default": section}
    if "default" not in sections:
        bad("a per-role section map needs a `default`")
    for key, value in sections.items():
        if key != "default" and key not in {r.value for r in Role}:
            bad(f"section map key {key!r} isn't a role")
        if value not in SECTIONS:
            bad(f"unknown section {value!r}")

    confidence = item.get("confidence", "med")
    if confidence not in CONFIDENCE_PRIORITY:
        bad("confidence must be high or med")
    priority = item.get("priority", CONFIDENCE_PRIORITY.get(confidence, 50))
    if not isinstance(priority, int) or not 0 <= priority <= 100:
        bad("priority must be a whole number 0-100")

    when = []
    for cond in item.get("when") or []:
        if not (isinstance(cond, list) and len(cond) == 3):
            bad(f"condition {cond!r} must be [path, op, value]")
            continue
        path, op, value = cond
        if path not in schema:
            bad(f"path {path!r} isn't available in {scope} scope (scout/rules/context.py)")
        if op not in OPS:
            bad(f"unknown op {op!r}")
        if op in ("in", "not_in", "has_any") and not isinstance(value, list):
            bad(f"`{op}` needs a list value in {cond!r}")
        when.append((path, op, value))
    if not when:
        bad("needs at least one `when` condition")

    say = item.get("say")
    if not isinstance(say, str) or not say.strip():
        bad("needs a `say` text")
        say = ""
    fields = {f for _, f, _, _ in string.Formatter().parse(say) if f}
    for name in sorted(fields - PLACEHOLDERS[scope]):
        bad(f"placeholder {{{name}}} isn't available in {scope} scope")

    excludes = tuple(item.get("excludes") or ())
    tests = item.get("tests")
    if not (isinstance(tests, dict) and isinstance(tests.get("fires"), dict)
            and isinstance(tests.get("not"), dict)):  # fmt: skip
        bad("needs a `tests` block with `fires` and `not` contexts")
        tests = {"fires": {}, "not": {}}
    for kind in ("fires", "not"):
        for path in tests.get(kind, {}):
            if path not in schema:
                bad(f"tests.{kind} path {path!r} isn't available in {scope} scope")

    rule = Rule(rid, scope, lanes, audience, their_lane, sections, priority, confidence,
                tuple(when), say.strip(), excludes, tests)  # fmt: skip
    return (rule if not problems else None), problems


def matches(rule: Rule, values: Mapping[str, Any]) -> bool:
    return all(_check(values.get(path), op, value) for path, op, value in rule.when)


def _check(actual: Any, op: str, expected: Any) -> bool:
    if actual is None:
        return False  # missing data never makes a rule fire, not even for != or lacks
    try:
        if op == "==":
            return actual == expected
        if op == "!=":
            return actual != expected
        if op == ">=":
            return actual >= expected
        if op == "<=":
            return actual <= expected
        if op == ">":
            return actual > expected
        if op == "<":
            return actual < expected
        if op == "in":
            return actual in expected
        if op == "not_in":
            return actual not in expected
        if op == "has":
            return expected in actual
        if op == "lacks":
            return expected not in actual
        if op == "has_any":
            return any(x in actual for x in expected)
    except TypeError:
        return False
    return False


def default_audience(context: Context) -> frozenset[Role]:
    if context.scope == "lane" and context.lane is not None:
        return frozenset(LANE_ROLES[context.lane]) | {Role.JUNGLE}
    if context.scope == "map":
        return frozenset({Role.JUNGLE})
    if context.scope == "counterpick" and context.subject_role is not None:
        return frozenset({context.subject_role})  # my matchup: only my report
    if context.scope == "ally" and context.subject_role is not None:
        return ALL_ROLES - {context.subject_role}  # not news to the champion's own player
    return ALL_ROLES


def evaluate(rules: Iterable[Rule], insights: Insights) -> list[Fired]:
    """Every rule that fires for this game, once per context it fires in."""
    rules = list(rules)
    fired: list[Fired] = []
    for context in contexts(insights):
        for rule in rules:
            if rule.scope != context.scope:
                continue
            if rule.lanes and context.lane not in rule.lanes:
                continue
            if not matches(rule, context.values):
                continue
            audience = default_audience(context)
            if rule.their_lane and context.subject_role is not None:
                audience = frozenset(roles_in(lane_of(context.subject_role) or Lane.MID))
                audience = (audience if context.subject_role is not Role.JUNGLE
                            else frozenset()) | {Role.JUNGLE}  # fmt: skip
            elif rule.audience is not None:
                audience = (rule.audience & audience if context.scope == "lane"
                            else rule.audience)  # fmt: skip
            text = rule.say.format_map(context.fill)
            team = context.values.get("team", "") if rule.scope == "pair" else ""
            fired.append(Fired(rule, context.lane, context.subject, audience, text, team))
    return fired


def rule_test_values(rule: Rule, kind: str) -> dict[str, Any]:
    """The context a rule's own `tests.fires` / `tests.not` describes (everything else missing)."""
    values = dict.fromkeys(SCHEMA[rule.scope])
    for path, value in rule.tests[kind].items():
        values[path] = frozenset(value) if isinstance(value, list) else value  # tags, classes
    return values


def conflicts(fired: Iterable[Fired]) -> list[tuple[str, str]]:
    """Pairs of rules linked by `excludes` that fired together for the same lane."""
    fired = list(fired)
    found = []
    for a in fired:
        for b in fired:
            if b.rule.id in a.rule.excludes and a.lane == b.lane:
                found.append((a.rule.id, b.rule.id))
    return found
