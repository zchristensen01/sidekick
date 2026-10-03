"""The GET-only League client: auth, 404s, reconnecting after a client restart, errors."""

import base64
import re

import httpx
import pytest

from scout.lcu.client import (
    CHAMP_SELECT_SESSION,
    ENDPOINTS,
    GAMEFLOW_PHASE,
    TEMPLATES,
    LcuClient,
    LcuError,
    LcuUnavailable,
    allowed,
)
from scout.lcu.connection import LcuCredentials

OLD = LcuCredentials(port=50001, token="token-1", source="process")
NEW = LcuCredentials(port=50002, token="token-2", source="process")


class Finder:
    """Returns the given credentials in turn (the last one repeats); counts calls."""

    def __init__(self, *results: LcuCredentials | None):
        self.results = list(results)
        self.calls = 0

    def __call__(self) -> LcuCredentials | None:
        self.calls += 1
        return self.results[min(self.calls, len(self.results)) - 1]


def make_client(handler, finder) -> LcuClient:
    return LcuClient(finder, transport=httpx.MockTransport(handler))


def test_get_sends_basic_auth_and_parses_json():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        assert str(request.url) == "https://127.0.0.1:50001/lol-gameflow/v1/gameflow-phase"
        expected = base64.b64encode(b"riot:token-1").decode()
        assert request.headers["Authorization"] == f"Basic {expected}"
        return httpx.Response(200, json="ChampSelect")

    assert make_client(handler, Finder(OLD)).get(GAMEFLOW_PHASE) == "ChampSelect"


def test_404_and_empty_body_are_none():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == CHAMP_SELECT_SESSION:
            return httpx.Response(404, json={"message": "No active delegate"})
        return httpx.Response(204)

    client = make_client(handler, Finder(OLD))
    assert client.get(CHAMP_SELECT_SESSION) is None
    assert client.get(GAMEFLOW_PHASE) is None


def test_only_listed_endpoints_can_be_read():
    client = make_client(lambda r: httpx.Response(200, json={}), Finder(OLD))
    with pytest.raises(ValueError, match="ENDPOINTS"):
        client.get("/lol-champ-select/v1/session/my-selection")


def test_templates_take_one_plain_id_only():
    assert allowed("/lol-summoner/v2/summoners/puuid/7cc86c65-c7a2-55e4-8d14-b7ec33a09149")
    assert not allowed("/lol-summoner/v2/summoners/puuid/../../lol-login/v1/session")
    assert not allowed("/lol-summoner/v2/summoners/puuid/short")
    assert not allowed("/lol-summoner/v2/summoners/puuid/7cc86c65-c7a2-55e4-8d14-b7ec33a0914/x")


def test_not_running_is_unavailable_without_retry():
    finder = Finder(None)
    client = make_client(lambda r: httpx.Response(200, json="None"), finder)
    with pytest.raises(LcuUnavailable, match="not running"):
        client.get(GAMEFLOW_PHASE)
    assert finder.calls == 1


@pytest.mark.parametrize("failure", ["connect_error", "401"])
def test_reconnects_once_after_client_restart(failure):
    restarted = False

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.port == 50001 and restarted:
            if failure == "401":
                return httpx.Response(401)
            raise httpx.ConnectError("connection refused", request=request)
        return httpx.Response(200, json=f"port {request.url.port}")

    finder = Finder(OLD, NEW)
    client = make_client(handler, finder)
    assert client.get(GAMEFLOW_PHASE) == "port 50001"
    restarted = True  # new port and token; the old ones stop working
    assert client.get(GAMEFLOW_PHASE) == "port 50002"
    assert finder.calls == 2


def test_gives_up_after_one_retry_then_rediscovers_next_time():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    finder = Finder(OLD)
    client = make_client(handler, finder)
    with pytest.raises(LcuUnavailable):
        client.get(GAMEFLOW_PHASE)
    assert finder.calls == 1  # it had no connection yet, so nothing stale to retry
    with pytest.raises(LcuUnavailable):
        client.get(GAMEFLOW_PHASE)
    assert finder.calls == 2


def test_server_error_is_not_unavailable():
    client = make_client(lambda r: httpx.Response(500), Finder(OLD))
    with pytest.raises(LcuError) as info:
        client.get(GAMEFLOW_PHASE)
    assert not isinstance(info.value, LcuUnavailable)


def test_certificate_failure_is_reported_not_retried():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError(
            "[SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed", request=request
        )

    finder = Finder(OLD)
    with pytest.raises(LcuError, match="riotgames.pem") as info:
        make_client(handler, finder).get(GAMEFLOW_PHASE)
    assert not isinstance(info.value, LcuUnavailable)
    assert finder.calls == 1


def test_every_endpoint_is_documented(repo_paths):
    lcu_doc = (repo_paths.root / "docs" / "LCU.md").read_text(encoding="utf-8")
    section = re.search(r"## 2\..*?(?=\n## )", lcu_doc, re.S)
    assert section, "docs/LCU.md has no section 2"
    for path in ENDPOINTS | TEMPLATES:
        assert f"`{path}`" in section.group(0), f"{path} isn't listed in docs/LCU.md section 2"
