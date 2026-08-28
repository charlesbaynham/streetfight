import json
from uuid import UUID

import pytest
from fastapi.exceptions import HTTPException

from backend.admin_interface import AdminInterface
from backend.ticker_message_dispatcher import TickerMessageType
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


def test_bystander_recorded_in_shot_history(user_in_team, test_image_string):
    shot_id = submit_a_shot(user_in_team, test_image_string)

    AdminInterface().mark_shot_bystander(shot_id)

    (shot,) = UserInterface(user_in_team).get_own_shots()
    assert shot["checked"] is True
    assert shot["result"] == "bystander"
    assert shot["target_name"] is None
    # A bystander costs the ammo, exactly like a miss
    assert UserInterface(user_in_team).get_user_model().num_bullets == 0


def test_bystander_tells_the_shooter(user_in_team, test_image_string):
    shot_id = submit_a_shot(user_in_team, test_image_string)

    AdminInterface().mark_shot_bystander(shot_id)

    messages = UserInterface(user_in_team).get_messages(10, private=True)
    assert any("bystander" in message.lower() for _, message in messages)


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


# -- hitting somebody who is already knocked out -----------------------------


def ticker_types(mocked):
    return [call.args[0] for call in mocked.call_args_list]


def test_the_death_blow_announces_the_knockout_once(
    mocker, two_users_in_different_teams, test_image_string
):
    shooter, target = two_users_in_different_teams
    shot_id = submit_a_shot(shooter, test_image_string)
    mocked = mocker.patch("backend.ticker_message_dispatcher.send_ticker_message")

    AdminInterface().hit_user(shot_id, target)

    assert ticker_types(mocked) == [
        TickerMessageType.HIT_AND_KNOCKOUT,
        TickerMessageType.USER_GOT_KNOCKED_OUT,
    ]


def test_hitting_an_already_dead_player_is_a_plain_hit(
    mocker, two_users_in_different_teams, test_image_string
):
    """A shot queued behind the one that killed its target did hit them; it
    just changes nothing. Announcing a second knockout would credit the kill to
    whoever happened to be next in the queue."""
    shooter, target = two_users_in_different_teams
    death_blow = submit_a_shot(shooter, test_image_string)
    afterwards = submit_a_shot(shooter, test_image_string)
    AdminInterface().hit_user(death_blow, target)

    mocked = mocker.patch("backend.ticker_message_dispatcher.send_ticker_message")
    clearing = mocker.spy(UserInterface, "clear_unchecked_shots")

    AdminInterface().hit_user(afterwards, target)

    assert ticker_types(mocked) == [
        TickerMessageType.HIT_AND_DAMAGE,
        TickerMessageType.USER_GOT_HIT,
    ]
    clearing.assert_not_called()
    assert UserInterface(target).get_user_model().hit_points == 0
    results = {
        shot["id"]: shot["result"] for shot in UserInterface(shooter).get_own_shots()
    }
    assert results[afterwards] == "hit"


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
        "ai_target_name",
    }


def test_shot_history_ai_suggestion_can_be_miss(user_in_team, shot_from_user_in_team):
    AdminInterface().store_shot_ai_review(
        shot_from_user_in_team, "done", {"is_hit": False, "outcome": "miss"}
    )

    (shot,) = UserInterface(user_in_team).get_own_shots()
    assert shot["ai_suggestion"] == "miss"


def test_shot_history_ai_suggestion_can_be_bystander(
    user_in_team, shot_from_user_in_team
):
    AdminInterface().store_shot_ai_review(
        shot_from_user_in_team, "done", {"is_hit": False, "outcome": "hit_bystander"}
    )

    (shot,) = UserInterface(user_in_team).get_own_shots()
    assert shot["ai_suggestion"] == "bystander"


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


# -- telemetry captured with a shot (docs/roadmap.md R5) ---------------------
#
# Nothing reads either of these fields yet, on purpose: they are recorded now
# because they cannot be recovered afterwards.


def test_shot_records_the_heading_it_was_fired_on(user_in_team, test_image_string):
    ui = UserInterface(user_in_team)
    ui.award_ammo(1)
    shot_id = ui.submit_shot(test_image_string, heading=137.5)

    assert AdminInterface().get_shot_model(shot_id).heading == 137.5


def test_shot_without_a_heading_is_still_a_shot(user_in_team, test_image_string):
    ui = UserInterface(user_in_team)
    ui.award_ammo(1)
    shot_id = ui.submit_shot(test_image_string)

    assert AdminInterface().get_shot_model(shot_id).heading is None


def test_submit_shot_endpoint_passes_the_heading_through(
    api_client, api_user_id, one_team, test_image_string
):
    UserInterface(api_user_id).join_team(one_team)
    UserInterface(api_user_id).award_ammo(1)

    response = api_client.post(
        "/api/submit_shot", json={"photo": test_image_string, "heading": 42.0}
    )
    assert response.is_success

    shot_id = UUID(response.json())
    assert AdminInterface().get_shot_model(shot_id).heading == 42.0


def test_submit_shot_endpoint_tolerates_a_missing_heading(
    api_client, api_user_id, one_team, test_image_string
):
    UserInterface(api_user_id).join_team(one_team)
    UserInterface(api_user_id).award_ammo(1)

    response = api_client.post("/api/submit_shot", json={"photo": test_image_string})
    assert response.is_success

    shot_id = UUID(response.json())
    assert AdminInterface().get_shot_model(shot_id).heading is None


def test_location_accuracy_is_stored_and_reported(user_in_team):
    ui = UserInterface(user_in_team)
    ui.set_location(51.5, -0.1, accuracy=12.5)

    assert ui.get_user_model().location_accuracy == 12.5

    (location,) = [
        entry
        for entry in AdminInterface().get_locations()
        if entry["user_id"] == user_in_team
    ]
    assert location["accuracy"] == 12.5


def test_location_accuracy_is_optional(user_in_team):
    ui = UserInterface(user_in_team)
    ui.set_location(51.5, -0.1)

    (location,) = [
        entry
        for entry in AdminInterface().get_locations()
        if entry["user_id"] == user_in_team
    ]
    assert location["accuracy"] is None


def test_set_location_endpoint_passes_the_accuracy_through(
    api_client, api_user_id, one_team
):
    UserInterface(api_user_id).join_team(one_team)

    response = api_client.post(
        "/api/set_location",
        params={"latitude": 51.5, "longitude": -0.1, "accuracy": 8.25},
    )
    assert response.is_success

    assert UserInterface(api_user_id).get_user_model().location_accuracy == 8.25


def test_shot_location_context_carries_the_shooters_fix(
    user_in_team, test_image_string
):
    """The context serialised into every shot is what a future model reads
    back, so the accuracy has to survive the round trip into it."""
    ui = UserInterface(user_in_team)
    ui.set_location(51.5, -0.1, accuracy=9.0)
    ui.award_ammo(1)
    shot_id = ui.submit_shot(test_image_string, heading=90.0)

    shot = AdminInterface().get_shot_model(shot_id)
    context = json.loads(shot.location_context)

    (shooter,) = [entry for entry in context if entry["user_id"] == str(user_in_team)]
    assert shooter["latitude"] == 51.5
    assert shooter["longitude"] == -0.1
    assert shooter["accuracy"] == 9.0
