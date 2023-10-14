from pathlib import Path

import pytest
from fastapi.exceptions import HTTPException

from backend.admin_interface import AdminInterface
from backend.model import Shot
from backend.user_interface import UserInterface


def test_making_item():
    assert isinstance(AdminInterface().make_new_item("ammo", {"num": 123}), str)


def test_using_made_item(user_in_team):
    encoded_item = AdminInterface().make_new_item("ammo", {"num": 123})

    UserInterface(user_in_team).collect_item(encoded_item)


def test_making_item_fail():
    with pytest.raises(HTTPException):
        AdminInterface().make_new_item("whatever", {"num": 123})


@pytest.fixture
def old_shot_prep(
    api_client, db_session, user_factory, team_factory, test_image_string
):
    team_a = team_factory()
    team_b = team_factory()

    user_a = user_factory()
    user_b = user_factory()

    UserInterface(user_a).join_team(team_a)
    UserInterface(user_b).join_team(team_b)

    AdminInterface().award_user_ammo(user_a, 1000)
    AdminInterface().award_user_ammo(user_b, 1000)

    # User A shoots user B (the admin hasn't checked it yet)
    UserInterface(user_a).submit_shot(test_image_string)
    shot_a = db_session.query(Shot.id).order_by(Shot.id.desc()).first()[0]

    # User B shoots user A (though they should be dead)
    UserInterface(user_b).submit_shot(test_image_string)
    shot_b = db_session.query(Shot.id).order_by(Shot.id.desc()).first()[0]

    # The admin checks user A and awards the shot to them
    response = api_client.post(
        f"/api/admin_shot_hit_user?shot_id={shot_a}&target_user_id={user_b}"
    )
    assert response.ok

    return user_a, user_b, shot_a, shot_b


# Now, shot B should be marked as checked
def test_dead_user_old_shots_not_in_database(old_shot_prep, db_session):
    user_a, user_b, shot_a, shot_b = old_shot_prep
    shot_b_model: Shot = db_session.query(Shot).get(shot_b)
    assert shot_b_model.checked


# ...and therefore not in the queue
def test_dead_user_old_shots_not_in_queue(old_shot_prep, db_session):
    user_a, user_b, shot_a, shot_b = old_shot_prep
    assert len(AdminInterface().get_unchecked_shots()) == 0


# User b should be dead
def test_dead_user_old_shots_user_b_dead(old_shot_prep, db_session):
    user_a, user_b, shot_a, shot_b = old_shot_prep
    assert UserInterface(user_b).get_user_model().hit_points == 0


# And user A should be alive
def test_dead_user_old_shots_user_a_alive(old_shot_prep, db_session):
    user_a, user_b, shot_a, shot_b = old_shot_prep
    assert UserInterface(user_a).get_user_model().hit_points == 1


# And user B should have got a bullet refund
def test_dead_user_old_shots_user_b_refunded(old_shot_prep, db_session):
    user_a, user_b, shot_a, shot_b = old_shot_prep
    assert UserInterface(user_b).get_user_model().num_bullets == 1000


# But user A shouldn't have
def test_dead_user_old_shots_user_a_not_refunded(old_shot_prep, db_session):
    user_a, user_b, shot_a, shot_b = old_shot_prep
    assert UserInterface(user_a).get_user_model().num_bullets == 999
