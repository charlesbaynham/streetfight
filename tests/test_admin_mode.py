from pathlib import Path

import pytest
from fastapi.exceptions import HTTPException

from backend.admin_interface import AdminInterface
from backend.model import Shot
from backend.user_interface import UserInterface

test_image_string = Path(__file__, "../sample_base64_image.txt").resolve().read_text()


def test_making_item():
    assert isinstance(AdminInterface().make_new_item("ammo", {"num": 123}), str)


def test_using_made_item(user_in_team):
    encoded_item = AdminInterface().make_new_item("ammo", {"num": 123})

    UserInterface(user_in_team).collect_item(encoded_item)


def test_making_item_fail():
    with pytest.raises(HTTPException):
        AdminInterface().make_new_item("whatever", {"num": 123})


def test_dead_users_cannot_kill_with_old_shots(
    api_client, db_session, user_factory, team_factory
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
    shot_a = UserInterface(user_a).submit_shot(test_image_string)

    # User B shoots user A (though they should be dead)
    shot_b = UserInterface(user_b).submit_shot(test_image_string)

    # The admin checks user A and awards the shot to them
    response = api_client.post(
        f"/api/admin_shot_hit_user?shot_id={shot_a}&target_user_id={user_b}"
    )
    assert response.ok

    # Now, shot B should not be in the queue
    shot_b_model: Shot = db_session.query(Shot).get(shot_b)
    assert shot_b_model.checked
    # And user B should be dead
    assert UserInterface(user_b).get_user_model().hit_points == 0
    # And user A should be alive
    assert UserInterface(user_a).get_user_model().hit_points == 1
    # And user B should have got a bullet refund
    assert UserInterface(user_b).get_user_model().num_bullets == 1000
    # But user A shouldn't have
    assert UserInterface(user_a).get_user_model().num_bullets == 999
