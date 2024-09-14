from pathlib import Path

import pytest
from fastapi.exceptions import HTTPException

from backend.admin_interface import AdminInterface
from backend.model import Shot
from backend.model import User
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
    assert response.is_success

    return user_a, user_b, shot_a, shot_b


# Now, shot A should have been marked as checked (because it was)
def test_alive_user_shot_checked(old_shot_prep, db_session):
    user_a, user_b, shot_a, shot_b = old_shot_prep
    shot_a_model: Shot = db_session.query(Shot).get(shot_a)
    assert shot_a_model.checked


# Shot B should be marked as checked because it's now invalid
def test_dead_user_shot_checked(old_shot_prep, db_session):
    user_a, user_b, shot_a, shot_b = old_shot_prep
    shot_b_model: Shot = db_session.query(Shot).get(shot_b)
    assert shot_b_model.checked


# ...and therefore not in the queue
def test_dead_user_old_shots_not_in_queue(old_shot_prep):
    user_a, user_b, shot_a, shot_b = old_shot_prep

    num_shots, shots = AdminInterface().get_unchecked_shots()
    assert len(shots) == 0
    assert num_shots == 0


# User b should be dead
def test_dead_user_old_shots_user_b_dead(old_shot_prep):
    user_a, user_b, shot_a, shot_b = old_shot_prep
    assert UserInterface(user_b).get_user_model().hit_points == 0


# And user A should be alive
def test_dead_user_old_shots_user_a_alive(old_shot_prep):
    user_a, user_b, shot_a, shot_b = old_shot_prep
    assert UserInterface(user_a).get_user_model().hit_points == 1


# And user B should have got a bullet refund
def test_dead_user_old_shots_user_b_refunded(old_shot_prep):
    user_a, user_b, shot_a, shot_b = old_shot_prep
    assert UserInterface(user_b).get_user_model().num_bullets == 1000


# But user A shouldn't have
def test_dead_user_old_shots_user_a_not_refunded(old_shot_prep):
    user_a, user_b, shot_a, shot_b = old_shot_prep
    assert UserInterface(user_a).get_user_model().num_bullets == 999


# The good Shot should now record both the shooter and the shootee
def test_shots_record_targets(old_shot_prep):
    user_a, user_b, shot_a, shot_b = old_shot_prep
    shot = AdminInterface()._get_shot_orm(shot_a)

    assert shot.user_id == user_a
    assert shot.target_user_id == user_b


# The refunded Shot should be only the shooter
def test_shots_record_targets(old_shot_prep):
    user_a, user_b, shot_a, shot_b = old_shot_prep
    shot = AdminInterface().get_shot_model(shot_b)

    assert shot.user_id == user_b
    assert shot.target_user_id is None


def test_scoreboard_builds(db_session, team_factory, user_factory):
    team_id = team_factory()
    user_id_1 = user_factory()
    user_id_2 = user_factory()
    UserInterface(user_id_1).join_team(team_id)
    UserInterface(user_id_2).join_team(team_id)
    UserInterface(user_id_2).award_HP(2)
    game_id = db_session.query(User).get(user_id_1).team.game.id

    print(game_id)
    print(AdminInterface().get_scoreboard(game_id))
