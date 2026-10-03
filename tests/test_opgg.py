"""The OP.GG client (M8): tool check, parsers, protocol, throttle. Recorded answers, no network."""

import json
from pathlib import Path

import httpx
import pytest

from scout.data import opgg
from scout.data.opgg import FormatChanged, McpHttp, Opgg, OpggError, OpggNoData
from scout.model.roles import Role

SOURCES = Path(__file__).resolve().parent / "fixtures" / "sources" / "opgg"


def answer(name: str) -> dict:
    return json.loads((SOURCES / name).read_text(encoding="utf-8"))


def text(name: str) -> str:
    return answer(name)["result"]["content"][0]["text"]


TOOLS = answer("tools_list.json")["result"]["tools"]


# ---------------------------------------------------------------- names


@pytest.mark.parametrize(
    ("display", "expected"),
    [
        ("Lee Sin", "LEE_SIN"),
        ("Kai'Sa", "KAISA"),
        ("Dr. Mundo", "DR_MUNDO"),
        ("Nunu & Willump", "NUNU_WILLUMP"),
        ("Jarvan IV", "JARVAN_IV"),
        ("Wukong", "WUKONG"),
        ("Renata Glasc", "RENATA_GLASC"),
        ("K'Sante", "KSANTE"),
        ("LeBlanc", "LEBLANC"),
    ],
)
def test_opgg_names_follow_the_display_name(display, expected):
    """Checked live 2026-10-02: MONKEY_KING and NUNU are refused, these work."""
    assert opgg.opgg_name(display) == expected


def test_name_key_matches_opgg_and_data_dragon_spellings():
    assert opgg.name_key("Cho'Gath") == opgg.name_key("Cho'gath") == "chogath"


# ---------------------------------------------------------------- tool check (hard rule 6)


def test_the_recorded_tool_list_has_everything_we_use():
    assert opgg.check_tools(TOOLS) == []


def test_tool_changes_are_named():
    tools = json.loads(json.dumps(TOOLS))
    tools = [t for t in tools if t["name"] != opgg.SYNERGIES]
    guide = next(t for t in tools if t["name"] == opgg.GUIDE)
    guide["inputSchema"]["required"].append("tier")
    guide["inputSchema"]["properties"]["position"]["enum"].remove("adc")
    del next(t for t in tools if t["name"] == opgg.LANE_META)["inputSchema"]["properties"][
        "desired_output_fields"
    ]
    problems = opgg.check_tools(tools)
    assert f"tool {opgg.SYNERGIES} is missing" in problems
    assert f"{opgg.GUIDE}: new required parameter tier" in problems
    assert any("position no longer accepts" in p for p in problems)
    assert f"{opgg.LANE_META}: parameter desired_output_fields is missing" in problems


class Recorded:
    """A transport that answers from the recorded fixtures."""

    def __init__(self, tools=TOOLS):
        self.tools = tools
        self.calls: list[tuple[str, dict]] = []

    def request(self, method, params):
        if method == "tools/list":
            return {"tools": self.tools}
        self.calls.append((params["name"], params["arguments"]))
        name = {
            opgg.LANE_META: "lane_meta_all.json",
            opgg.SYNERGIES: "champion_synergies_Samira_bot.json",
            opgg.GUIDE: "lane_matchup_guide_LeeSin_vs_Elise_jungle.json",
        }[params["name"]]
        return answer(name)["result"]


def test_no_call_is_made_when_the_tools_changed():
    transport = Recorded(tools=[t for t in TOOLS if t["name"] != opgg.GUIDE])
    client = Opgg(transport, min_interval_s=0)
    with pytest.raises(OpggError, match="tools changed.*lol_get_lane_matchup_guide is missing"):
        client.guide(Role.JUNGLE, "LEE_SIN", "ELISE")
    assert transport.calls == []


def test_calls_are_spaced_out():
    now = [0.0]
    slept: list[float] = []

    def sleep(seconds: float) -> None:
        slept.append(seconds)
        now[0] += seconds

    client = Opgg(Recorded(), min_interval_s=1.0, clock=lambda: now[0], sleep=sleep)
    for _ in range(3):
        client.guide(Role.JUNGLE, "LEE_SIN", "ELISE")
    assert slept == [1.0, 1.0]


def test_client_methods_send_opgg_positions():
    transport = Recorded()
    client = Opgg(transport, min_interval_s=0)
    rows, shape = client.lane_meta()
    client.synergies("SAMIRA", Role.BOT, Role.SUPPORT)
    client.guide(Role.BOT, "JHIN", "SAMIRA")
    (_, meta), (_, syn), (_, guide) = transport.calls
    assert meta["position"] == "all" and len(meta["desired_output_fields"]) == 7
    assert (syn["my_position"], syn["synergy_position"]) == ("adc", "support")
    assert guide["position"] == "adc"
    assert len(rows) == 269 and "Top:champion," in shape


# ---------------------------------------------------------------- parsers


def test_lane_meta_is_parsed_by_header():
    rows = opgg.parse_lane_meta(text("lane_meta_all.json"))
    by_role: dict[Role, int] = {}
    for r in rows:
        by_role[r.role] = by_role.get(r.role, 0) + 1
    assert by_role == {Role.TOP: 62, Role.JUNGLE: 60, Role.MID: 58, Role.BOT: 40, Role.SUPPORT: 49}
    lee = next(r for r in rows if r.name == "Lee Sin")
    assert (lee.role, lee.games, lee.wins, lee.role_rate, lee.tier) == (
        Role.JUNGLE,
        203209,
        100077,
        0.96,
        2,
    )
    assert any(r.name == "Cho'Gath" for r in rows)


def test_matchup_guide():
    g = opgg.parse_guide(text("lane_matchup_guide_LeeSin_vs_Elise_jungle.json"))
    assert (g.role, g.my_key, g.my_name, g.opp_name, g.patch) == (
        Role.JUNGLE,
        64,
        "Lee Sin",
        "Elise",
        "16.19",
    )
    assert (60, 3572, 1700) in g.counters and len(g.counters) == 59
    assert g.game_lengths[0] == pytest.approx(0.519561) and set(g.game_lengths) == {
        0,
        25,
        30,
        35,
        40,
    }
    assert (g.lane_advantage, g.solo_kill_advantage, g.play_style) == ("even", "them", "even")
    assert g.tip.startswith("Elise excels")
    assert g.builds["core"][0] == opgg.Build((6692, 6610, 6333), 303, 160)
    assert g.builds["runes"][0].ids == (8010, 9111, 9104, 8014)
    assert (g.my_games, g.my_win_rate) == (203209, pytest.approx(0.492483))


def test_synergies():
    rows = opgg.parse_synergies(text("champion_synergies_Samira_bot.json"))
    assert rows[0] == opgg.SynergyRow(360, 111, 1700, 906, 2)


def test_compact_format_drift_fails_loudly():
    with pytest.raises(FormatChanged, match="3 values for 2 fields"):
        opgg.parse_compact("class X: a,b\n\nX(1,2,3)")
    with pytest.raises(FormatChanged, match="no class header for Y"):
        opgg.parse_compact("class X: a\n\nX(Y(1))")
    with pytest.raises(FormatChanged, match="rows lack role_rate"):
        opgg.parse_lane_meta(
            "class L: data\nclass D: positions\nclass P: top\n"
            "class T: champion,play,win,pick_rate,ban_rate,tier\n\n"
            'L(D(P([T("Garen",1,1,0.1,0.1,1)])))'
        )
    with pytest.raises(FormatChanged, match="missing counters"):
        broken = json.loads(text("lane_matchup_guide_LeeSin_vs_Elise_jungle.json"))
        del broken["data"]["counters"]
        opgg.parse_guide(json.dumps(broken))


def test_compact_strings_with_escapes():
    assert opgg.parse_compact('class X: a,b\n\nX("say \\"hi\\"",[true,null,-1.5])') == {
        "a": 'say "hi"',
        "b": [True, None, -1.5],
    }


# ---------------------------------------------------------------- the HTTP protocol


def mock_server(handler):
    return McpHttp(
        "https://example.test/mcp", http=httpx.Client(transport=httpx.MockTransport(handler))
    )


def test_session_handshake_then_calls():
    seen: list[tuple[str | None, str | None]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        seen.append((body.get("method"), request.headers.get("mcp-session-id")))
        if body["method"] == "initialize":
            return httpx.Response(
                200,
                json={"jsonrpc": "2.0", "id": body["id"], "result": {}},
                headers={"mcp-session-id": "abc"},
            )
        if "id" not in body:
            return httpx.Response(202)
        return httpx.Response(
            200, json={"jsonrpc": "2.0", "id": body["id"], "result": {"tools": []}}
        )

    server = mock_server(handler)
    assert server.request("tools/list", {}) == {"tools": []}
    server.request("tools/list", {})
    assert seen == [
        ("initialize", None),
        ("notifications/initialized", "abc"),
        ("tools/list", "abc"),
        ("tools/list", "abc"),
    ]


def test_unknown_champion_and_errors():
    error = answer("error_unknown_champion.json")["error"]

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        if body.get("method") == "tools/call":
            return httpx.Response(200, json={"jsonrpc": "2.0", "id": body["id"], "error": error})
        return httpx.Response(200, json={"jsonrpc": "2.0", "id": body.get("id"), "result": {}})

    with pytest.raises(OpggNoData, match="Invalid position or champion"):
        mock_server(handler).request("tools/call", {"name": opgg.GUIDE, "arguments": {}})


def test_event_stream_answers_and_lost_sessions():
    sessions = iter(["one", "two"])
    forgotten = {"one"}

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        if body.get("method") == "initialize":
            return httpx.Response(
                200,
                json={"jsonrpc": "2.0", "id": body["id"], "result": {}},
                headers={"mcp-session-id": next(sessions)},
            )
        if "id" not in body:
            return httpx.Response(202)
        if request.headers.get("mcp-session-id") in forgotten:
            return httpx.Response(404)
        event = json.dumps({"jsonrpc": "2.0", "id": body["id"], "result": {"ok": True}})
        return httpx.Response(
            200,
            text=f"event: message\ndata: {event}\n\n",
            headers={"content-type": "text/event-stream"},
        )

    assert mock_server(handler).request("tools/list", {}) == {"ok": True}


def test_network_down_is_an_opgg_error():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("no network")

    with pytest.raises(OpggError, match="OP.GG unreachable"):
        mock_server(handler).request("tools/list", {})


def test_a_guide_with_no_game_length_rates_still_parses():
    """Off-role picks (Darius mid) come back with `rate: null` for every game length; the
    matchups are still there (68 such calls failed in the first backtest, 2026-10-03)."""
    g = opgg.parse_guide(text("lane_matchup_guide_Darius_vs_Swain_mid.json"))
    assert g.game_lengths == {} and g.counters
