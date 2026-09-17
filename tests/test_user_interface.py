from pathlib import Path
from uuid import uuid4 as uuid

import pytest
from fastapi.exceptions import HTTPException

from backend import shot_escalation
from backend import shot_vision
from backend.admin_interface import AdminInterface
from backend.identity.config import PROVIDED_CHANNEL
from backend.identity.config import TEAM_CHANNEL
from backend.identity.config import default_scheme
from backend.identity.config import hex_for
from backend.model import User
from backend.user_interface import UserInterface

from .shared_fixtures import NO_FIRE_DELAY

SCHEME = default_scheme()

# Two slots whose canonical outfits share no colour in any channel, so a
# reading of one is never a near miss for the other.
SLOT_A = 7
SLOT_B = 12


# Mock "schedule_update_event" since we don't have an asyncio loop
@pytest.fixture(autouse=True)
def mock_asyncio_tasks(mocker):
    mocker.patch("backend.asyncio_triggers.schedule_update_event")


@pytest.fixture
def test_image():
    return Path(__file__, "../sample_base64_image.txt").resolve().read_text()


def test_can_join_new_team(user_factory):
    user_id = user_factory()
    UserInterface(user_id=user_id).join_team(uuid())


def test_can_use_userinterface_as_contextmanager(user_factory):
    user_id = user_factory()

    with UserInterface(user_id=user_id) as ui:
        ui.join_team(uuid())


def test_can_reuse_userinterface_as_contextmanager(user_factory):
    user_id = user_factory()

    user_interface = UserInterface(user_id=user_id)

    with user_interface as ui:
        ui.join_team(uuid())

    with user_interface as ui:
        ui.get_user_model()


def test_can_join_existing_team(user_factory, team_factory):
    user_id = user_factory()

    UserInterface(user_id=user_id).join_team(team_factory())


def test_cannot_join_new_team_if_multiple_games(game_factory, user_factory):
    game_factory()
    game_factory()

    user_id = user_factory()

    with pytest.raises(HTTPException):
        UserInterface(user_id=user_id).join_team(uuid())


def test_user_shots_respect_ammo(db_session, team_factory, user_factory, test_image):
    team_id = team_factory()
    user_id = user_factory()

    UserInterface(user_id).join_team(team_id)

    # Bullets, and a weapon with no fire delay: this test is about running out
    # of ammo, and the server-side cooldown (M1.1) would otherwise refuse
    # shots two and three for a reason it is not about.
    user = db_session.query(User).filter_by(id=user_id).first()
    user.num_bullets = 3
    user.shot_timeout = NO_FIRE_DELAY
    db_session.commit()

    for _ in range(3):
        UserInterface(user_id).submit_shot(test_image)

    # ...and the refusal has to be the ammo one, now that there is a second
    # thing in submit_shot that answers with a 403.
    with pytest.raises(HTTPException) as refusal:
        UserInterface(user_id).submit_shot(test_image)
    assert refusal.value.detail == "User has no ammo"


def test_user_cannot_shoot_when_dead(
    db_session, team_factory, user_factory, test_image
):
    team_id = team_factory()
    user_id = user_factory()

    UserInterface(user_id).join_team(team_id)

    # Give the user 3 bullets
    user = db_session.query(User).filter_by(id=user_id).first()
    user.num_bullets = 3
    db_session.commit()

    UserInterface(user_id).submit_shot(test_image)

    # Kill them
    UserInterface(user_id).hit()

    with pytest.raises(HTTPException):
        UserInterface(user_id).submit_shot(test_image)


def test_can_give_health(user_in_team):
    UserInterface(user_in_team).award_HP()

    assert UserInterface(user_in_team).get_user_model().hit_points == 2


def test_can_give_multiple_health(user_in_team):
    UserInterface(user_in_team).award_HP(num=10)

    assert UserInterface(user_in_team).get_user_model().hit_points == 11


def test_can_give_ammo(user_in_team):
    UserInterface(user_in_team).award_ammo()

    assert UserInterface(user_in_team).get_user_model().num_bullets == 1


def test_can_give_multiple_ammo(user_in_team):
    UserInterface(user_in_team).award_ammo(num=10)

    assert UserInterface(user_in_team).get_user_model().num_bullets == 10


def test_user_in_team(user_in_team):
    assert UserInterface(user_in_team).get_user_model().team_id is not None


def test_a_player_is_not_a_team_leader_until_an_admin_says_so(user_in_team):
    """The leader flag (M7) rides on the user model, which is what user_info
    serves, so the waiting page can show the checklist without a second call."""
    assert UserInterface(user_in_team).get_user_model().is_team_leader is False

    AdminInterface().set_team_leader(user_in_team, True)
    assert UserInterface(user_in_team).get_user_model().is_team_leader is True

    AdminInterface().set_team_leader(user_in_team, False)
    assert UserInterface(user_in_team).get_user_model().is_team_leader is False


def test_a_signed_up_player_with_no_team_can_be_made_a_leader(user_factory):
    """Teams are scanned in at the door (R15), so a leader may be nominated
    before the app knows which team they lead."""
    user_id = user_factory()

    AdminInterface().set_team_leader(user_id, True)

    assert UserInterface(user_id).get_user_model().is_team_leader is True


def test_outfit_wardrobe_is_none_before_an_outfit_is_picked(user_in_team):
    model = UserInterface(user_in_team).get_user_model()
    assert model.outfit_wardrobe is None
    assert model.outfit_provided is None


def test_outfit_wardrobe_reports_the_players_own_garments(user_in_team, db_session):
    db_session.query(User).filter_by(id=user_in_team).update({"identity_slot": SLOT_A})
    db_session.commit()

    wardrobe = UserInterface(user_in_team).get_user_model().outfit_wardrobe

    canonical = SCHEME.appearance_of_slot(SLOT_A)
    assert wardrobe == {
        name: {"colour": colour, "hex": hex_for(name, colour)}
        for name, colour in canonical.items()
        if name not in (TEAM_CHANNEL, PROVIDED_CHANNEL)
    }
    # The hat and armband are handed out at the door, not chosen by the
    # player, so they're excluded even though the slot names a colour for
    # them too - they ride along separately (see below).
    assert TEAM_CHANNEL not in wardrobe
    assert PROVIDED_CHANNEL not in wardrobe


def test_outfit_provided_reports_the_kit_handed_over_at_the_door(
    user_in_team, db_session
):
    """The front page has to tell a waiting player which hat and armband are
    coming: since R15 they are allocated per player rather than pinned to the
    team, so nothing else on that screen says."""
    db_session.query(User).filter_by(id=user_in_team).update({"identity_slot": SLOT_A})
    db_session.commit()

    provided = UserInterface(user_in_team).get_user_model().outfit_provided

    canonical = SCHEME.appearance_of_slot(SLOT_A)
    assert provided == {
        name: {"colour": colour, "hex": hex_for(name, colour)}
        for name, colour in canonical.items()
        if name in (TEAM_CHANNEL, PROVIDED_CHANNEL)
    }


# -- who the AI thinks the shooter shot -------------------------------------


def review_of(slot):
    """The stored reading of a photograph of somebody wearing ``slot``."""
    return {
        "is_hit": True,
        "outcome": shot_vision.HIT_PLAYER,
        "channels": {
            name: {"visible": True, "colour": colour, "confidence": 0.9}
            for name, colour in SCHEME.appearance_of_slot(slot).items()
        },
    }


@pytest.fixture
def player_wearing(db_session, team_factory, user_factory):
    """Another player in the same game, in the outfit of a given slot."""

    def factory(slot):
        user_id = user_factory()
        UserInterface(user_id).join_team(team_factory())
        db_session.query(User).filter_by(id=user_id).update({"identity_slot": slot})
        db_session.commit()
        return user_id

    return factory


def name_of(user_id):
    return AdminInterface().get_user_model(user_id).name


def own_shot(user_id):
    (shot,) = UserInterface(user_id).get_own_shots()
    return shot


def test_the_shot_history_names_a_confidently_identified_target(
    user_in_team, shot_from_user_in_team, player_wearing
):
    target = player_wearing(SLOT_A)
    player_wearing(SLOT_B)
    AdminInterface().store_shot_ai_review(
        shot_from_user_in_team, "done", review_of(SLOT_A)
    )

    shot = own_shot(user_in_team)
    assert shot["ai_suggestion"] == "hit"
    assert shot["ai_target_name"] == name_of(target)


def test_the_shot_history_names_nobody_when_two_players_match_equally(
    user_in_team, shot_from_user_in_team, player_wearing
):
    """Two players in the same outfit is exactly the case an admin has to
    settle -- naming either of them would be a coin toss shown as a fact."""
    player_wearing(SLOT_A)
    player_wearing(SLOT_A)
    AdminInterface().store_shot_ai_review(
        shot_from_user_in_team, "done", review_of(SLOT_A)
    )

    shot = own_shot(user_in_team)
    assert shot["ai_suggestion"] == "hit"
    assert shot["ai_target_name"] is None


def test_the_shot_history_prefers_the_escalated_target(
    user_in_team, shot_from_user_in_team, player_wearing
):
    """The escalation exists because the cheap reading was not good enough to
    act on, so its answer wins over the cheap reading's own."""
    player_wearing(SLOT_A)
    AdminInterface().store_shot_ai_review(
        shot_from_user_in_team, "done", review_of(SLOT_A)
    )
    AdminInterface().store_shot_escalation(
        shot_from_user_in_team,
        shot_escalation.STATE_DONE,
        {"verdict": "player", "confidence": 0.9, "target_name": "somebody else"},
    )

    assert own_shot(user_in_team)["ai_target_name"] == "somebody else"


def test_the_shot_history_drops_the_guess_once_an_admin_has_ruled(
    user_in_team, shot_from_user_in_team, player_wearing
):
    player_wearing(SLOT_A)
    AdminInterface().store_shot_ai_review(
        shot_from_user_in_team, "done", review_of(SLOT_A)
    )
    AdminInterface().mark_shot_missed(shot_from_user_in_team)

    assert own_shot(user_in_team)["ai_target_name"] is None
