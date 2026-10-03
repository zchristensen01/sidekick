"""The LoL Wiki (CC BY-SA 3.0): Module:ChampionData (Riot subclasses, positions, last-changed
patch) and each champion page's mechanic categories (knock-ups, dashes, stealth...).

The module is a Lua table; we parse it as data and never execute anything. Fields and filters:
docs/DATA.md (LoL wiki). Tested against tests/fixtures/sources/wiki/.
"""

import re
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode

from scout.data.patch import from_display_label
from scout.model.roles import Role

URL = "https://wiki.leagueoflegends.com/en-us/Module:ChampionData/data?action=raw"
LICENSE = "CC BY-SA 3.0"

# Wiki position labels -> roles. Unknown labels are reported, not guessed.
POSITION_ROLE = {
    "top": Role.TOP,
    "jungle": Role.JUNGLE,
    "middle": Role.MID,
    "mid": Role.MID,
    "bottom": Role.BOT,
    "bot": Role.BOT,
    "support": Role.SUPPORT,
}


class LuaParseError(ValueError):
    pass


@dataclass(frozen=True)
class WikiChampion:
    display_name: str
    champ_id: str  # `apiname`, the Data Dragon id
    key: int | None
    classes: tuple[str, ...]  # Riot subclasses, lowercase snake_case: ("diver",)
    range_type: str | None  # melee | ranged
    adaptive_type: str | None  # physical | magic
    positions: tuple[Role, ...]  # client + external positions, in role order
    client_positions: tuple[Role, ...]  # Riot's in-client positions only (usually the main role)
    unknown_positions: tuple[str, ...]
    last_changed_patch: str | None  # short Data Dragon patch: "V26.12" -> "16.12"
    ratings: dict[str, int]  # damage, durability, cc, mobility, utility, difficulty
    attack_range: float | None = None  # base attack range in game units
    move_speed: float | None = None  # base move speed


def parse_module(text: str) -> dict[str, WikiChampion]:
    """Champions by Data Dragon id. Entries that aren't playable champions are dropped."""
    table = parse_lua_return(text)
    if not isinstance(table, dict):
        raise LuaParseError("ChampionData didn't return a table of champions")
    champions: dict[str, WikiChampion] = {}
    for display_name, raw in table.items():
        if not isinstance(raw, dict) or not raw.get("apiname"):
            continue
        champ = _champion(str(display_name), raw)
        # Duplicates (e.g. "Kled & Skaarl" next to "Kled"): keep the first one seen.
        champions.setdefault(champ.champ_id, champ)
    return champions


def _champion(display_name: str, raw: dict[str, Any]) -> WikiChampion:
    positions: list[Role] = []
    client: list[Role] = []
    unknown: list[str] = []
    client_labels = _strings(raw.get("client_positions"))
    for label in client_labels + _strings(raw.get("external_positions")):
        role = POSITION_ROLE.get(label.lower())
        if role is None:
            unknown.append(label)
            continue
        if role not in positions:
            positions.append(role)
        if label in client_labels and role not in client:
            client.append(role)
    stats = raw.get("stats") if isinstance(raw.get("stats"), dict) else {}
    changes = raw.get("changes")
    try:
        last_changed = from_display_label(changes) if isinstance(changes, str) else None
    except ValueError:
        last_changed = None
    ratings = {
        name: raw[source]
        for name, source in (
            ("damage", "damage"), ("durability", "toughness"), ("cc", "control"),
            ("mobility", "mobility"), ("utility", "utility"), ("difficulty", "difficulty"),
        )
        if isinstance(raw.get(source), int)
    }  # fmt: skip
    return WikiChampion(
        display_name=display_name,
        champ_id=str(raw["apiname"]),
        key=raw["id"] if isinstance(raw.get("id"), int) else None,
        classes=tuple(_snake(c) for c in _strings(raw.get("role"))),
        range_type=_lower(raw.get("rangetype")),
        adaptive_type=_lower(raw.get("adaptivetype")),
        positions=tuple(r for r in Role if r in positions),
        client_positions=tuple(r for r in Role if r in client),
        unknown_positions=tuple(unknown),
        last_changed_patch=last_changed,
        ratings=ratings,
        attack_range=_stat(stats.get("range")),
        move_speed=_stat(stats.get("ms")),
    )


# ---------------------------------------------------------------- mechanics (page categories)
# Each champion page sits in categories like "Knockup champion" or "Dash champion", which the
# wiki groups under "Category:Advanced attributes" (each category page says what it means:
# "champions that possess the ability to knock units up on the spot through airborne"). The
# list of attribute categories is read at refresh time, not hard-coded.

API = "https://wiki.leagueoflegends.com/en-us/api.php"
ATTRIBUTES = "Category:Advanced attributes"
TITLES_PER_CALL = 15  # small batches rarely need the API's "continue" step
NOT_MECHANICS = frozenset({  # attribute categories about resources and range, not abilities
    "mana", "manaless", "energy", "fury", "health", "cooldown", "melee", "ranged",
})  # fmt: skip


def attributes_url() -> str:
    params = {"action": "query", "list": "categorymembers", "cmtitle": ATTRIBUTES,
              "cmtype": "subcat", "cmlimit": "max", "format": "json"}  # fmt: skip
    return f"{API}?{urlencode(params)}"


def categories_url(titles: list[str], cont: dict[str, str] | None = None) -> str:
    params = {"action": "query", "prop": "categories", "titles": "|".join(titles),
              "cllimit": "max", "redirects": "1", "format": "json", **(cont or {})}  # fmt: skip
    return f"{API}?{urlencode(params)}"


def mechanic_name(category: str) -> str | None:
    """'Category:Knock aside champion' -> 'knock_aside'; None for anything else."""
    name = category.removeprefix("Category:").strip()
    if not name.endswith(" champion") or name.startswith("Champion"):
        return None
    return _snake(name.removesuffix(" champion")) or None


def parse_attributes(raw: Any) -> frozenset[str]:
    """The mechanics the wiki tracks, from the 'Advanced attributes' category listing."""
    members = (raw or {}).get("query", {}).get("categorymembers", [])
    names = {mechanic_name(m.get("title", "")) for m in members if isinstance(m, dict)}
    return frozenset(n for n in names if n and n not in NOT_MECHANICS)


def parse_categories(raw: Any) -> tuple[dict[str, set[str]], dict[str, str] | None]:
    """({requested page title: its categories}, the API's continue parameters or None).
    Redirected and normalized titles are mapped back to the title that was asked for."""
    query = (raw or {}).get("query", {})
    back: dict[str, str] = {}
    for step in (*query.get("normalized", []), *query.get("redirects", [])):
        back[step["to"]] = back.get(step["from"], step["from"])
    found: dict[str, set[str]] = {}
    for page in query.get("pages", {}).values():
        title = page.get("title", "")
        cats = {c["title"] for c in page.get("categories", []) if "title" in c}
        found.setdefault(back.get(title, title), set()).update(cats)
    cont = raw.get("continue") if isinstance(raw, dict) else None
    return found, ({k: str(v) for k, v in cont.items()} if isinstance(cont, dict) else None)


def mechanics(categories: set[str], attributes: frozenset[str]) -> tuple[str, ...]:
    """A champion's mechanics: its categories that are wiki attributes, sorted."""
    names = {mechanic_name(c) for c in categories}
    return tuple(sorted(n for n in names if n and n in attributes))


def _stat(value: Any) -> float | None:
    return float(value) if isinstance(value, int | float) and not isinstance(value, bool) else None


def _strings(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [v for v in value if isinstance(v, str)]
    return []


def _lower(value: Any) -> str | None:
    return value.strip().lower() if isinstance(value, str) and value.strip() else None


def _snake(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", text.strip().lower()).strip("_")


# ---------------------------------------------------------------- a tiny Lua data reader

_TOKEN = re.compile(
    r"""
    (?P<space>\s+)
    | (?P<comment>--\[\[.*?\]\]|--[^\n]*)
    | (?P<str>"(?:[^"\\\n]|\\.)*"|'(?:[^'\\\n]|\\.)*')
    | (?P<num>(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?)
    | (?P<name>[A-Za-z_]\w*)
    | (?P<sym>[{}\[\]=,;()+\-*/])
    """,
    re.VERBOSE | re.DOTALL,
)
_ESCAPES = {"n": "\n", "t": "\t", "r": "\r", "\\": "\\", '"': '"', "'": "'", "\n": "\n"}


def _tokens(text: str) -> list[tuple[str, str, int]]:
    out: list[tuple[str, str, int]] = []
    pos = 0
    while pos < len(text):
        match = _TOKEN.match(text, pos)
        if not match:
            raise LuaParseError(f"unexpected character {text[pos]!r} at offset {pos}")
        kind = match.lastgroup or ""
        if kind not in ("space", "comment"):
            out.append((kind, match.group(), pos))
        pos = match.end()
    return out


def parse_lua_return(text: str) -> Any:
    """The value after `return` in a Lua module made only of literals and tables."""
    tokens = _tokens(text)
    for i, (kind, value, _) in enumerate(tokens):
        if kind == "name" and value == "return":
            result, end = _value(tokens, i + 1)
            return result
    raise LuaParseError("no `return` statement found")


def _value(tokens: list[tuple[str, str, int]], i: int) -> tuple[Any, int]:
    if i >= len(tokens):
        raise LuaParseError("unexpected end of input")
    kind, value, pos = tokens[i]
    if kind == "str":
        return _unquote(value), i + 1
    if kind == "num" or value in ("-", "("):
        return _sum(tokens, i)
    if kind == "name" and value in ("true", "false", "nil"):
        return {"true": True, "false": False, "nil": None}[value], i + 1
    if value == "{":
        return _table(tokens, i + 1)
    raise LuaParseError(f"unexpected {value!r} at offset {pos}")


# Arithmetic on number literals only, e.g. Kled's `84+1000/17`. No names, nothing executed.
def _sum(tokens: list[tuple[str, str, int]], i: int) -> tuple[float | int, int]:
    total, i = _product(tokens, i)
    while i < len(tokens) and tokens[i][1] in ("+", "-"):
        op = tokens[i][1]
        right, i = _product(tokens, i + 1)
        total = total + right if op == "+" else total - right
    return total, i


def _product(tokens: list[tuple[str, str, int]], i: int) -> tuple[float | int, int]:
    total, i = _number(tokens, i)
    while i < len(tokens) and tokens[i][1] in ("*", "/"):
        op = tokens[i][1]
        right, i = _number(tokens, i + 1)
        total = total * right if op == "*" else total / right
    return total, i


def _number(tokens: list[tuple[str, str, int]], i: int) -> tuple[float | int, int]:
    if i >= len(tokens):
        raise LuaParseError("unexpected end of input in a number")
    kind, value, pos = tokens[i]
    if value == "-":
        number, i = _number(tokens, i + 1)
        return -number, i
    if value == "(":
        number, i = _sum(tokens, i + 1)
        return number, _expect(tokens, i, ")")
    if kind == "num":
        is_int = value.isdigit()
        return (int(value) if is_int else float(value)), i + 1
    raise LuaParseError(f"expected a number, found {value!r} at offset {pos}")


def _table(tokens: list[tuple[str, str, int]], i: int) -> tuple[Any, int]:
    entries: dict[Any, Any] = {}
    next_index = 1
    while True:
        if i >= len(tokens):
            raise LuaParseError("unclosed table")
        kind, value, pos = tokens[i]
        if value == "}":
            i += 1
            break
        if value == "[":  # [key] = value
            key, i = _value(tokens, i + 1)
            i = _expect(tokens, i, "]")
            i = _expect(tokens, i, "=")
            entries[key], i = _value(tokens, i)
        elif kind == "name" and i + 1 < len(tokens) and tokens[i + 1][1] == "=":  # name = value
            entries[value], i = _value(tokens, i + 2)
        else:  # positional value
            entries[next_index], i = _value(tokens, i)
            next_index += 1
        if i < len(tokens) and tokens[i][1] in (",", ";"):
            i += 1
    if entries and list(entries) == list(range(1, len(entries) + 1)):
        return [entries[n] for n in range(1, len(entries) + 1)], i
    return entries, i


def _expect(tokens: list[tuple[str, str, int]], i: int, symbol: str) -> int:
    if i >= len(tokens) or tokens[i][1] != symbol:
        found = tokens[i][1] if i < len(tokens) else "end of input"
        raise LuaParseError(f"expected {symbol!r}, found {found!r}")
    return i + 1


def _unquote(literal: str) -> str:
    body = literal[1:-1]
    return re.sub(r"\\(.)", lambda m: _ESCAPES.get(m.group(1), m.group(1)), body, flags=re.S)
