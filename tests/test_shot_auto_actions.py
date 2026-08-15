"""Tests for the head-of-queue auto-action drain (backend.shot_auto_actions).

Nothing here touches the network: reviews arrive either through review_shot
with a FakeVisionClient, or as stored payloads followed by a direct
process_queue_head call.
"""

from datetime import datetime
from uuid import uuid4 as get_uuid

import pytest
from fastapi import HTTPException

from backend import ai_shot_review
from backend import shot_auto_actions
from backend import shot_vision
from backend.admin_interface import AdminInterface
from backend.identity.config import default_scheme
from backend.model import Shot
from backend.model import Team
from backend.model import User
from backend.user_interface import UserInterface
from backend.vision_client import FakeVisionClient
from backend.vision_client import VisionError

SCHEME = default_scheme()

TARGET_SLOT = 7


@pytest.fixture(autouse=True)
def mock_asyncio_tasks(mocker):
    mocker.patch("backend.asyncio_triggers.schedule_update_event")


# -- helpers ----------------------------------------------------------------


def game_of(shot_id):
    return AdminInterface().get_shot_model(shot_id).game_id


def confident_hit_reply(slot=TARGET_SLOT, confidence=0.9, channel_confidence=0.9):
    appearance = SCHEME.appearance_of_slot(slot)
    return {
        "shot_hit_a_person": True,
        "reasoning": "clear view of the target",
        "confidence": confidence,
        "channels": {
            name: {"visible": True, "colour": colour, "confidence": channel_confidence}
            for name, colour in appearance.items()
        },
    }


def miss_reply(confidence=0.9):
    return {
        "shot_hit_a_person": False,
        "reasoning": "empty pavement",
        "confidence": confidence,
    }


def bystander_reply(confidence=0.9):
    return {
        "shot_hit_a_person": True,
        "reasoning": "a passer-by in plain clothes",
        "confidence": confidence,
        "channels": {
            name: {"visible": False, "colour": "unknown", "confidence": 0.9}
            for name in SCHEME.channels.names
        },
    }


def store_done_review(shot_id, raw):
    """Store the payload review_shot would have produced for reply ``raw``."""
    payload = shot_vision.classify(shot_vision.parse_result(raw), SCHEME).to_dict()
    AdminInterface().store_shot_ai_review(shot_id, ai_shot_review.STATE_DONE, payload)


def shot_row(db_session, shot_id) -> Shot:
    db_session.expire_all()
    return db_session.query(Shot).filter_by(id=shot_id).one()


def set_shot_time(db_session, shot_id, when: datetime):
    """Pin a shot's timestamp: time_created only has 1s resolution, so tests
    that need a definite queue order set it explicitly."""
    db_session.query(Shot).filter_by(id=shot_id).update({"time_created": when})
    db_session.commit()


def enable_ai(game_id):
    """Both flags on: recognition annotates the queue and auto-actions act."""
    AdminInterface().set_ai_shot_review_enabled(game_id, True)
    AdminInterface().set_ai_auto_actions_enabled(game_id, True)


@pytest.fixture
def target_with_slot(db_session, team_factory, user_factory):
    """A second user, on their own team in the same game, wearing TARGET_SLOT."""
    team_id = team_factory()
    user_id = user_factory()
    with UserInterface(user_id) as ui:
        ui.join_team(team_id)
    db_session.query(User).filter_by(id=user_id).update({"identity_slot": TARGET_SLOT})
    db_session.commit()
    return user_id


# -- the AdminInterface helpers ---------------------------------------------


def test_get_shot_game_id(db_session, shot_from_user_in_team):
    assert AdminInterface().get_shot_game_id(shot_from_user_in_team) == game_of(
        shot_from_user_in_team
    )


def test_get_shot_game_id_404s_on_an_unknown_shot(db_session, one_game):
    with pytest.raises(HTTPException) as excinfo:
        AdminInterface().get_shot_game_id(get_uuid())

    assert excinfo.value.status_code == 404


def test_get_queue_head_returns_the_light_fields(
    db_session, shot_from_user_in_team, user_in_team
):
    head = AdminInterface().get_queue_head(game_of(shot_from_user_in_team))

    assert head.id == shot_from_user_in_team
    assert head.user_id == user_in_team
    assert head.ai_review_state is None
    assert head.ai_review is None
    assert not hasattr(head, "image_base64")


def test_get_queue_head_of_an_empty_queue_is_none(db_session, one_game):
    assert AdminInterface().get_queue_head(one_game) is None


# -- confident verdicts resolve the head ------------------------------------


@pytest.mark.asyncio
async def test_a_confident_miss_resolves_the_head(db_session, shot_from_user_in_team):
    enable_ai(game_of(shot_from_user_in_team))

    await ai_shot_review.review_shot(
        shot_from_user_in_team, FakeVisionClient(miss_reply(confidence=0.9))
    )

    shot = shot_row(db_session, shot_from_user_in_team)
    assert shot.checked is True
    assert shot.result == "miss"


@pytest.mark.asyncio
async def test_a_confident_bystander_hit_is_marked_missed(
    db_session, shot_from_user_in_team
):
    enable_ai(game_of(shot_from_user_in_team))

    await ai_shot_review.review_shot(
        shot_from_user_in_team, FakeVisionClient(bystander_reply(confidence=0.9))
    )

    shot = shot_row(db_session, shot_from_user_in_team)
    assert shot.checked is True
    assert shot.result == "miss"


@pytest.mark.asyncio
async def test_a_confident_hit_hits_the_identified_player(
    db_session, shot_from_user_in_team, target_with_slot
):
    enable_ai(game_of(shot_from_user_in_team))

    await ai_shot_review.review_shot(
        shot_from_user_in_team, FakeVisionClient(confident_hit_reply())
    )

    shot = shot_row(db_session, shot_from_user_in_team)
    assert shot.checked is True
    assert shot.result == "hit"
    assert shot.target_user_id == target_with_slot
    assert UserInterface(target_with_slot).get_user_model().hit_points == 0


# -- ambiguity and low confidence stay with the admin -----------------------


@pytest.mark.asyncio
async def test_an_unconfident_miss_stays_queued(db_session, shot_from_user_in_team):
    enable_ai(game_of(shot_from_user_in_team))

    await ai_shot_review.review_shot(
        shot_from_user_in_team, FakeVisionClient(miss_reply(confidence=0.4))
    )

    shot = shot_row(db_session, shot_from_user_in_team)
    assert shot.ai_review_state == ai_shot_review.STATE_DONE
    assert shot.checked is False


def test_a_legacy_review_without_confidence_never_fires(
    db_session, shot_from_user_in_team
):
    # Reviews stored before the confidence field existed parse as 0.0.
    game_id = game_of(shot_from_user_in_team)
    enable_ai(game_id)
    AdminInterface().store_shot_ai_review(
        shot_from_user_in_team,
        ai_shot_review.STATE_DONE,
        {"outcome": "miss", "is_hit": False},
    )

    shot_auto_actions.process_queue_head(game_id)

    assert shot_row(db_session, shot_from_user_in_team).checked is False


@pytest.mark.asyncio
async def test_a_hit_with_shaky_channels_stays_queued(
    db_session, shot_from_user_in_team, target_with_slot
):
    # High overall confidence, but only the armbands were read confidently:
    # the outcome is hit_player, yet one readable channel identifies nobody.
    reply = confident_hit_reply(confidence=0.9)
    for name in ("tshirt", "trousers", "hat"):
        reply["channels"][name]["confidence"] = 0.5
    enable_ai(game_of(shot_from_user_in_team))

    await ai_shot_review.review_shot(shot_from_user_in_team, FakeVisionClient(reply))

    shot = shot_row(db_session, shot_from_user_in_team)
    assert shot.ai_review_state == ai_shot_review.STATE_DONE
    assert shot.checked is False
    assert UserInterface(target_with_slot).get_user_model().hit_points == 1


@pytest.mark.asyncio
async def test_an_errored_review_blocks_the_drain(db_session, shot_from_user_in_team):
    enable_ai(game_of(shot_from_user_in_team))

    await ai_shot_review.review_shot(
        shot_from_user_in_team, FakeVisionClient(error=VisionError("nope"))
    )

    shot = shot_row(db_session, shot_from_user_in_team)
    assert shot.ai_review_state == ai_shot_review.STATE_ERROR
    assert shot.checked is False


# -- mapping the identified slot to a target --------------------------------


def drain_with_confident_hit(db_session, shot_id):
    game_id = game_of(shot_id)
    enable_ai(game_id)
    store_done_review(shot_id, confident_hit_reply())
    shot_auto_actions.process_queue_head(game_id)
    return shot_row(db_session, shot_id)


def test_a_hit_with_no_slot_holder_stays_queued(db_session, shot_from_user_in_team):
    shot = drain_with_confident_hit(db_session, shot_from_user_in_team)

    assert shot.checked is False


def test_a_hit_on_a_dead_holder_stays_queued(
    db_session, shot_from_user_in_team, target_with_slot
):
    with UserInterface(target_with_slot) as ui:
        ui.hit(1)  # knocked out before the drain runs

    shot = drain_with_confident_hit(db_session, shot_from_user_in_team)

    assert shot.checked is False


def test_a_hit_identifying_the_shooter_stays_queued(
    db_session, shot_from_user_in_team, user_in_team
):
    db_session.query(User).filter_by(id=user_in_team).update(
        {"identity_slot": TARGET_SLOT}
    )
    db_session.commit()

    shot = drain_with_confident_hit(db_session, shot_from_user_in_team)

    assert shot.checked is False


def test_the_same_slot_in_another_game_does_not_confuse_the_mapping(
    db_session, shot_from_user_in_team, target_with_slot, game_factory, user_factory
):
    # A user in a *different* game wearing the same slot must be invisible here.
    other_game = game_factory()
    other_team = Team(name="other", game_id=other_game)
    db_session.add(other_team)
    db_session.commit()
    other_user = user_factory()
    with UserInterface(other_user) as ui:
        ui.join_team(other_team.id)
    db_session.query(User).filter_by(id=other_user).update(
        {"identity_slot": TARGET_SLOT}
    )
    db_session.commit()

    shot = drain_with_confident_hit(db_session, shot_from_user_in_team)

    assert shot.checked is True
    assert shot.target_user_id == target_with_slot
    assert UserInterface(other_user).get_user_model().hit_points == 1


# -- strict queue order ------------------------------------------------------


def test_an_ambiguous_head_blocks_and_an_admin_resolution_cascades(
    db_session, admin_api_client, user_in_team, test_image_string
):
    ui = UserInterface(user_in_team)
    ui.award_ammo(2)
    ui.set_weapon_data(1, 6)
    older = ui.submit_shot(test_image_string)
    newer = ui.submit_shot(test_image_string)
    set_shot_time(db_session, older, datetime(2026, 1, 1, 12, 0, 0))
    set_shot_time(db_session, newer, datetime(2026, 1, 1, 12, 0, 5))

    game_id = game_of(older)
    enable_ai(game_id)
    store_done_review(older, miss_reply(confidence=0.3))  # ambiguous head
    store_done_review(newer, miss_reply(confidence=0.9))  # confident behind it

    shot_auto_actions.process_queue_head(game_id)

    assert shot_row(db_session, older).checked is False
    assert shot_row(db_session, newer).checked is False  # blocked by the head

    # The admin resolves the head; the endpoint's drain cascades to the rest
    response = admin_api_client.post(f"/api/admin_mark_shot_missed?shot_id={older}")
    assert response.is_success

    assert shot_row(db_session, older).result == "miss"
    newer_shot = shot_row(db_session, newer)
    assert newer_shot.checked is True
    assert newer_shot.result == "miss"


def test_a_knockout_mid_drain_refunds_the_victims_shot_and_continues(
    db_session, user_in_team, target_with_slot, test_image_string
):
    shooter_ui = UserInterface(user_in_team)
    shooter_ui.award_ammo(2)
    shooter_ui.set_weapon_data(1, 6)
    victim_ui = UserInterface(target_with_slot)
    victim_ui.award_ammo(1)
    victim_ui.set_weapon_data(1, 6)

    kill_shot = shooter_ui.submit_shot(test_image_string)
    victims_shot = victim_ui.submit_shot(test_image_string)
    later_shot = shooter_ui.submit_shot(test_image_string)
    set_shot_time(db_session, kill_shot, datetime(2026, 1, 1, 12, 0, 0))
    set_shot_time(db_session, victims_shot, datetime(2026, 1, 1, 12, 0, 5))
    set_shot_time(db_session, later_shot, datetime(2026, 1, 1, 12, 0, 10))

    game_id = game_of(kill_shot)
    enable_ai(game_id)
    store_done_review(kill_shot, confident_hit_reply())
    store_done_review(later_shot, miss_reply(confidence=0.9))
    # The victim's queued shot has no review at all

    shot_auto_actions.process_queue_head(game_id)

    # The hit knocked the victim out...
    assert shot_row(db_session, kill_shot).result == "hit"
    assert UserInterface(target_with_slot).get_user_model().hit_points == 0
    # ...which refunded their queued shot mid-drain...
    assert shot_row(db_session, victims_shot).result == "refunded"
    assert UserInterface(target_with_slot).get_user_model().num_bullets == 1
    # ...and the re-reading drain carried on past the vanished entry
    assert shot_row(db_session, later_shot).result == "miss"


def test_racing_an_admin_is_swallowed_and_the_drain_terminates(
    mocker, db_session, shot_from_user_in_team
):
    game_id = game_of(shot_from_user_in_team)
    enable_ai(game_id)
    store_done_review(shot_from_user_in_team, miss_reply(confidence=0.9))

    real_decide = shot_auto_actions._decide

    def racing_decide(head, game_id_):
        decision = real_decide(head, game_id_)
        # An admin resolves the same shot between the decision and the action
        AdminInterface().mark_shot_missed(head.id)
        return decision

    mocker.patch.object(shot_auto_actions, "_decide", racing_decide)

    shot_auto_actions.process_queue_head(game_id)  # must not raise

    assert shot_row(db_session, shot_from_user_in_team).result == "miss"


# -- the auto-actions toggle gates every action ------------------------------


def test_the_drain_is_a_no_op_when_auto_actions_are_off(
    db_session, shot_from_user_in_team
):
    game_id = game_of(shot_from_user_in_team)
    store_done_review(shot_from_user_in_team, miss_reply(confidence=0.9))

    shot_auto_actions.process_queue_head(game_id)

    assert shot_row(db_session, shot_from_user_in_team).checked is False


@pytest.mark.asyncio
async def test_annotate_only_mode_reviews_but_never_acts(
    db_session, shot_from_user_in_team
):
    # Recognition on, auto-actions off: every photo is reviewed but the shot
    # stays in the queue for the admin to resolve by hand.
    game_id = game_of(shot_from_user_in_team)
    AdminInterface().set_ai_shot_review_enabled(game_id, True)

    await ai_shot_review.review_shot(
        shot_from_user_in_team, FakeVisionClient(miss_reply(confidence=0.9))
    )

    shot = shot_row(db_session, shot_from_user_in_team)
    assert shot.ai_review_state == ai_shot_review.STATE_DONE
    assert shot.checked is False


def test_auto_actions_act_on_a_done_head_without_the_review_toggle(
    db_session, shot_from_user_in_team
):
    # The flags are independent: a review stored while recognition is off
    # (e.g. a manual admin_review_shot run) is still acted on.
    game_id = game_of(shot_from_user_in_team)
    AdminInterface().set_ai_auto_actions_enabled(game_id, True)
    store_done_review(shot_from_user_in_team, miss_reply(confidence=0.9))

    shot_auto_actions.process_queue_head(game_id)

    shot = shot_row(db_session, shot_from_user_in_team)
    assert shot.checked is True
    assert shot.result == "miss"


@pytest.mark.asyncio
async def test_a_manual_rerun_with_both_toggles_off_annotates_but_does_not_act(
    db_session, shot_from_user_in_team
):
    # admin_review_shot works whatever the toggles say, but the annotation it
    # stores must not act on the queue unless the game has opted in.
    await ai_shot_review.review_shot(
        shot_from_user_in_team, FakeVisionClient(miss_reply(confidence=0.9))
    )

    shot = shot_row(db_session, shot_from_user_in_team)
    assert shot.ai_review_state == ai_shot_review.STATE_DONE
    assert shot.checked is False


# -- the admin endpoint ------------------------------------------------------


def test_auto_actions_default_to_off(db_session, one_game):
    assert AdminInterface().is_ai_auto_actions_enabled(one_game) is False


def test_auto_actions_endpoint_flips_the_game_flag(admin_api_client, one_game):
    response = admin_api_client.post(
        f"/api/admin_set_ai_auto_actions?game_id={one_game}&enabled=true"
    )

    assert response.status_code == 200
    assert AdminInterface().is_ai_auto_actions_enabled(one_game) is True

    response = admin_api_client.post(
        f"/api/admin_set_ai_auto_actions?game_id={one_game}&enabled=false"
    )

    assert response.is_success
    assert AdminInterface().is_ai_auto_actions_enabled(one_game) is False


def test_enabling_auto_actions_drains_a_waiting_confident_head(
    db_session, admin_api_client, shot_from_user_in_team
):
    game_id = game_of(shot_from_user_in_team)
    store_done_review(shot_from_user_in_team, miss_reply(confidence=0.9))

    response = admin_api_client.post(
        f"/api/admin_set_ai_auto_actions?game_id={game_id}&enabled=true"
    )

    assert response.is_success
    shot = shot_row(db_session, shot_from_user_in_team)
    assert shot.checked is True
    assert shot.result == "miss"


def test_auto_actions_endpoint_needs_admin_auth(api_client, one_game):
    response = api_client.post(
        f"/api/admin_set_ai_auto_actions?game_id={one_game}&enabled=true"
    )

    assert response.status_code == 403
