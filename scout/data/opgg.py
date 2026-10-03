"""OP.GG MCP client: lane stats, role rates, matchup tables, labels, synergies, builds.

Lists tools on connect and fails loudly if a tool or parameter we use is missing (CLAUDE.md
hard rule 6). Parses the compact class format by header. Throttled, with timeouts.
Details: docs/DATA.md (OP.GG MCP server). Tested against tests/fixtures/sources/opgg/.

Speaks the MCP protocol over plain HTTP (initialize, notifications/initialized, then requests
with the session id) instead of the `mcp` SDK: the SDK's strict validation rejects OP.GG's
tool list (two Valorant tools declare an array output schema). DECISIONS.md #40.
"""

import itertools
import json
import re
import threading
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any, Protocol

import httpx

from scout.model.roles import Role

ENDPOINT = "https://mcp-api.op.gg/mcp"
PROTOCOL_VERSION = "2025-06-18"
CLIENT_INFO = {"name": "lol-scout", "version": "0.1"}
SOURCE = "opgg"

POSITION: dict[Role, str] = {
    Role.TOP: "top",
    Role.JUNGLE: "jungle",
    Role.MID: "mid",
    Role.BOT: "adc",
    Role.SUPPORT: "support",
}
ROLE_OF_POSITION = {v: k for k, v in POSITION.items()}

LANE_META = "lol_list_lane_meta_champions"
GUIDE = "lol_get_lane_matchup_guide"
SYNERGIES = "lol_get_champion_synergies"
PROFILE = "lol_get_summoner_profile"
# The tools we call and every argument we pass. Checked against tools/list before any call.
EXPECTED_TOOLS: dict[str, tuple[str, ...]] = {
    LANE_META: ("position", "desired_output_fields"),
    GUIDE: ("position", "my_champion", "opponent_champion"),
    SYNERGIES: ("champion", "my_position", "synergy_position", "desired_output_fields"),
    PROFILE: ("game_name", "tag_line", "region", "desired_output_fields"),
}
# Riot platform (config player.platform) -> OP.GG's region code.
REGION_OF_PLATFORM = {
    "na1": "NA", "euw1": "EUW", "eun1": "EUNE", "kr": "KR", "jp1": "JP", "br1": "BR",
    "la1": "LAN", "la2": "LAS", "tr1": "TR", "ru": "RU", "me1": "ME", "oc1": "OCE",
}  # fmt: skip
PROFILE_FIELDS = [
    "data.summoner.ranked_most_champions.my_champion_stats[].{champion_name,id,lose,play,win}",
    "data.summoner.ranked_most_champions.my_champion_stats[].basic.{kill,death,assist}",
    "data.summoner.recent_champion_stats[].{assist,champion_name,death,id,kill,play,win}",
    "data.summoner.league_stats[].{game_type,win,lose}",
    "data.summoner.league_stats[].tier_info.{tier,division,lp}",
]
POSITION_ARGS = ("position", "my_position", "synergy_position")

LANE_FIELDS = ("champion", "play", "win", "pick_rate", "role_rate", "ban_rate", "tier")
SYNERGY_FIELDS = ("champion_id", "synergy_champion_id", "play", "win")
GUIDE_FIELDS = (
    "summary",
    "counters",
    "game_lengths",
    "trends",
    "lane_advantage_champion",
    "lane_solo_kill_advantage_champion",
    "recommended_play_style",
    "opponent_champion_tip",
    "core_items",
    "boots",
    "starter_items",
    "summoner_spells",
)
BUILD_KINDS = {
    "core": "core_items",
    "boots": "boots",
    "starter": "starter_items",
    "spells": "summoner_spells",
    "runes": "runes",
}


class OpggError(Exception):
    """OP.GG failed: unreachable, an error answer, or a changed format."""


class OpggNoData(OpggError):
    """OP.GG has nothing for this champion and lane (also its answer for an unknown name)."""


class FormatChanged(OpggError):
    """A response no longer has the fields we parse. Re-record the fixture, fix the parser."""


def opgg_name(display_name: str) -> str:
    """OP.GG's champion argument: 'Kai'Sa' -> KAISA, 'Dr. Mundo' -> DR_MUNDO,
    'Nunu & Willump' -> NUNU_WILLUMP, 'Wukong' -> WUKONG (checked live 2026-10-02)."""
    letters = re.sub(r"[^A-Z0-9 ]", "", display_name.upper().replace("&", " "))
    return "_".join(letters.split())


def name_key(display_name: str) -> str:
    """Loose match between OP.GG and Data Dragon display names: 'Cho'Gath' -> 'chogath'."""
    return re.sub(r"[^a-z0-9]", "", display_name.casefold())


# ---------------------------------------------------------------- tool check


def check_tools(tools: list[Mapping[str, Any]]) -> list[str]:
    """Problems with the tools we use: missing tools, parameters, or position values."""
    problems = []
    by_name = {t.get("name"): t for t in tools}
    for name, args in EXPECTED_TOOLS.items():
        tool = by_name.get(name)
        if tool is None:
            problems.append(f"tool {name} is missing")
            continue
        schema = tool.get("inputSchema") or {}
        props = schema.get("properties") or {}
        problems += [f"{name}: parameter {a} is missing" for a in args if a not in props]
        problems += [
            f"{name}: new required parameter {r}"
            for r in schema.get("required") or []
            if r not in args
        ]
        for arg in POSITION_ARGS:
            allowed = (props.get(arg) or {}).get("enum")
            if allowed and not set(POSITION.values()) <= set(allowed):
                problems.append(f"{name}: {arg} no longer accepts {sorted(POSITION.values())}")
    return problems


# ---------------------------------------------------------------- compact class format


def parse_compact(text: str) -> Any:
    """'class X: a,b' header lines, then one value like X(1,[Y("s",true)]). Constructors
    become dicts keyed by their class header. Raises FormatChanged on anything unexpected."""
    headers: dict[str, list[str]] = {}
    lines = text.strip().splitlines()
    body_start = 0
    for i, line in enumerate(lines):
        match = re.match(r"class (\w+):\s*(.*)$", line.strip())
        if match:
            headers[match[1]] = [f.strip() for f in match[2].split(",") if f.strip()]
        elif line.strip():
            body_start = i
            break
    body = "\n".join(lines[body_start:])
    if not headers or not body:
        raise FormatChanged("not the compact class format")
    value, end = _Reader(body, headers).value(0)
    if body[end:].strip():
        raise FormatChanged(f"unexpected text after the value: {body[end : end + 40]!r}")
    return value


def fingerprint(headers_or_keys: Any) -> str:
    """Sorted field names: shows in fetch_log exactly when a source changed shape."""
    if isinstance(headers_or_keys, str):
        found = re.findall(r"^class (\w+):\s*(.*)$", headers_or_keys, re.M)
        return ";".join(sorted(f"{name}:{fields}" for name, fields in found))
    return ",".join(sorted(headers_or_keys))


@dataclass
class _Reader:
    text: str
    headers: dict[str, list[str]]

    def value(self, i: int) -> tuple[Any, int]:
        i = self._skip(i)
        if i >= len(self.text):
            raise FormatChanged("the value ended early")
        ch = self.text[i]
        if ch == '"':
            return self._string(i)
        if ch == "[":
            return self._list(i)
        match = re.compile(r"-?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?").match(self.text, i)
        if match:
            number = match[0]
            is_float = any(c in number for c in ".eE")
            return (float(number) if is_float else int(number)), match.end()
        match = re.compile(r"[A-Za-z_]\w*").match(self.text, i)
        if not match:
            raise FormatChanged(f"unexpected {self.text[i : i + 20]!r}")
        word, i = match[0], match.end()
        if word in ("true", "false", "null"):
            return {"true": True, "false": False, "null": None}[word], i
        if self.text[i : i + 1] != "(":
            raise FormatChanged(f"unexpected word {word!r}")
        if word not in self.headers:
            raise FormatChanged(f"no class header for {word}")
        args, i = self._items(i + 1, ")")
        names = self.headers[word]
        if len(args) != len(names):
            raise FormatChanged(f"{word} has {len(args)} values for {len(names)} fields")
        return dict(zip(names, args, strict=True)), i

    def _string(self, i: int) -> tuple[str, int]:
        j = i + 1
        while j < len(self.text):
            if self.text[j] == "\\":
                j += 2
                continue
            if self.text[j] == '"':
                return json.loads(self.text[i : j + 1]), j + 1
            j += 1
        raise FormatChanged("unterminated string")

    def _list(self, i: int) -> tuple[list[Any], int]:
        return self._items(i + 1, "]")

    def _items(self, i: int, close: str) -> tuple[list[Any], int]:
        items: list[Any] = []
        i = self._skip(i)
        if self.text[i : i + 1] == close:
            return items, i + 1
        while True:
            item, i = self.value(i)
            items.append(item)
            i = self._skip(i)
            ch = self.text[i : i + 1]
            if ch == close:
                return items, i + 1
            if ch != ",":
                raise FormatChanged(f"expected ',' or {close!r} at {self.text[i : i + 20]!r}")
            i += 1

    def _skip(self, i: int) -> int:
        while i < len(self.text) and self.text[i].isspace():
            i += 1
        return i


# ---------------------------------------------------------------- parsed results


@dataclass(frozen=True)
class LaneRow:
    role: Role
    name: str  # OP.GG display name, e.g. "Cho'Gath"
    games: int
    wins: int
    pick_rate: float
    role_rate: float
    ban_rate: float
    tier: int | None


@dataclass(frozen=True)
class Build:
    ids: tuple[int, ...]
    games: int
    wins: int


@dataclass(frozen=True)
class Guide:
    """One lol_get_lane_matchup_guide answer: my champion's view of one lane."""

    role: Role
    my_key: int  # League champion key (LCU id), e.g. 64 for Lee Sin
    my_name: str
    opp_name: str
    patch: str  # OP.GG's newest patch in the trends, e.g. "16.19"
    counters: tuple[tuple[int, int, int], ...]  # (opponent key, games, wins of mine)
    game_lengths: dict[int, float]  # minute bucket -> my win rate
    lane_advantage: str  # us | them | even | "" (from my side)
    solo_kill_advantage: str
    play_style: str
    tip: str
    builds: dict[str, tuple[Build, ...]] = field(default_factory=dict)
    my_games: int = 0  # my games in this role (summary), for the base win rate
    my_win_rate: float | None = None
    fingerprint: str = ""


@dataclass(frozen=True)
class SynergyRow:
    key: int
    ally_key: int
    games: int
    wins: int
    tier: int | None


@dataclass(frozen=True)
class ChampRecord:
    """A player's games on one champion. Kills, deaths and assists are totals (OP.GG sums them
    over the games), so averages divide by `games`."""

    key: int  # Riot's champion key
    games: int
    wins: int
    kills: int = 0
    deaths: int = 0
    assists: int = 0


@dataclass(frozen=True)
class Profile:
    """What OP.GG shows for one player: solo queue rank, ranked games per champion this season,
    and their most recent games per champion. No identifiers are kept."""

    tier: str | None  # "GOLD"; None = unranked in solo queue
    division: int | None
    lp: int | None
    solo_wins: int
    solo_losses: int
    season: dict[int, ChampRecord]  # champion key -> ranked games this season
    recent: dict[int, ChampRecord]  # champion key -> recent games (all queues OP.GG counts)


def parse_profile(text: str) -> Profile:
    root = parse_compact(text)
    try:
        summoner = root["data"]["summoner"]
    except (KeyError, TypeError) as exc:
        raise FormatChanged(f"profile: no data.summoner ({exc})") from None
    solo = next((s for s in summoner.get("league_stats") or []
                 if isinstance(s, dict) and s.get("game_type") == "SOLORANKED"), {})  # fmt: skip
    tier_info = solo.get("tier_info") or {}

    def record(entry: dict[str, Any], totals: dict[str, Any]) -> ChampRecord | None:
        if not isinstance(entry.get("id"), int) or not isinstance(entry.get("play"), int):
            return None
        return ChampRecord(entry["id"], entry["play"], int(entry.get("win") or 0),
                           int(totals.get("kill") or 0), int(totals.get("death") or 0),
                           int(totals.get("assist") or 0))  # fmt: skip

    season: dict[int, ChampRecord] = {}
    ranked = (summoner.get("ranked_most_champions") or {}).get("my_champion_stats") or []
    for e in ranked:
        found = record(e, e.get("basic") or {}) if isinstance(e, dict) else None
        if found is not None:
            season[found.key] = found
    recent: dict[int, ChampRecord] = {}
    for e in summoner.get("recent_champion_stats") or []:
        found = record(e, e) if isinstance(e, dict) else None
        if found is not None:
            recent[found.key] = found
    return Profile(
        tier_info.get("tier") or None, tier_info.get("division"), tier_info.get("lp"),
        int(solo.get("win") or 0), int(solo.get("lose") or 0), season, recent,
    )  # fmt: skip


def parse_lane_meta(text: str) -> list[LaneRow]:
    root = parse_compact(text)
    try:
        positions = root["data"]["positions"]
    except (KeyError, TypeError) as exc:
        raise FormatChanged(f"lane meta: no data.positions ({exc})") from None
    rows = []
    for position, entries in positions.items():
        role = ROLE_OF_POSITION.get(position)
        if role is None:
            raise FormatChanged(f"lane meta: unknown position {position!r}")
        for e in entries or []:
            missing = [f for f in LANE_FIELDS if f not in e]
            if missing:
                raise FormatChanged(f"lane meta: rows lack {', '.join(missing)}")
            rows.append(
                LaneRow(
                    role,
                    e["champion"],
                    int(e["play"]),
                    int(e["win"]),
                    float(e["pick_rate"]),
                    float(e["role_rate"]),
                    float(e["ban_rate"]),
                    _int(e["tier"]),
                )
            )
    if not rows:
        raise FormatChanged("lane meta: no champions")
    return rows


def parse_guide(text: str) -> Guide:
    try:
        root = json.loads(text)
        data = root["data"]
        missing = [f for f in GUIDE_FIELDS if f not in data]
        if missing:
            raise FormatChanged(f"matchup guide: missing {', '.join(missing)}")
        role = ROLE_OF_POSITION[root["position"]]
        me, opp = root["my_champion"], root["opponent_champion"]
        versions = [
            t["version"]
            for kind in ("win", "pick", "ban")
            for t in data["trends"].get(kind) or []
            if t.get("version")
        ]
        if not versions:
            raise FormatChanged("matchup guide: no patch in trends")
        position = next(
            (
                p
                for p in data["summary"].get("positions") or []
                if p.get("name", "").lower() == root["position"]
            ),
            None,
        )
        stats = (position or {}).get("stats") or {}
        builds = {
            kind: tuple(
                Build(
                    tuple(int(i) for i in b.get("ids") or b.get("primary_rune_ids") or []),
                    int(b["play"]),
                    int(b["win"]),
                )
                for b in data.get(source) or []
            )
            for kind, source in BUILD_KINDS.items()
        }
        return Guide(
            role=role,
            my_key=int(data["summary"]["id"]),
            my_name=me,
            opp_name=opp,
            patch=max(versions, key=_version_key),
            counters=tuple(
                (int(c["champion_id"]), int(c["play"]), int(c["win"])) for c in data["counters"]
            ),
            game_lengths={int(g["game_length"]): float(g["rate"]) for g in data["game_lengths"]
                          if g.get("rate") is not None},  # null where too few games (off-role)
            lane_advantage=_side(data["lane_advantage_champion"], me, opp),
            solo_kill_advantage=_side(data["lane_solo_kill_advantage_champion"], me, opp),
            play_style=str(data["recommended_play_style"] or "").lower(),
            tip=str(data["opponent_champion_tip"] or "").strip(),
            builds=builds,
            my_games=int(stats.get("play") or 0),
            my_win_rate=float(stats["win_rate"]) if stats.get("win_rate") is not None else None,
            fingerprint=fingerprint(data.keys()),
        )
    except FormatChanged:
        raise
    except (ValueError, KeyError, TypeError) as exc:
        raise FormatChanged(f"matchup guide: {type(exc).__name__}: {exc}") from None


def parse_synergies(text: str) -> list[SynergyRow]:
    root = parse_compact(text)
    try:
        entries = root["data"]["synergies"]
    except (KeyError, TypeError) as exc:
        raise FormatChanged(f"synergies: no data.synergies ({exc})") from None
    rows = []
    for e in entries or []:
        missing = [f for f in SYNERGY_FIELDS if f not in e]
        if missing:
            raise FormatChanged(f"synergies: rows lack {', '.join(missing)}")
        tier = (e.get("synergy_tier_data") or {}).get("tier")
        rows.append(
            SynergyRow(
                int(e["champion_id"]),
                int(e["synergy_champion_id"]),
                int(e["play"]),
                int(e["win"]),
                _int(tier),
            )
        )
    return rows


def _side(label: Any, me: str, opp: str) -> str:
    text = str(label or "").strip()
    if not text:
        return ""
    if text.upper() == "EVEN":
        return "even"
    if name_key(text) == name_key(me):
        return "us"
    if name_key(text) == name_key(opp):
        return "them"
    return ""


def _int(value: Any) -> int | None:
    return int(value) if isinstance(value, (int, float)) else None


def _version_key(version: str) -> tuple[int, ...]:
    return tuple(int(p) for p in version.split(".") if p.isdigit())


# ---------------------------------------------------------------- transport


class Transport(Protocol):
    def request(self, method: str, params: dict[str, Any]) -> dict[str, Any]: ...


class McpHttp:
    """MCP over Streamable HTTP: one session, re-opened if the server forgets it."""

    def __init__(
        self, url: str = ENDPOINT, timeout_s: float = 15.0, http: httpx.Client | None = None
    ) -> None:
        self.url = url
        self.http = http or httpx.Client(timeout=timeout_s)
        self._session: str | None = None
        self._opened = False
        self._lock = threading.Lock()
        self._ids = itertools.count(1)

    def request(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            if not self._opened:
                self._open()
        try:
            return self._send(method, params)
        except _SessionLost:
            with self._lock:
                self._open()
            return self._send(method, params)

    def close(self) -> None:
        self.http.close()

    def _open(self) -> None:
        self._session = None
        response = self._post(
            {
                "jsonrpc": "2.0",
                "id": next(self._ids),
                "method": "initialize",
                "params": {
                    "protocolVersion": PROTOCOL_VERSION,
                    "capabilities": {},
                    "clientInfo": CLIENT_INFO,
                },
            }
        )
        self._session = response.headers.get("mcp-session-id")
        self._post({"jsonrpc": "2.0", "method": "notifications/initialized"})
        self._opened = True

    def _send(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        request_id = next(self._ids)
        response = self._post(
            {"jsonrpc": "2.0", "id": request_id, "method": method, "params": params}
        )
        message = _message(response, request_id)
        if "error" in message:
            error = message["error"] or {}
            text = f"{error.get('message', 'error')} (code {error.get('code')})"
            if error.get("code") == -32600:
                raise OpggNoData(text)
            raise OpggError(f"OP.GG answered with an error: {text}")
        return message.get("result") or {}

    def _post(self, body: dict[str, Any]) -> httpx.Response:
        headers = {
            "Accept": "application/json, text/event-stream",
            "Content-Type": "application/json",
        }
        if self._session:
            headers["Mcp-Session-Id"] = self._session
            headers["MCP-Protocol-Version"] = PROTOCOL_VERSION
        try:
            response = self.http.post(self.url, json=body, headers=headers)
        except httpx.HTTPError as exc:
            raise OpggError(f"OP.GG unreachable ({type(exc).__name__}: {exc})") from None
        if response.status_code == 404 and self._session:
            raise _SessionLost()
        if response.status_code >= 400:
            raise OpggError(f"OP.GG returned HTTP {response.status_code}")
        return response


class _SessionLost(Exception):
    pass


def _message(response: httpx.Response, request_id: int) -> dict[str, Any]:
    """The JSON-RPC answer: a plain JSON body, or the matching event in an event stream."""
    kind = response.headers.get("content-type", "")
    try:
        if "text/event-stream" in kind:
            for line in response.text.splitlines():
                if line.startswith("data:"):
                    message = json.loads(line[5:].strip())
                    if message.get("id") == request_id:
                        return message
            raise OpggError("OP.GG's event stream had no answer")
        return response.json()
    except json.JSONDecodeError as exc:
        raise OpggError(f"OP.GG's answer wasn't JSON ({exc})") from None


# ---------------------------------------------------------------- the client


@dataclass
class Opgg:
    """The tools we use, throttled: at most one call start per `min_interval_s`, and at most
    `max_concurrent` calls at once (docs/DATA.md, Being a polite client)."""

    transport: Transport
    min_interval_s: float = 1.0
    max_concurrent: int = 2
    clock: Callable[[], float] = time.monotonic
    sleep: Callable[[float], None] = time.sleep
    lang: str = "en_US"
    _checked: bool = False
    _next_start: float = 0.0
    _lock: threading.Lock = field(default_factory=threading.Lock)
    _slots: threading.Semaphore = field(init=False)

    def __post_init__(self) -> None:
        self._slots = threading.Semaphore(self.max_concurrent)

    def check(self) -> None:
        """List tools and fail loudly if anything we use changed (CLAUDE.md hard rule 6)."""
        with self._lock:
            if self._checked:
                return
        result = self.transport.request("tools/list", {})
        problems = check_tools(result.get("tools") or [])
        if problems:
            raise OpggError(
                "OP.GG's tools changed; stats are off until the client is fixed: "
                + "; ".join(problems)
            )
        with self._lock:
            self._checked = True

    def call(self, tool: str, arguments: dict[str, Any]) -> str:
        self.check()
        with self._slots:
            with self._lock:
                now = self.clock()
                wait = self._next_start - now
                self._next_start = max(now, self._next_start) + self.min_interval_s
            if wait > 0:
                self.sleep(wait)
            result = self.transport.request("tools/call", {"name": tool, "arguments": arguments})
        if result.get("isError"):
            raise OpggError(f"{tool} failed: {_text(result)[:200]}")
        return _text(result)

    def lane_meta(self) -> tuple[list[LaneRow], str]:
        fields = "{" + ",".join(sorted(LANE_FIELDS)) + "}"
        wanted = [f"data.positions.{p}[].{fields}" for p in POSITION.values()]
        text = self.call(
            LANE_META,
            {
                "position": "all",
                "lang": self.lang,
                "desired_output_fields": [*wanted, "lang", "position_filter"],
            },
        )
        return parse_lane_meta(text), fingerprint(text)

    def guide(self, role: Role, my_champion: str, opponent: str) -> Guide:
        """my_champion and opponent are OP.GG names (opgg_name)."""
        text = self.call(
            GUIDE,
            {
                "position": POSITION[role],
                "my_champion": my_champion,
                "opponent_champion": opponent,
                "lang": self.lang,
            },
        )
        return parse_guide(text)

    def profile(self, game_name: str, tag_line: str, region: str) -> Profile:
        """One player's rank and champion records. The Riot ID is only passed to OP.GG."""
        text = self.call(PROFILE, {"game_name": game_name, "tag_line": tag_line,
                                   "region": region, "lang": self.lang,
                                   "desired_output_fields": PROFILE_FIELDS})  # fmt: skip
        return parse_profile(text)

    def synergies(self, champion: str, role: Role, ally_role: Role) -> tuple[list[SynergyRow], str]:
        fields = "{" + ",".join(sorted((*SYNERGY_FIELDS, "win_rate"))) + "}"
        text = self.call(
            SYNERGIES,
            {
                "champion": champion,
                "my_position": POSITION[role],
                "synergy_position": POSITION[ally_role],
                "lang": self.lang,
                "desired_output_fields": [
                    f"data.synergies[].{fields}",
                    "data.synergies[].synergy_tier_data.{tier}",
                ],
            },
        )
        return parse_synergies(text), fingerprint(text)


def _text(result: Mapping[str, Any]) -> str:
    content = result.get("content") or []
    if not content or not isinstance(content[0], dict) or "text" not in content[0]:
        raise FormatChanged("the answer has no text content")
    return str(content[0]["text"])
