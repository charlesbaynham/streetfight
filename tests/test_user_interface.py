from uuid import uuid4 as uuid

from backend.user_interface import UserInterface


def test_can_join_game(user_factory):
    user_id = user_factory()
    UserInterface(user_id=user_id).join_game(uuid())
