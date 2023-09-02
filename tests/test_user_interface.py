from uuid import uuid4 as uuid

import pytest
from fastapi.exceptions import HTTPException

from backend.model import User
from backend.user_interface import UserInterface


def test_can_join_new_team(user_factory):
    user_id = user_factory()
    UserInterface(user_id=user_id).join_team(uuid())


def test_can_join_existing_team(user_factory, team_factory):
    user_id = user_factory()

    UserInterface(user_id=user_id).join_team(team_factory())


def test_cannot_join_new_team_if_multiple_games(game_factory, user_factory):
    game_factory()
    game_factory()

    user_id = user_factory()

    with pytest.raises(HTTPException):
        UserInterface(user_id=user_id).join_team(uuid())


def test_user_shots_respect_ammo(db_session, team_factory, user_factory):
    from base64 import b64encode

    team_id = team_factory()
    user_id = user_factory()

    test_data = str(b64encode(b"123"))

    UserInterface(user_id).join_team(team_id)

    # Give the user some bullets
    user = db_session.query(User).filter_by(id=user_id).first()
    user.num_bullets = 3
    db_session.commit()

    for _ in range(3):
        UserInterface(user_id).submit_shot(test_data)

    with pytest.raises(HTTPException):
        UserInterface(user_id).submit_shot(test_data)


def test_user_cannot_shoot_when_dead(db_session, team_factory, user_factory):
    from base64 import b64encode

    team_id = team_factory()
    user_id = user_factory()

    test_data = str(b64encode(b"123"))

    UserInterface(user_id).join_team(team_id)

    # Give the user 3 bullets
    user = db_session.query(User).filter_by(id=user_id).first()
    user.num_bullets = 3
    db_session.commit()

    UserInterface(user_id).submit_shot(test_data)

    # Kill them
    UserInterface(user_id).kill()

    with pytest.raises(HTTPException):
        UserInterface(user_id).submit_shot(test_data)
