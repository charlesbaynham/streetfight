"""Tests for the AI shot review worker and its admin surface.

Nothing here touches the network: every test injects a FakeVisionClient.
"""

import json

import pytest

from backend import ai_shot_review
from backend import shot_vision
from backend.admin_interface import AdminInterface
from backend.identity.config import default_scheme
from backend.model import Shot
from backend.user_interface import UserInterface
from backend.vision_client import FakeVisionClient
from backend.vision_client import VisionError

SCHEME = default_scheme()


@pytest.fixture(autouse=True)
def mock_asyncio_tasks(mocker):
    mocker.patch("backend.asyncio_triggers.schedule_update_event")


@pytest.fixture
def no_api_key(monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)


def hit_reply(slot=7):
    appearance = SCHEME.appearance_of_slot(slot)
    return {
        "shot_hit_a_person": True,
        "reasoning": "clear view of the target",
        "channels": {
            name: {"visible": True, "colour": colour, "confidence": 0.9}
            for name, colour in appearance.items()
        },
    }


def game_of(shot_id):
    return AdminInterface().get_shot_model(shot_id).game_id


# -- the worker -------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_successful_review_is_stored(db_session, shot_from_user_in_team):
    client = FakeVisionClient(reply=hit_reply())

    await ai_shot_review.review_shot(shot_from_user_in_team, client)

    stored = AdminInterface().get_shot_ai_review(shot_from_user_in_team)
    assert stored["state"] == ai_shot_review.STATE_DONE
    assert stored["review"]["outcome"] == shot_vision.HIT_PLAYER
    assert stored["review"]["is_hit"] is True
    assert stored["review"]["channels"]["tshirt"]["colour"] == "black"


@pytest.mark.asyncio
async def test_the_image_sent_is_prepared_not_raw(db_session, shot_from_user_in_team):
    client = FakeVisionClient(reply=hit_reply())

    await ai_shot_review.review_shot(shot_from_user_in_team, client)

    sent = client.images_sent[0]
    original = AdminInterface().get_shot_model(shot_from_user_in_team).image_base64
    assert sent.startswith("data:image/jpeg;base64,")
    assert sent != original


@pytest.mark.asyncio
async def test_the_zoom_is_cut_from_the_original_not_the_downsized_image(
    mocker, db_session, shot_from_user_in_team
):
    # The whole point of the zoom is to spend camera resolution that
    # prepare_for_vision has already thrown away, so it must start from the raw
    # photo. Zooming the prepared image would just magnify blur.
    spy = mocker.patch(
        "backend.ai_shot_review.zoom_image", return_value="data:image/jpeg;base64,Z"
    )
    client = FakeVisionClient(reply=[{"request_zoom": True}, hit_reply()])

    await ai_shot_review.review_shot(shot_from_user_in_team, client)

    original = AdminInterface().get_shot_model(shot_from_user_in_team).image_base64
    assert spy.call_args[0][0] == original
    assert client.images_sent[-1] == "data:image/jpeg;base64,Z"
    assert (
        AdminInterface().get_shot_ai_review(shot_from_user_in_team)["state"]
        == ai_shot_review.STATE_DONE
    )


@pytest.mark.asyncio
async def test_no_zoom_is_produced_when_the_model_does_not_ask(
    mocker, db_session, shot_from_user_in_team
):
    spy = mocker.patch("backend.ai_shot_review.zoom_image")

    await ai_shot_review.review_shot(
        shot_from_user_in_team, FakeVisionClient(hit_reply())
    )

    spy.assert_not_called()


@pytest.mark.asyncio
async def test_a_failing_client_is_recorded_as_an_error(
    db_session, shot_from_user_in_team
):
    client = FakeVisionClient(error=VisionError("the model fell over"))

    await ai_shot_review.review_shot(shot_from_user_in_team, client)

    stored = AdminInterface().get_shot_ai_review(shot_from_user_in_team)
    assert stored["state"] == ai_shot_review.STATE_ERROR
    assert "fell over" in stored["review"]["error"]


@pytest.mark.asyncio
async def test_a_failing_review_leaves_the_shot_alone(
    db_session, shot_from_user_in_team
):
    client = FakeVisionClient(error=VisionError("nope"))

    await ai_shot_review.review_shot(shot_from_user_in_team, client)

    shot = db_session.query(Shot).filter_by(id=shot_from_user_in_team).one()
    assert shot.checked is False
    assert shot.target_user_id is None


@pytest.mark.asyncio
async def test_a_garbled_reply_is_recorded_as_an_error(
    db_session, shot_from_user_in_team
):
    client = FakeVisionClient(reply={"nonsense": True})

    await ai_shot_review.review_shot(shot_from_user_in_team, client)

    assert (
        AdminInterface().get_shot_ai_review(shot_from_user_in_team)["state"]
        == ai_shot_review.STATE_ERROR
    )


@pytest.mark.asyncio
async def test_a_review_notifies_the_admin_stream_and_the_shooter(
    mocker, db_session, shot_from_user_in_team, user_in_team
):
    mocked = mocker.patch("backend.ai_shot_review.trigger_update_event")

    await ai_shot_review.review_shot(
        shot_from_user_in_team, FakeVisionClient(hit_reply())
    )

    triggered = [call.args for call in mocked.call_args_list]
    assert ("user", user_in_team) in triggered
    assert mocked.call_args_list[-1][0][0] == "shots"


@pytest.mark.asyncio
async def test_a_failing_auto_action_drain_does_not_break_the_review_contract(
    mocker, db_session, shot_from_user_in_team
):
    # review_shot never raises, and the review must be stored even if the
    # drain bolted onto the end of it blows up.
    mocker.patch(
        "backend.ai_shot_review.shot_auto_actions.process_queue_head",
        side_effect=RuntimeError("boom"),
    )

    await ai_shot_review.review_shot(
        shot_from_user_in_team, FakeVisionClient(hit_reply())
    )

    stored = AdminInterface().get_shot_ai_review(shot_from_user_in_team)
    assert stored["state"] == ai_shot_review.STATE_DONE


@pytest.mark.asyncio
async def test_a_completed_review_runs_the_auto_action_drain(
    mocker, db_session, shot_from_user_in_team
):
    spy = mocker.patch("backend.ai_shot_review.shot_auto_actions.process_queue_head")

    await ai_shot_review.review_shot(
        shot_from_user_in_team, FakeVisionClient(hit_reply())
    )

    spy.assert_called_once_with(game_of(shot_from_user_in_team))


def test_without_an_api_key_nothing_is_queued(
    no_api_key, db_session, shot_from_user_in_team
):
    assert ai_shot_review.enqueue_review(shot_from_user_in_team) is None

    assert AdminInterface().get_shot_ai_review(shot_from_user_in_team)["state"] is None


# -- the toggle -------------------------------------------------------------


def test_the_toggle_defaults_to_off(db_session, one_game):
    assert AdminInterface().is_ai_shot_review_enabled(one_game) is False


def test_enabling_the_toggle_returns_the_backlog(db_session, shot_from_user_in_team):
    game_id = game_of(shot_from_user_in_team)

    backlog = AdminInterface().set_ai_shot_review_enabled(game_id, True)

    assert backlog == [shot_from_user_in_team]
    assert AdminInterface().is_ai_shot_review_enabled(game_id) is True


def test_checked_shots_are_not_in_the_backlog(db_session, shot_from_user_in_team):
    game_id = game_of(shot_from_user_in_team)
    AdminInterface().mark_shot_missed(shot_from_user_in_team)

    assert AdminInterface().set_ai_shot_review_enabled(game_id, True) == []


def test_already_reviewed_shots_are_not_in_the_backlog(
    db_session, shot_from_user_in_team
):
    """The toggle gets flipped during a game; that must not re-review the queue."""
    game_id = game_of(shot_from_user_in_team)
    AdminInterface().store_shot_ai_review(
        shot_from_user_in_team, ai_shot_review.STATE_DONE, {"outcome": "miss"}
    )

    assert AdminInterface().set_ai_shot_review_enabled(game_id, True) == []


def test_a_shot_whose_review_errored_is_retried(db_session, shot_from_user_in_team):
    game_id = game_of(shot_from_user_in_team)
    AdminInterface().store_shot_ai_review(
        shot_from_user_in_team, ai_shot_review.STATE_ERROR, "connection reset"
    )

    assert AdminInterface().set_ai_shot_review_enabled(game_id, True) == [
        shot_from_user_in_team
    ]


def test_a_shot_mid_review_is_not_queued_twice(db_session, shot_from_user_in_team):
    game_id = game_of(shot_from_user_in_team)
    AdminInterface().store_shot_ai_review(
        shot_from_user_in_team, ai_shot_review.STATE_PENDING
    )

    assert AdminInterface().set_ai_shot_review_enabled(game_id, True) == []


def test_unreviewed_shots_are_still_in_the_backlog(
    db_session, user_in_team, test_image_string, shot_from_user_in_team
):
    """The reviewed shot is skipped, the new one that arrived is not."""
    game_id = game_of(shot_from_user_in_team)
    AdminInterface().store_shot_ai_review(
        shot_from_user_in_team, ai_shot_review.STATE_DONE, {"outcome": "miss"}
    )
    ui = UserInterface(user_in_team)
    ui.award_ammo(1)
    new_shot = ui.submit_shot(test_image_string)

    assert AdminInterface().set_ai_shot_review_enabled(game_id, True) == [new_shot]


def test_disabling_the_toggle_returns_no_backlog(db_session, shot_from_user_in_team):
    game_id = game_of(shot_from_user_in_team)
    AdminInterface().set_ai_shot_review_enabled(game_id, True)

    assert AdminInterface().set_ai_shot_review_enabled(game_id, False) == []
    assert AdminInterface().is_ai_shot_review_enabled(game_id) is False


# -- submit_shot now hands back an id ---------------------------------------


def test_submit_shot_returns_the_new_shot_id(
    db_session, user_in_team, test_image_string
):
    ui = UserInterface(user_in_team)
    ui.award_ammo(1)

    shot_id = ui.submit_shot(test_image_string)

    assert shot_id is not None
    assert db_session.query(Shot).filter_by(id=shot_id).one().checked is False


# -- the admin API ----------------------------------------------------------


def test_review_endpoint_reports_nothing_before_a_review(
    admin_api_client, shot_from_user_in_team
):
    response = admin_api_client.get(
        f"/api/admin_get_shot_ai_review?shot_id={shot_from_user_in_team}"
    )

    assert response.status_code == 200
    assert response.json() == {"state": None, "review": None}


def test_review_endpoint_returns_a_stored_review(
    admin_api_client, shot_from_user_in_team
):
    AdminInterface().store_shot_ai_review(
        shot_from_user_in_team, ai_shot_review.STATE_DONE, {"outcome": "miss"}
    )

    response = admin_api_client.get(
        f"/api/admin_get_shot_ai_review?shot_id={shot_from_user_in_team}"
    )

    assert response.json() == {"state": "done", "review": {"outcome": "miss"}}


def test_review_endpoint_needs_admin_auth(api_client, shot_from_user_in_team):
    response = api_client.get(
        f"/api/admin_get_shot_ai_review?shot_id={shot_from_user_in_team}"
    )

    assert response.status_code == 403


def test_toggle_endpoint_flips_the_game_flag(admin_api_client, shot_from_user_in_team):
    game_id = game_of(shot_from_user_in_team)

    response = admin_api_client.post(
        f"/api/admin_set_ai_shot_review?game_id={game_id}&enabled=true"
    )

    assert response.status_code == 200
    assert response.json()["backlog"] == 1
    assert AdminInterface().is_ai_shot_review_enabled(game_id) is True


def test_toggle_endpoint_shows_up_in_the_game_model(
    admin_api_client, shot_from_user_in_team
):
    game_id = game_of(shot_from_user_in_team)
    admin_api_client.post(
        f"/api/admin_set_ai_shot_review?game_id={game_id}&enabled=true"
    )

    games = admin_api_client.get("/api/admin_list_games").json()

    assert any(g["ai_shot_review_enabled"] for g in games if g["id"] == str(game_id))


def test_manual_review_without_a_key_is_a_clear_error(
    no_api_key, admin_api_client, shot_from_user_in_team
):
    response = admin_api_client.post(
        f"/api/admin_review_shot?shot_id={shot_from_user_in_team}"
    )

    assert response.status_code == 503
    assert "OPENROUTER_API_KEY" in response.json()["detail"]


# -- storage ----------------------------------------------------------------


def test_an_error_message_survives_being_stored_as_non_json(
    db_session, shot_from_user_in_team
):
    AdminInterface().store_shot_ai_review(
        shot_from_user_in_team, ai_shot_review.STATE_ERROR, "connection reset"
    )

    stored = AdminInterface().get_shot_ai_review(shot_from_user_in_team)

    assert stored["review"] == {"error": "connection reset"}


def test_a_review_is_stored_as_json_text(db_session, shot_from_user_in_team):
    AdminInterface().store_shot_ai_review(
        shot_from_user_in_team, ai_shot_review.STATE_DONE, {"outcome": "miss"}
    )

    shot = db_session.query(Shot).filter_by(id=shot_from_user_in_team).one()

    assert json.loads(shot.ai_review) == {"outcome": "miss"}
