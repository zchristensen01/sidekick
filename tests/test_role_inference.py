"""Enemy role inference (docs/ROLES.md, Enemy roles and pick order)."""

import pytest

from scout.analysis.role_inference import infer_roles, rates_from_wiki_positions
from scout.model.roles import Role

T, J, M, B, S = Role.TOP, Role.JUNGLE, Role.MID, Role.BOT, Role.SUPPORT
RATES = {
    "LeeSin": {J: 1.0},
    "Gragas": {T: 0.3, J: 0.5, M: 0.2},
    "Ahri": {M: 1.0},
    "Jinx": {B: 1.0},
    "Thresh": {S: 1.0},
    "Darius": {T: 1.0},
    "Sejuani": {J: 0.8, T: 0.2},
    "Sylas": {M: 0.6, T: 0.4},
}


def test_single_role_champions_resolve_with_certainty():
    guess = infer_roles(["Darius", "LeeSin", "Ahri", "Jinx", "Thresh"], RATES)
    assert guess.best == {T: "Darius", J: "LeeSin", M: "Ahri", B: "Jinx", S: "Thresh"}
    assert all(guess.confidence(role) == pytest.approx(1.0, abs=0.001) for role in Role)


def test_teammates_resolve_a_flex_pick():
    # Gragas is usually a jungler, but with Lee Sin on the team he must be top or mid.
    guess = infer_roles(["Gragas", "LeeSin", "Ahri", "Jinx", "Thresh"], RATES)
    assert guess.best[T] == "Gragas" and guess.best[J] == "LeeSin"
    alone = infer_roles(["Gragas"], RATES)
    assert alone.best == {J: "Gragas"} and alone.confidence(J) == pytest.approx(0.5, abs=0.01)


def test_genuine_uncertainty_is_reported():
    guess = infer_roles(["Sejuani", "Gragas", "Sylas", "Jinx", "Thresh"], RATES)
    assert guess.best[J] == "Sejuani"
    jungle = dict(guess.by_role[J])
    assert jungle["Sejuani"] > jungle["Gragas"] > 0.05
    assert guess.likely(J, at_least=0.99) is None
    assert guess.likely(B, at_least=0.99) == "Jinx"


def test_probabilities_add_up():
    guess = infer_roles(["Sejuani", "Gragas", "Sylas", "Jinx", "Thresh"], RATES)
    for champ in ["Sejuani", "Gragas", "Sylas", "Jinx", "Thresh"]:
        total = sum(p for role in Role for c, p in guess.by_role[role] if c == champ)
        assert total == pytest.approx(1.0)
    probs = [a.probability for a in guess.alternatives]
    assert probs == sorted(probs, reverse=True) and len(probs) == 5


def test_partial_team_and_off_role_picks():
    two = infer_roles(["LeeSin", "Jinx"], RATES)
    assert two.best == {J: "LeeSin", B: "Jinx"}
    junglers = infer_roles(["LeeSin", "Sejuani"], RATES)  # two junglers: one plays off-role
    assert junglers.best[J] == "LeeSin" and junglers.best[T] == "Sejuani"
    unknown = infer_roles(["Newchamp"], RATES)  # no rates: every role equally likely
    assert unknown.confidence(next(iter(unknown.best))) == pytest.approx(0.2)


def test_limits():
    assert infer_roles([], RATES).best == {}
    with pytest.raises(ValueError):
        infer_roles(["A", "B", "C"], RATES, open_roles=[T, J])


def test_same_draft_same_guess():
    first = infer_roles(["Newchamp", "Otherchamp"], {})
    assert first == infer_roles(["Newchamp", "Otherchamp"], {})


def test_rates_from_wiki_positions_count_client_positions_double():
    rows = [
        {"champ_id": "Zac", "positions": "top|jungle|support", "client_positions": "jungle"},
        {"champ_id": "Jinx", "positions": "bot", "client_positions": "bot"},
        {"champ_id": "Nobody", "positions": "", "client_positions": ""},
    ]
    rates = rates_from_wiki_positions(rows)
    assert rates["Zac"] == {T: 0.25, J: 0.5, S: 0.25}
    assert rates["Jinx"] == {B: 1.0}
    assert "Nobody" not in rates
