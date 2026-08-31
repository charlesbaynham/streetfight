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
from backend import shot_escalation
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


def unreadable_reply(confidence=0.9):
    """Somebody was hit, but nothing they are wearing could be read."""
    return {
        "shot_hit_a_person": True,
        "reasoning": "too dark to make out any clothing",
        "confidence": confidence,
        "channels": {
            name: {"visible": False, "colour": "unknown", "confidence": 0.9}
            for name in SCHEME.channels.names
        },
    }


def partly_read_reply(hidden, confidence=0.9):
    """A confident hit with ``hidden`` read too shakily to count."""
    reply = confident_hit_reply(confidence=confidence)
    for name in hidden:
        reply["channels"][name]["confidence"] = 0.4
    return reply


def misread_hit_reply(garment, confidence=0.9):
    """A confident hit whose ``garment`` is read confidently but wrongly.

    One substitution with no erasures is the single misread [4,2,3] corrects,
    so the reading still identifies the slot's wearer.
    """
    reply = confident_hit_reply(confidence=confidence)
    channel = next(c for c in SCHEME.channels if c.name == garment)
    worn = reply["channels"][garment]["colour"]
    reply["channels"][garment]["colour"] = next(
        label for label in channel.labels if label != worn
    )
    return reply


def contradicted_hit_reply(confidence=0.9):
    """A confident hit whose reading fits nobody: two misreads is past what
    d = 3 can correct."""
    reply = confident_hit_reply(confidence=confidence)
    for garment in ("hat", "tshirt"):
        channel = next(c for c in SCHEME.channels if c.name == garment)
        worn = reply["channels"][garment]["colour"]
        reply["channels"][garment]["colour"] = next(
            label for label in channel.labels if label != worn
        )
    return reply


def escalation_payload(verdict, confidence=0.9, target_user_id=None):
    """The payload a completed escalation would have stored."""
    return {
        "verdict": verdict,
        "candidate": 1 if target_user_id else None,
        "target_user_id": str(target_user_id) if target_user_id else None,
        "target_name": "somebody",
        "confidence": confidence,
        "reasoning": "the reference photo settles it",
        "candidates": [],
        "requested_reference_photos": [],
        "transcript": [],
    }


def store_done_review(shot_id, raw):
    """Store the payload review_shot would have produced for reply ``raw``."""
    payload = shot_vision.classify(shot_vision.parse_result(raw), SCHEME).to_dict()
    AdminInterface().store_shot_ai_review(shot_id, ai_shot_review.STATE_DONE, payload)


def store_escalation(shot_id, state, payload=None):
    AdminInterface().store_shot_escalation(shot_id, state, payload)


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
    assert head.ai_escalation_state is None
    assert head.ai_escalation is None
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
async def test_an_unreadable_hit_is_never_auto_bystandered(
    mocker, db_session, shot_from_user_in_team
):
    # This used to be the auto-bystander case. Roadmap #11 retired it: nothing
    # auto-bystanders off the weak model any more, because "we could not read
    # any of it" is not evidence that the person is not playing.
    enqueue = mocker.patch("backend.shot_escalation.enqueue_escalation")
    enable_ai(game_of(shot_from_user_in_team))

    await ai_shot_review.review_shot(
        shot_from_user_in_team, FakeVisionClient(unreadable_reply(confidence=0.9))
    )

    shot = shot_row(db_session, shot_from_user_in_team)
    assert shot.checked is False
    enqueue.assert_called_once_with(shot_from_user_in_team)


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
    # High overall confidence, but only the armbands were read confidently: one
    # readable channel names nobody, so this goes up the ladder rather than
    # taking a life. With no escalation model configured it waits for the admin.
    enable_ai(game_of(shot_from_user_in_team))

    await ai_shot_review.review_shot(
        shot_from_user_in_team,
        FakeVisionClient(partly_read_reply(("tshirt", "trousers", "hat"))),
    )

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


# -- the escalation ladder ---------------------------------------------------


@pytest.fixture
def no_escalation_model(monkeypatch):
    """The default state of the world: escalation is not configured."""
    monkeypatch.delenv("OPENROUTER_ESCALATION_MODEL", raising=False)


def drain_with(db_session, shot_id, raw):
    """Store ``raw`` as the head's review and run the drain."""
    game_id = game_of(shot_id)
    enable_ai(game_id)
    store_done_review(shot_id, raw)
    shot_auto_actions.process_queue_head(game_id)
    return shot_row(db_session, shot_id)


def test_four_readable_channels_are_acted_on(
    db_session, shot_from_user_in_team, target_with_slot
):
    shot = drain_with(db_session, shot_from_user_in_team, confident_hit_reply())

    assert shot.result == "hit"
    assert shot.target_user_id == target_with_slot


def test_three_channels_with_the_armbands_are_acted_on(
    db_session, shot_from_user_in_team, target_with_slot
):
    # The armbands are the garment the game hands out, so player-ness is solid
    # and one erasure is well within the code: no second opinion needed.
    shot = drain_with(db_session, shot_from_user_in_team, partly_read_reply(("hat",)))

    assert shot.result == "hit"
    assert shot.target_user_id == target_with_slot


def test_three_channels_without_the_armbands_are_escalated(
    mocker, db_session, shot_from_user_in_team, target_with_slot
):
    # The missing channel is the player marker, so however well the other three
    # read, this one gets a second opinion rather than a life taken off it.
    enqueue = mocker.patch("backend.shot_escalation.enqueue_escalation")

    shot = drain_with(
        db_session, shot_from_user_in_team, partly_read_reply(("armbands",))
    )

    assert shot.checked is False
    enqueue.assert_called_once_with(shot_from_user_in_team)


def test_two_readable_channels_are_escalated(
    mocker, db_session, shot_from_user_in_team, target_with_slot
):
    enqueue = mocker.patch("backend.shot_escalation.enqueue_escalation")

    shot = drain_with(
        db_session, shot_from_user_in_team, partly_read_reply(("armbands", "hat"))
    )

    assert shot.checked is False
    enqueue.assert_called_once_with(shot_from_user_in_team)


def test_escalation_defaults_to_on(db_session, one_game):
    # Unlike its two siblings: it is a kill switch inside auto-actions, not a
    # third opt-in, so a game nobody has touched escalates as it always did.
    assert AdminInterface().is_ai_escalation_enabled(one_game) is True


def test_the_escalate_rung_waits_for_the_admin_when_escalation_is_off(
    mocker, db_session, shot_from_user_in_team, target_with_slot
):
    # Toggling it off is the same safety valve as configuring no escalation
    # model: nothing is asked of the stronger model and the head simply waits.
    enqueue = mocker.patch("backend.shot_escalation.enqueue_escalation")
    AdminInterface().set_ai_escalation_enabled(game_of(shot_from_user_in_team), False)

    shot = drain_with(
        db_session, shot_from_user_in_team, partly_read_reply(("armbands",))
    )

    assert shot.checked is False
    enqueue.assert_not_called()


def test_an_escalation_in_flight_blocks_the_queue_and_is_not_re_enqueued(
    mocker, db_session, shot_from_user_in_team
):
    enqueue = mocker.patch("backend.shot_escalation.enqueue_escalation")
    game_id = game_of(shot_from_user_in_team)
    enable_ai(game_id)
    store_done_review(shot_from_user_in_team, partly_read_reply(("armbands",)))
    store_escalation(shot_from_user_in_team, ai_shot_review.STATE_PENDING)

    shot_auto_actions.process_queue_head(game_id)

    assert shot_row(db_session, shot_from_user_in_team).checked is False
    enqueue.assert_not_called()


def test_an_errored_escalation_is_left_to_the_admin(
    mocker, db_session, shot_from_user_in_team
):
    enqueue = mocker.patch("backend.shot_escalation.enqueue_escalation")
    game_id = game_of(shot_from_user_in_team)
    enable_ai(game_id)
    store_done_review(shot_from_user_in_team, partly_read_reply(("armbands",)))
    store_escalation(shot_from_user_in_team, ai_shot_review.STATE_ERROR, "timed out")

    shot_auto_actions.process_queue_head(game_id)

    assert shot_row(db_session, shot_from_user_in_team).checked is False
    enqueue.assert_not_called()


def drain_with_escalation(db_session, shot_id, payload):
    game_id = game_of(shot_id)
    enable_ai(game_id)
    store_done_review(shot_id, partly_read_reply(("armbands",)))
    store_escalation(shot_id, ai_shot_review.STATE_DONE, payload)
    shot_auto_actions.process_queue_head(game_id)
    return shot_row(db_session, shot_id)


def test_a_confident_escalated_player_verdict_takes_the_hit(
    db_session, shot_from_user_in_team, target_with_slot
):
    shot = drain_with_escalation(
        db_session,
        shot_from_user_in_team,
        escalation_payload("player", confidence=0.9, target_user_id=target_with_slot),
    )

    assert shot.result == "hit"
    assert shot.target_user_id == target_with_slot
    assert UserInterface(target_with_slot).get_user_model().hit_points == 0


def test_an_unconfident_escalated_player_verdict_stays_queued(
    db_session, shot_from_user_in_team, target_with_slot
):
    # Naming a player takes a life off somebody, so it needs more than the
    # generic threshold: 0.7 clears CONFIDENT and still fails this.
    shot = drain_with_escalation(
        db_session,
        shot_from_user_in_team,
        escalation_payload("player", confidence=0.7, target_user_id=target_with_slot),
    )

    assert shot.checked is False
    assert UserInterface(target_with_slot).get_user_model().hit_points == 1


def test_an_escalated_player_verdict_on_a_dead_target_still_lands(
    db_session, shot_from_user_in_team, target_with_slot
):
    # Hitting somebody who is already out is a hit that does nothing. It must
    # not come back to the admin: there is nothing for them to decide.
    with UserInterface(target_with_slot) as ui:
        ui.hit(1)  # knocked out between the escalation and the drain

    shot = drain_with_escalation(
        db_session,
        shot_from_user_in_team,
        escalation_payload("player", confidence=0.9, target_user_id=target_with_slot),
    )

    assert shot.result == "hit"
    assert shot.target_user_id == target_with_slot
    assert UserInterface(target_with_slot).get_user_model().hit_points == 0


def test_an_escalated_miss_resolves_the_head(db_session, shot_from_user_in_team):
    shot = drain_with_escalation(
        db_session, shot_from_user_in_team, escalation_payload("miss")
    )

    assert shot.result == "miss"


def test_an_escalated_bystander_resolves_the_head(db_session, shot_from_user_in_team):
    shot = drain_with_escalation(
        db_session, shot_from_user_in_team, escalation_payload("bystander")
    )

    assert shot.result == "bystander"


def test_an_escalated_unsure_verdict_is_the_admins(
    db_session, shot_from_user_in_team, target_with_slot
):
    # The human rung: a player was hit but which one is undecidable, which is
    # exactly where every shot went before any of this existed.
    shot = drain_with_escalation(
        db_session, shot_from_user_in_team, escalation_payload("unsure")
    )

    assert shot.checked is False


def test_an_unconfident_escalated_miss_stays_queued(db_session, shot_from_user_in_team):
    shot = drain_with_escalation(
        db_session, shot_from_user_in_team, escalation_payload("miss", confidence=0.4)
    )

    assert shot.checked is False


def test_without_an_escalation_model_the_drain_stops_cleanly(
    no_escalation_model, db_session, shot_from_user_in_team, target_with_slot
):
    # The safety valve: nothing is enqueued, nothing is acted on, and the drain
    # terminates rather than spinning on a head it cannot resolve.
    assert shot_escalation.enqueue_escalation(shot_from_user_in_team) is None

    shot = drain_with(
        db_session, shot_from_user_in_team, partly_read_reply(("armbands",))
    )

    assert shot.checked is False
    assert shot.ai_escalation_state is None


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


def test_a_hit_on_a_dead_holder_is_acted_on_for_no_damage(
    db_session, shot_from_user_in_team, target_with_slot
):
    # The knocked-out player is still standing there to be photographed, so the
    # reading identifies them normally and the shot resolves against them.
    with UserInterface(target_with_slot) as ui:
        ui.hit(1)  # knocked out before the drain runs

    shot = drain_with_confident_hit(db_session, shot_from_user_in_team)

    assert shot.result == "hit"
    assert shot.target_user_id == target_with_slot
    assert UserInterface(target_with_slot).get_user_model().hit_points == 0


def test_a_misread_garment_is_still_a_confident_hit(
    db_session, shot_from_user_in_team, target_with_slot
):
    """A test-sized game -- one shooter, one target -- leaves the ranking a
    single candidate, and so no pair to measure the candidates' own separation
    over. The correction radius falls back to the code's own d there, or the
    misread d = 3 exists to correct would block the queue instead.
    """
    game_id = game_of(shot_from_user_in_team)
    enable_ai(game_id)
    store_done_review(shot_from_user_in_team, misread_hit_reply("hat"))

    shot_auto_actions.process_queue_head(game_id)

    shot = shot_row(db_session, shot_from_user_in_team)
    assert shot.result == "hit"
    assert shot.target_user_id == target_with_slot


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
    # ...which invalidated their queued shot mid-drain, fired after the kill...
    assert shot_row(db_session, victims_shot).result == "invalidated"
    assert UserInterface(target_with_slot).get_user_model().num_bullets == 1
    # ...and the re-reading drain carried on past the vanished entry
    assert shot_row(db_session, later_shot).result == "miss"


def test_a_shot_queued_behind_a_kill_resolves_against_the_dead_target(
    mocker, db_session, user_in_team, target_with_slot, test_image_string
):
    # The whole point of keeping the dead in the candidate set: the second
    # photograph of the same person still identifies them, so it resolves as a
    # hit that does nothing rather than matching nobody, burning an escalation
    # and blocking the queue for an admin who has nothing to decide.
    enqueue = mocker.patch("backend.shot_escalation.enqueue_escalation")
    ui = UserInterface(user_in_team)
    ui.award_ammo(3)
    ui.set_weapon_data(1, 6)
    kill_shot = ui.submit_shot(test_image_string)
    after_death = ui.submit_shot(test_image_string)
    later_shot = ui.submit_shot(test_image_string)
    set_shot_time(db_session, kill_shot, datetime(2026, 1, 1, 12, 0, 0))
    set_shot_time(db_session, after_death, datetime(2026, 1, 1, 12, 0, 5))
    set_shot_time(db_session, later_shot, datetime(2026, 1, 1, 12, 0, 10))

    game_id = game_of(kill_shot)
    enable_ai(game_id)
    store_done_review(kill_shot, confident_hit_reply())
    store_done_review(after_death, confident_hit_reply())
    store_done_review(later_shot, miss_reply(confidence=0.9))

    shot_auto_actions.process_queue_head(game_id)

    assert shot_row(db_session, kill_shot).result == "hit"
    assert UserInterface(target_with_slot).get_user_model().hit_points == 0

    second = shot_row(db_session, after_death)
    assert second.result == "hit"
    assert second.target_user_id == target_with_slot
    enqueue.assert_not_called()

    # ...and the queue carried on rather than stopping on the dead target
    assert shot_row(db_session, later_shot).result == "miss"


def test_racing_an_admin_is_swallowed_and_the_drain_terminates(
    mocker, db_session, shot_from_user_in_team
):
    game_id = game_of(shot_from_user_in_team)
    enable_ai(game_id)
    store_done_review(shot_from_user_in_team, miss_reply(confidence=0.9))

    real_decide = shot_auto_actions._decide

    def racing_decide(head, game_id_, resolve_everything=False):
        decision = real_decide(head, game_id_, resolve_everything)
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


# -- "resolve everything" (roadmap R8) ---------------------------------------
#
# The relaxed mode: a rung that would hand the head to the admin resolves it as
# best the evidence allows instead, because an appeal makes the error loud and
# recoverable. Every row of the table is here, in both modes.

OTHER_SLOT = 2


@pytest.fixture
def second_target_with_slot(db_session, team_factory, user_factory):
    """A third player wearing the *same* outfit as target_with_slot: the two
    tie, so the ranking is ambiguous and unconfident."""
    team_id = team_factory()
    user_id = user_factory()
    with UserInterface(user_id) as ui:
        ui.join_team(team_id)
    db_session.query(User).filter_by(id=user_id).update({"identity_slot": TARGET_SLOT})
    db_session.commit()
    return user_id


def force(game_id):
    """Both AI flags on, plus resolve-everything."""
    enable_ai(game_id)
    AdminInterface().set_ai_resolve_everything_enabled(game_id, True)


def forced_drain_with(db_session, shot_id, raw):
    game_id = game_of(shot_id)
    force(game_id)
    store_done_review(shot_id, raw)
    shot_auto_actions.process_queue_head(game_id)
    return shot_row(db_session, shot_id)


def forced_drain_with_escalation(db_session, shot_id, payload):
    game_id = game_of(shot_id)
    force(game_id)
    store_done_review(shot_id, partly_read_reply(("armbands",)))
    store_escalation(shot_id, ai_shot_review.STATE_DONE, payload)
    shot_auto_actions.process_queue_head(game_id)
    return shot_row(db_session, shot_id)


def test_resolve_everything_defaults_to_off(db_session, one_game):
    assert AdminInterface().is_ai_resolve_everything_enabled(one_game) is False


# ...nothing to resolve *from* is never forced


def test_forcing_does_not_resolve_a_head_with_no_review(
    db_session, shot_from_user_in_team
):
    game_id = game_of(shot_from_user_in_team)
    force(game_id)

    shot_auto_actions.process_queue_head(game_id)

    assert shot_row(db_session, shot_from_user_in_team).checked is False


@pytest.mark.parametrize(
    "state,payload",
    [
        (ai_shot_review.STATE_PENDING, None),
        (ai_shot_review.STATE_ERROR, "the model timed out"),
        (ai_shot_review.STATE_DONE, "not json at all"),
    ],
)
def test_forcing_does_not_resolve_an_unusable_review(
    db_session, shot_from_user_in_team, state, payload
):
    game_id = game_of(shot_from_user_in_team)
    force(game_id)
    AdminInterface().store_shot_ai_review(shot_from_user_in_team, state, payload)

    shot_auto_actions.process_queue_head(game_id)

    assert shot_row(db_session, shot_from_user_in_team).checked is False


# ...but an unconfident verdict is


def test_forcing_resolves_an_unconfident_miss(db_session, shot_from_user_in_team):
    shot = forced_drain_with(
        db_session, shot_from_user_in_team, miss_reply(confidence=0.3)
    )

    assert shot.result == "miss"


def test_forcing_resolves_a_stored_bystander_outcome(
    mocker, db_session, shot_from_user_in_team
):
    # Retired as an auto-action by #11 because "we could not read any of it" is
    # not evidence the person is not playing. Forced, it is still the best the
    # reading offers, and a bystander call takes nothing off anybody -- but
    # only once the stronger model is out of the picture, since a second
    # opinion that is actually coming beats a forced guess.
    enqueue = mocker.patch("backend.shot_escalation.enqueue_escalation")
    game_id = game_of(shot_from_user_in_team)
    force(game_id)
    AdminInterface().set_ai_escalation_enabled(game_id, False)
    AdminInterface().store_shot_ai_review(
        shot_from_user_in_team,
        ai_shot_review.STATE_DONE,
        {"outcome": shot_vision.HIT_BYSTANDER, "is_hit": False, "confidence": 0.4},
    )

    shot_auto_actions.process_queue_head(game_id)

    assert shot_row(db_session, shot_from_user_in_team).result == "bystander"
    enqueue.assert_not_called()


def test_forcing_leaves_an_unrecognised_outcome_alone(
    db_session, shot_from_user_in_team
):
    game_id = game_of(shot_from_user_in_team)
    force(game_id)
    AdminInterface().store_shot_ai_review(
        shot_from_user_in_team,
        ai_shot_review.STATE_DONE,
        {"outcome": "something_new", "confidence": 0.95},
    )

    shot_auto_actions.process_queue_head(game_id)

    assert shot_row(db_session, shot_from_user_in_team).checked is False


def test_forcing_resolves_an_unconfident_hit(
    db_session, shot_from_user_in_team, target_with_slot
):
    shot = forced_drain_with(
        db_session, shot_from_user_in_team, confident_hit_reply(confidence=0.3)
    )

    assert shot.result == "hit"
    assert shot.target_user_id == target_with_slot


def test_forcing_resolves_an_ambiguous_ranking(
    db_session, shot_from_user_in_team, target_with_slot, second_target_with_slot
):
    # Two players in the same outfit: the ranking ties, so unforced this is the
    # admin's. Forced, the most likely candidate is named - being wrong is what
    # the appeal is for.
    shot = drain_with(db_session, shot_from_user_in_team, confident_hit_reply())
    assert shot.checked is False

    shot = forced_drain_with(db_session, shot_from_user_in_team, confident_hit_reply())

    assert shot.result == "hit"
    assert shot.target_user_id in (target_with_slot, second_target_with_slot)


def test_forcing_never_names_somebody_the_reading_contradicts(
    db_session, shot_from_user_in_team, target_with_slot
):
    # The photograph reads as an outfit nobody here is wearing. Naming the only
    # candidate anyway would take a life off somebody the evidence argues
    # against, which is worse than asking the admin.
    shot = forced_drain_with(
        db_session, shot_from_user_in_team, confident_hit_reply(slot=OTHER_SLOT)
    )

    assert shot.checked is False


def test_forcing_never_resolves_a_hit_that_ranks_nobody(
    db_session, shot_from_user_in_team
):
    # Nobody in the game wears a slot, so there is nobody to notify - and so
    # nobody who could appeal the verdict this would invent.
    shot = forced_drain_with(db_session, shot_from_user_in_team, confident_hit_reply())

    assert shot.checked is False


# ...and the escalation ladder relaxes the same way


def test_forcing_still_escalates_first(
    mocker, db_session, shot_from_user_in_team, target_with_slot
):
    # A second opinion that is actually coming beats a forced guess
    enqueue = mocker.patch("backend.shot_escalation.enqueue_escalation")

    shot = forced_drain_with(
        db_session, shot_from_user_in_team, partly_read_reply(("armbands",))
    )

    assert shot.checked is False
    enqueue.assert_called_once_with(shot_from_user_in_team)


def test_forcing_still_waits_for_an_escalation_in_flight(
    db_session, shot_from_user_in_team, target_with_slot
):
    game_id = game_of(shot_from_user_in_team)
    force(game_id)
    store_done_review(shot_from_user_in_team, partly_read_reply(("armbands",)))
    store_escalation(shot_from_user_in_team, ai_shot_review.STATE_PENDING)

    shot_auto_actions.process_queue_head(game_id)

    assert shot_row(db_session, shot_from_user_in_team).checked is False


def test_forcing_leaves_an_errored_escalation_to_the_admin(
    db_session, shot_from_user_in_team, target_with_slot
):
    game_id = game_of(shot_from_user_in_team)
    force(game_id)
    store_done_review(shot_from_user_in_team, partly_read_reply(("armbands",)))
    store_escalation(shot_from_user_in_team, ai_shot_review.STATE_ERROR, "timed out")

    shot_auto_actions.process_queue_head(game_id)

    assert shot_row(db_session, shot_from_user_in_team).checked is False


def test_forcing_acts_on_an_unconfident_escalated_player_verdict(
    db_session, shot_from_user_in_team, target_with_slot
):
    shot = forced_drain_with_escalation(
        db_session,
        shot_from_user_in_team,
        escalation_payload("player", confidence=0.4, target_user_id=target_with_slot),
    )

    assert shot.result == "hit"
    assert shot.target_user_id == target_with_slot


@pytest.mark.parametrize("verdict", ["miss", "bystander"])
def test_forcing_acts_on_an_unconfident_escalated_miss_or_bystander(
    db_session, shot_from_user_in_team, target_with_slot, verdict
):
    shot = forced_drain_with_escalation(
        db_session, shot_from_user_in_team, escalation_payload(verdict, confidence=0.2)
    )

    assert shot.result == verdict


def test_forcing_falls_back_to_the_weak_ranking_when_the_escalation_is_unsure(
    db_session, shot_from_user_in_team, target_with_slot
):
    # The stronger model has nothing to add, so the weak reading's ranking is
    # the best there is - and it is still a verdict somebody can appeal.
    shot = forced_drain_with_escalation(
        db_session, shot_from_user_in_team, escalation_payload("unsure")
    )

    assert shot.result == "hit"
    assert shot.target_user_id == target_with_slot


def test_forcing_falls_back_when_escalation_is_switched_off(
    mocker, db_session, shot_from_user_in_team, target_with_slot
):
    enqueue = mocker.patch("backend.shot_escalation.enqueue_escalation")
    AdminInterface().set_ai_escalation_enabled(game_of(shot_from_user_in_team), False)

    shot = forced_drain_with(
        db_session, shot_from_user_in_team, partly_read_reply(("armbands",))
    )

    assert shot.result == "hit"
    assert shot.target_user_id == target_with_slot
    enqueue.assert_not_called()


def test_forcing_falls_back_when_no_escalation_model_is_configured(
    no_escalation_model, db_session, shot_from_user_in_team, target_with_slot
):
    shot = forced_drain_with(
        db_session, shot_from_user_in_team, partly_read_reply(("armbands",))
    )

    assert shot.result == "hit"
    assert shot.target_user_id == target_with_slot


def test_the_fallback_still_refuses_a_head_that_ranks_nobody(
    no_escalation_model, db_session, shot_from_user_in_team
):
    shot = forced_drain_with(
        db_session, shot_from_user_in_team, partly_read_reply(("armbands",))
    )

    assert shot.checked is False


def test_resolve_everything_endpoint_flips_the_game_flag(admin_api_client, one_game):
    response = admin_api_client.post(
        f"/api/admin_set_ai_resolve_everything?game_id={one_game}&enabled=true"
    )

    assert response.status_code == 200
    assert AdminInterface().is_ai_resolve_everything_enabled(one_game) is True

    response = admin_api_client.post(
        f"/api/admin_set_ai_resolve_everything?game_id={one_game}&enabled=false"
    )

    assert response.is_success
    assert AdminInterface().is_ai_resolve_everything_enabled(one_game) is False


def test_enabling_resolve_everything_drains_a_head_that_was_waiting(
    db_session, admin_api_client, shot_from_user_in_team
):
    game_id = game_of(shot_from_user_in_team)
    enable_ai(game_id)
    store_done_review(shot_from_user_in_team, miss_reply(confidence=0.3))
    shot_auto_actions.process_queue_head(game_id)
    assert shot_row(db_session, shot_from_user_in_team).checked is False

    response = admin_api_client.post(
        f"/api/admin_set_ai_resolve_everything?game_id={game_id}&enabled=true"
    )

    assert response.is_success
    assert shot_row(db_session, shot_from_user_in_team).result == "miss"


def test_escalation_endpoint_flips_the_game_flag(admin_api_client, one_game):
    response = admin_api_client.post(
        f"/api/admin_set_ai_escalation?game_id={one_game}&enabled=false"
    )

    assert response.status_code == 200
    assert AdminInterface().is_ai_escalation_enabled(one_game) is False

    response = admin_api_client.post(
        f"/api/admin_set_ai_escalation?game_id={one_game}&enabled=true"
    )

    assert response.is_success
    assert AdminInterface().is_ai_escalation_enabled(one_game) is True


def test_enabling_escalation_escalates_a_head_that_was_waiting(
    mocker, db_session, admin_api_client, shot_from_user_in_team
):
    enqueue = mocker.patch("backend.shot_escalation.enqueue_escalation")
    game_id = game_of(shot_from_user_in_team)
    enable_ai(game_id)
    AdminInterface().set_ai_escalation_enabled(game_id, False)
    store_done_review(shot_from_user_in_team, partly_read_reply(("armbands",)))
    shot_auto_actions.process_queue_head(game_id)
    enqueue.assert_not_called()

    response = admin_api_client.post(
        f"/api/admin_set_ai_escalation?game_id={game_id}&enabled=true"
    )

    assert response.is_success
    enqueue.assert_called_once_with(shot_from_user_in_team)


# -- nothing reaches the admin without the stronger model first --------------
#
# The escalation toggle means "the stronger model does what the admin would
# have done": every uncertainty goes to it, and only its own hand-back reaches
# a human. These all patch enqueue_escalation, which stands in for a configured
# escalation client.


@pytest.fixture
def crowd(db_session, team_factory, user_factory, target_with_slot):
    """Extra candidates, so the candidate set has pairs of its own."""
    team_id = team_factory()
    for slot in (13, 21, 27):
        uid = user_factory()
        with UserInterface(uid) as ui:
            ui.join_team(team_id)
        db_session.query(User).filter_by(id=uid).update({"identity_slot": slot})
        db_session.commit()
    return target_with_slot


@pytest.fixture
def twin(db_session, team_factory, user_factory, target_with_slot):
    """A second player wearing exactly what the target wears -- an unbreakable
    tie for any reading."""
    team_id = team_factory()
    uid = user_factory()
    with UserInterface(uid) as ui:
        ui.join_team(team_id)
    db_session.query(User).filter_by(id=uid).update({"identity_slot": TARGET_SLOT})
    db_session.commit()
    return uid


def drain_escalating(mocker, db_session, shot_id, raw):
    """Drain with an escalation client available; returns (shot, enqueue mock)."""
    enqueue = mocker.patch("backend.shot_escalation.enqueue_escalation")
    return drain_with(db_session, shot_id, raw), enqueue


def test_a_contradicted_reading_is_escalated(
    mocker, db_session, shot_from_user_in_team, crowd
):
    """The hardest case there is -- a fully-read photo that fits nobody -- used
    to be classified as easy and handed straight to the admin."""
    shot, enqueue = drain_escalating(
        mocker, db_session, shot_from_user_in_team, contradicted_hit_reply()
    )

    assert shot.checked is False
    enqueue.assert_called_once_with(shot_from_user_in_team)


def test_a_tied_ranking_is_escalated(
    mocker, db_session, shot_from_user_in_team, target_with_slot, twin
):
    shot, enqueue = drain_escalating(
        mocker, db_session, shot_from_user_in_team, confident_hit_reply()
    )

    assert shot.checked is False
    enqueue.assert_called_once_with(shot_from_user_in_team)


def test_an_unconfident_hit_is_escalated(
    mocker, db_session, shot_from_user_in_team, target_with_slot
):
    shot, enqueue = drain_escalating(
        mocker, db_session, shot_from_user_in_team, confident_hit_reply(confidence=0.3)
    )

    assert shot.checked is False
    enqueue.assert_called_once_with(shot_from_user_in_team)


def test_an_unconfident_miss_is_escalated(mocker, db_session, shot_from_user_in_team):
    shot, enqueue = drain_escalating(
        mocker, db_session, shot_from_user_in_team, miss_reply(confidence=0.3)
    )

    assert shot.checked is False
    enqueue.assert_called_once_with(shot_from_user_in_team)


def test_a_legacy_bystander_review_is_escalated(
    mocker, db_session, shot_from_user_in_team
):
    enqueue = mocker.patch("backend.shot_escalation.enqueue_escalation")
    game_id = game_of(shot_from_user_in_team)
    enable_ai(game_id)
    AdminInterface().store_shot_ai_review(
        shot_from_user_in_team,
        ai_shot_review.STATE_DONE,
        {"outcome": shot_vision.HIT_BYSTANDER, "confidence": 0.9},
    )

    shot_auto_actions.process_queue_head(game_id)

    assert shot_row(db_session, shot_from_user_in_team).checked is False
    enqueue.assert_called_once_with(shot_from_user_in_team)


def test_the_admin_only_sees_what_the_stronger_model_handed_back(
    mocker, db_session, shot_from_user_in_team, crowd
):
    """The one door to the admin: the stronger model looked and said unsure."""
    enqueue = mocker.patch("backend.shot_escalation.enqueue_escalation")
    game_id = game_of(shot_from_user_in_team)
    enable_ai(game_id)
    store_done_review(shot_from_user_in_team, contradicted_hit_reply())
    store_escalation(
        shot_from_user_in_team,
        ai_shot_review.STATE_DONE,
        escalation_payload(shot_escalation.VERDICT_UNSURE),
    )

    shot_auto_actions.process_queue_head(game_id)

    shot = shot_row(db_session, shot_from_user_in_team)
    assert shot.checked is False
    # Crucially not escalated a second time: the ladder must terminate.
    enqueue.assert_not_called()


def test_an_escalated_verdict_resolves_a_reading_the_first_model_botched(
    mocker, db_session, shot_from_user_in_team, crowd, target_with_slot
):
    """The whole point: the stronger model's answer overrides a first reading
    that contradicted everybody."""
    game_id = game_of(shot_from_user_in_team)
    enable_ai(game_id)
    store_done_review(shot_from_user_in_team, contradicted_hit_reply())
    store_escalation(
        shot_from_user_in_team,
        ai_shot_review.STATE_DONE,
        escalation_payload(
            shot_escalation.VERDICT_PLAYER, target_user_id=target_with_slot
        ),
    )

    shot_auto_actions.process_queue_head(game_id)

    shot = shot_row(db_session, shot_from_user_in_team)
    assert shot.result == "hit"
    assert shot.target_user_id == target_with_slot


def test_with_escalation_off_an_uncertain_head_still_waits_for_the_admin(
    mocker, db_session, shot_from_user_in_team, crowd
):
    """The kill switch still works: no stronger model means the admin, exactly
    as before any of this existed."""
    enqueue = mocker.patch("backend.shot_escalation.enqueue_escalation")
    game_id = game_of(shot_from_user_in_team)
    enable_ai(game_id)
    AdminInterface().set_ai_escalation_enabled(game_id, False)
    store_done_review(shot_from_user_in_team, contradicted_hit_reply())

    shot_auto_actions.process_queue_head(game_id)

    assert shot_row(db_session, shot_from_user_in_team).checked is False
    enqueue.assert_not_called()
