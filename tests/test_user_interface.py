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


def test_user_shots_respect_ammo(db_session, team_factory, user_factory):
    from base64 import b64encode

    team_id = team_factory()
    user_id = user_factory()

    test_data = b64encode(b"123")

    UserInterface(user_id).join_team(team_id)

    # Give the user a bullet
    user = db_session.query(User).filter_by(id=user_id).first()
    user.num_bullets = 1
    db_session.commit()

    UserInterface(user_id).submit_shot(test_data)

    with pytest.raises(HTTPException):
        UserInterface(user_id).submit_shot(test_data)
