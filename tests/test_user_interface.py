from pathlib import Path
from uuid import uuid4 as uuid

import pytest
from fastapi.exceptions import HTTPException

from backend.model import User
from backend.user_interface import UserInterface


# Mock "create_task" for all unit tests in this module
@pytest.fixture(autouse=True)
def mock_asyncio_tasks(mocker):
    mocker.patch("asyncio.create_task")


@pytest.fixture
def test_image():
    return Path(__file__, "../sample_base64_image.txt").resolve().read_text()


def test_can_join_new_team(user_factory):
    user_id = user_factory()
    UserInterface(user_id=user_id).join_team(uuid())


def test_can_use_userinterface_as_contextmanager(user_factory):
    user_id = user_factory()

    with UserInterface(user_id=user_id) as ui:
        ui.join_team(uuid())


def test_can_reuse_userinterface_as_contextmanager(user_factory):
    user_id = user_factory()

    user_interface = UserInterface(user_id=user_id)

    with user_interface as ui:
        ui.join_team(uuid())

    with user_interface as ui:
        ui.get_user_model()


def test_can_join_existing_team(user_factory, team_factory):
    user_id = user_factory()

    UserInterface(user_id=user_id).join_team(team_factory())


def test_cannot_join_new_team_if_multiple_games(game_factory, user_factory):
    game_factory()
    game_factory()

    user_id = user_factory()

    with pytest.raises(HTTPException):
        UserInterface(user_id=user_id).join_team(uuid())


def test_user_shots_respect_ammo(db_session, team_factory, user_factory, test_image):
    team_id = team_factory()
    user_id = user_factory()

    UserInterface(user_id).join_team(team_id)

    # Give the user some bullets
    user = db_session.query(User).filter_by(id=user_id).first()
    user.num_bullets = 3
    db_session.commit()

    for _ in range(3):
        UserInterface(user_id).submit_shot(test_image)

    with pytest.raises(HTTPException):
        UserInterface(user_id).submit_shot(test_image)


def test_user_cannot_shoot_when_dead(
    db_session, team_factory, user_factory, test_image
):
    team_id = team_factory()
    user_id = user_factory()

    UserInterface(user_id).join_team(team_id)

    # Give the user 3 bullets
    user = db_session.query(User).filter_by(id=user_id).first()
    user.num_bullets = 3
    db_session.commit()

    UserInterface(user_id).submit_shot(test_image)

    # Kill them
    UserInterface(user_id).hit()

    with pytest.raises(HTTPException):
        UserInterface(user_id).submit_shot(test_image)


def test_can_give_health(user_in_team):
    UserInterface(user_in_team).award_HP()

    assert UserInterface(user_in_team).get_user_model().hit_points == 2


def test_can_give_multiple_health(user_in_team):
    UserInterface(user_in_team).award_HP(num=10)

    assert UserInterface(user_in_team).get_user_model().hit_points == 11


def test_can_give_ammo(user_in_team):
    UserInterface(user_in_team).award_ammo()

    assert UserInterface(user_in_team).get_user_model().num_bullets == 1


def test_can_give_multiple_ammo(user_in_team):
    UserInterface(user_in_team).award_ammo(num=10)

    assert UserInterface(user_in_team).get_user_model().num_bullets == 10


def test_user_in_team(user_in_team):
    assert UserInterface(user_in_team).get_user_model().team_id is not None
