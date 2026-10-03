"""Hand-written game files (tests/fixtures/games/)."""

from pathlib import Path

import pytest

from scout.data.store import read_csv
from scout.model.gamefile import GameFileError, load_game
from scout.model.roles import Queue, Role

FIXTURES = Path(__file__).parent / "fixtures"
KNOWN = {r["champ_id"] for r in read_csv(FIXTURES / "static" / "16.19.1" / "champions.csv")}
GOOD = """name: {name}
ddragon_version: "16.19.1"
queue: ranked_solo
my_role: support
ally: {{top: Garen, jungle: LeeSin, mid: Ahri, bot: Jhin, support: Lulu}}
enemy: {{top: Malphite, jungle: Elise, mid: Yasuo, bot: Samira, support: Nautilus}}
pick_turns: {{Samira: 6, Lulu: 7}}
enemy_role_confidence: {{mid: 0.55}}
bans: [Zed]
"""


def write(tmp_path, text: str, name: str = "game") -> Path:
    path = tmp_path / f"{name}.yaml"
    path.write_text(text.format(name=name), encoding="utf-8")
    return path


@pytest.mark.parametrize("path", sorted((FIXTURES / "games").glob("*.yaml")))
def test_committed_game_files_load(path):
    game = load_game(path, KNOWN)
    assert len(game.ally) == 5 and len(game.enemy) == 5


def test_a_good_file(tmp_path):
    game = load_game(write(tmp_path, GOOD), KNOWN)
    assert game.queue is Queue.RANKED_SOLO and game.my_role is Role.SUPPORT
    assert game.my_pick.champ_id == "Lulu" and game.my_pick.pick_turn == 7
    assert game.enemy[Role.MID].role_confidence == 0.55
    assert game.enemy[Role.TOP].role_confidence == 1.0
    assert game.enemy[Role.BOT].pick_turn == 6 and game.bans == ["Zed"]


@pytest.mark.parametrize(
    ("change", "problem"),
    [
        (("name: {name}", "name: other"), "name must match"),
        (("queue: ranked_solo", "queue: aram"), "queue must be one of"),
        (("my_role: support", "my_role: adc"), "my_role must be one of"),
        (("LeeSin", "Leesin"), "unknown champion id 'Leesin'; did you mean LeeSin?"),
        (("support: Nautilus", "support: Nautilus, carry: Teemo"), "enemy role must be"),
        (("bot: Samira, ", ""), "enemy is missing roles: bot"),
        (("Samira: 6", "Teemo: 6"), "pick_turns names Teemo"),
        (("mid: 0.55", "mid: 1.5"), "between 0 and 1"),
    ],
)
def test_mistakes_are_explained(tmp_path, change, problem):
    with pytest.raises(GameFileError, match=problem.replace("?", r"\?")):
        load_game(write(tmp_path, GOOD.replace(*change)), KNOWN)


def test_unreadable_file(tmp_path):
    with pytest.raises(GameFileError, match="mapping"):
        load_game(write(tmp_path, "- just a list"), KNOWN)
