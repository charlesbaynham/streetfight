from uuid import UUID

from backend.model import User


def test_three_users(three_users):
    assert [isinstance(u, UUID) for u in three_users]


def test_one_team(one_team):
    return isinstance(one_team, UUID)


def test_client(api_client):
    pass


def test_user_in_team(db_session, user_in_team):
    user = db_session.query(User).get(user_in_team)
    assert user.team is not None
