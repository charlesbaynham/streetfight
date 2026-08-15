import pytest
from fastapi.exceptions import HTTPException

from backend.admin_interface import AdminInterface
from backend.user_interface import UserInterface


def test_submit_shot(user_in_team, test_image_string):
    ui = UserInterface(user_in_team)
    ui.award_ammo(1)
    ui.submit_shot(test_image_string)


def test_submit_shot_no_ammo(user_in_team, test_image_string):
    ui = UserInterface(user_in_team)
    with pytest.raises(HTTPException):
        ui.submit_shot(test_image_string)


def test_trigger_update_event_on_shot(mocker, user_in_team, test_image_string):
    mocked = mocker.patch("backend.asyncio_triggers.trigger_update_event")
    ui = UserInterface(user_in_team)
    ui.award_ammo(1)
    mocked.reset_mock()
    UserInterface(user_in_team).submit_shot(test_image_string)
    assert mocked.call_count == 1
    assert mocked.call_args_list[0][0][0] == "user"


# -- the user-facing shot history -------------------------------------------


def submit_a_shot(user_id, test_image_string):
    ui = UserInterface(user_id)
    ui.award_ammo(1)
    ui.set_weapon_data(1, 6)
    return ui.submit_shot(test_image_string)


def test_hit_recorded_in_shot_history(two_users_in_different_teams, test_image_string):
    shooter, target = two_users_in_different_teams
    shot_id = submit_a_shot(shooter, test_image_string)

    AdminInterface().hit_user(shot_id, target)

    (shot,) = UserInterface(shooter).get_own_shots()
    assert shot["id"] == shot_id
    assert shot["checked"] is True
    assert shot["result"] == "hit"
    assert shot["target_name"] == UserInterface(target).get_user_model().name


def test_miss_recorded_in_shot_history(user_in_team, test_image_string):
    shot_id = submit_a_shot(user_in_team, test_image_string)

    AdminInterface().mark_shot_missed(shot_id)

    (shot,) = UserInterface(user_in_team).get_own_shots()
    assert shot["checked"] is True
    assert shot["result"] == "miss"
    assert shot["target_name"] is None


def test_refund_recorded_in_shot_history(user_in_team, test_image_string):
    shot_id = submit_a_shot(user_in_team, test_image_string)

    AdminInterface().refund_shot(shot_id)

    (shot,) = UserInterface(user_in_team).get_own_shots()
    assert shot["result"] == "refunded"
    assert UserInterface(user_in_team).get_user_model().num_bullets == 1


def test_knockout_marks_targets_pending_shots_refunded(
    two_users_in_different_teams, test_image_string
):
    shooter, target = two_users_in_different_teams

    # The target has a shot of their own waiting in the queue when they get
    # knocked out - it comes back to them as a refund
    target_shot = submit_a_shot(target, test_image_string)
    shooter_shot = submit_a_shot(shooter, test_image_string)

    AdminInterface().hit_user(shooter_shot, target)

    (shot,) = UserInterface(target).get_own_shots()
    assert shot["id"] == target_shot
    assert shot["result"] == "refunded"


def test_hit_does_not_tell_shooter_they_missed(
    two_users_in_different_teams, test_image_string
):
    shooter, target = two_users_in_different_teams
    shot_id = submit_a_shot(shooter, test_image_string)

    AdminInterface().hit_user(shot_id, target)

    messages = UserInterface(shooter).get_messages(10, private=True)
    assert not any("missed" in message.lower() for _, message in messages)


def test_adjudication_nudges_the_shooter(mocker, user_in_team, test_image_string):
    shot_id = submit_a_shot(user_in_team, test_image_string)

    mocked = mocker.patch("backend.admin_interface.trigger_update_event")
    AdminInterface().mark_shot_missed(shot_id)

    assert ("user", user_in_team) in [c.args for c in mocked.call_args_list]


def test_shot_history_only_shares_the_ai_bottom_line(
    user_in_team, shot_from_user_in_team
):
    AdminInterface().store_shot_ai_review(
        shot_from_user_in_team,
        "done",
        {"is_hit": True, "outcome": "hit_player", "reasoning": "top secret"},
    )

    (shot,) = UserInterface(user_in_team).get_own_shots()
    assert shot["ai_review_state"] == "done"
    assert shot["ai_suggestion"] == "hit"
    # No reasoning, no clothing readings, no image - just the summary fields
    assert set(shot.keys()) == {
        "id",
        "time_created",
        "checked",
        "result",
        "target_name",
        "ai_review_state",
        "ai_suggestion",
    }


def test_shot_history_ai_suggestion_can_be_miss(user_in_team, shot_from_user_in_team):
    AdminInterface().store_shot_ai_review(
        shot_from_user_in_team, "done", {"is_hit": False, "outcome": "miss"}
    )

    (shot,) = UserInterface(user_in_team).get_own_shots()
    assert shot["ai_suggestion"] == "miss"


def test_user_shots_endpoint_excludes_images(
    api_client, api_user_id, one_team, test_image_string
):
    UserInterface(api_user_id).join_team(one_team)
    shot_id = submit_a_shot(api_user_id, test_image_string)

    response = api_client.get("/api/user_shots")
    assert response.is_success

    (shot,) = response.json()
    assert shot["id"] == str(shot_id)
    assert "image_base64" not in shot


def test_user_shot_image_endpoint(api_client, api_user_id, one_team, test_image_string):
    UserInterface(api_user_id).join_team(one_team)
    shot_id = submit_a_shot(api_user_id, test_image_string)

    response = api_client.get(f"/api/user_shot_image?shot_id={shot_id}")
    assert response.is_success
    assert response.json()["image_base64"] == test_image_string


def test_user_cannot_fetch_someone_elses_shot_image(api_client, shot_from_user_in_team):
    # The api_client session is a different user from the one who fired
    response = api_client.get(f"/api/user_shot_image?shot_id={shot_from_user_in_team}")
    assert response.status_code == 404
