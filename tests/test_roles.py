import pytest

from scout.model.game import GameState, Pick
from scout.model.roles import (
    Lane,
    Queue,
    Role,
    has_positions,
    lane_of,
    queue_from_id,
    role_from_lcu,
    roles_in,
)


def test_every_role_maps_to_its_lane():
    # The prototype compared roles to lane names, so support and ADC got no lane rules.
    assert lane_of(Role.TOP) is Lane.TOP
    assert lane_of(Role.MID) is Lane.MID
    assert lane_of(Role.BOT) is Lane.BOT
    assert lane_of(Role.SUPPORT) is Lane.BOT
    assert lane_of(Role.JUNGLE) is None
    assert roles_in(Lane.BOT) == (Role.BOT, Role.SUPPORT)


@pytest.mark.parametrize(
    ("position", "role"),
    [("top", Role.TOP), ("jungle", Role.JUNGLE), ("middle", Role.MID),
     ("bottom", Role.BOT), ("utility", Role.SUPPORT), ("", None), ("unknown", None)],
)  # fmt: skip
def test_lcu_positions(position, role):
    assert role_from_lcu(position) is role


def test_queues():
    assert queue_from_id(420) is Queue.RANKED_SOLO
    assert queue_from_id(400) is Queue.NORMAL_DRAFT
    assert queue_from_id(450) is Queue.OTHER  # ARAM: no report
    assert not has_positions(Queue.OTHER)
    assert has_positions(Queue.CLASH)


def test_lane_opponent_is_the_enemy_in_my_role():
    ally = {r: Pick(f"A{r}", r) for r in Role}
    enemy = {r: Pick(f"E{r}", r) for r in Role}
    game = GameState("16.19.1", Queue.RANKED_SOLO, Role.SUPPORT, ally, enemy)
    assert game.lane_opponent().champ_id == "Esupport"
    assert game.my_lane is Lane.BOT
    assert game.my_pick.champ_id == "Asupport"
