from uuid import UUID


def test_three_users(three_users):
    assert [isinstance(u, UUID) for u in three_users]


def test_one_team(one_team):
    return isinstance(one_team, UUID)


def test_client(api_client):
    pass
