"""Tests for the door kit check (backend.reference_photos) and its admin API.

Nothing here touches the network: every test either injects a FakeVisionClient
or unsets the API key so no review is ever queued.
"""

import json
from uuid import uuid4 as get_uuid

import pytest

from backend import reference_photos
from backend.admin_interface import AdminInterface
from backend.identity.config import default_scheme
from backend.model import Shot
from backend.model import TickerEntry
from backend.model import User
from backend.user_interface import UserInterface
from backend.vision_client import FakeVisionClient
from backend.vision_client import VisionError

SCHEME = default_scheme()

# Two slots whose canonical outfits share no colour in any channel, so a
# reading of one can never be mistaken for the other.
SLOT_A = 7
SLOT_B = 12


@pytest.fixture(autouse=True)
def mock_asyncio_tasks(mocker):
    mocker.patch("backend.asyncio_triggers.schedule_update_event")


@pytest.fixture
def no_api_key(monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)


def outfit_reply(slot, confidence=0.9):
    """The reply a model gives when it can see slot ``slot``'s outfit clearly."""
    appearance = SCHEME.appearance_of_slot(slot)
    return {
        "shot_hit_a_person": True,
        "reasoning": "the player is standing in front of me",
        "confidence": confidence,
        "channels": {
            name: {"visible": True, "colour": colour, "confidence": confidence}
            for name, colour in appearance.items()
        },
    }


def unreadable_reply(person=True):
    """The reply a model gives to a photograph with no garment in it: the
    floor, a bare leg, the back of somebody's head."""
    return {
        "shot_hit_a_person": person,
        "reasoning": "the crosshair lands on a bare leg; no clothing is visible",
        "confidence": 0.9,
        "channels": {
            name: {"visible": False, "colour": "unknown", "confidence": 0.1}
            for name in SCHEME.channels.names
        },
    }


def set_slot(db_session, user_id, slot):
    db_session.query(User).filter_by(id=user_id).update({"identity_slot": slot})
    db_session.commit()


def name_of(user_id):
    return AdminInterface().get_user_model(user_id).name


@pytest.fixture
def player(db_session, user_in_team, test_image_string):
    """A photographed player, wearing their own slot's colours."""
    set_slot(db_session, user_in_team, SLOT_A)
    AdminInterface().set_reference_photo(user_in_team, test_image_string)
    return user_in_team


@pytest.fixture
def other_player(db_session, team_factory, user_factory):
    """A second player, on another team in the same game, wearing SLOT_B."""
    user_id = user_factory()
    with UserInterface(user_id) as ui:
        ui.join_team(team_factory())
    set_slot(db_session, user_id, SLOT_B)
    return user_id


def game_of(user_id):
    return AdminInterface().get_user_model(user_id).game_id


# -- capture ----------------------------------------------------------------


def test_capture_stores_the_photo_and_nothing_else(
    no_api_key, db_session, admin_api_client, user_in_team, test_image_string
):
    """A kit check is not a shot: no Shot row, no ammo, no HP, no ticker."""
    before = db_session.query(User).filter_by(id=user_in_team).one()
    bullets, hit_points = before.num_bullets, before.hit_points

    response = admin_api_client.post(
        "/api/admin_capture_reference_photo",
        json={"user_id": str(user_in_team), "photo": test_image_string},
    )

    assert response.status_code == 200
    assert AdminInterface().get_reference_photo(user_in_team) == test_image_string
    assert db_session.query(Shot).count() == 0
    assert db_session.query(TickerEntry).count() == 0
    after = db_session.query(User).filter_by(id=user_in_team).one()
    assert (after.num_bullets, after.hit_points) == (bullets, hit_points)


def test_capture_without_an_api_key_still_stores_the_photo(
    no_api_key, db_session, admin_api_client, user_in_team, test_image_string
):
    """The kit check is not gated on the AI being configured."""
    admin_api_client.post(
        "/api/admin_capture_reference_photo",
        json={"user_id": str(user_in_team), "photo": test_image_string},
    )

    assert AdminInterface().get_reference_photo(user_in_team) == test_image_string
    assert AdminInterface().get_reference_review(user_in_team)["state"] is None


def test_a_new_capture_clears_the_previous_review(
    no_api_key, db_session, admin_api_client, player, test_image_string
):
    AdminInterface().store_reference_review(
        player, reference_photos.STATE_DONE, {"outcome": "hit"}
    )

    admin_api_client.post(
        "/api/admin_capture_reference_photo",
        json={"user_id": str(player), "photo": test_image_string},
    )

    assert AdminInterface().get_reference_review(player) == {
        "state": None,
        "review": None,
    }


def test_deleting_clears_the_photo_and_the_review(db_session, admin_api_client, player):
    AdminInterface().store_reference_review(
        player, reference_photos.STATE_DONE, {"outcome": "hit"}
    )

    response = admin_api_client.post(
        f"/api/admin_delete_reference_photo?user_id={player}"
    )

    assert response.status_code == 200
    assert AdminInterface().get_reference_photo(player) is None
    assert AdminInterface().get_reference_review(player)["state"] is None


# -- the review worker ------------------------------------------------------


@pytest.mark.asyncio
async def test_a_player_in_their_own_colours_is_recognised(
    db_session, player, other_player
):
    client = FakeVisionClient(reply=outfit_reply(SLOT_A))

    await reference_photos.review_reference_photo(player, client)

    stored = AdminInterface().get_reference_review(player)
    assert stored["state"] == reference_photos.STATE_DONE
    assert stored["review"]["channels"]["tshirt"]["colour"] == "black"
    identification = stored["review"]["identification"]
    assert identification["matches_expected"] is True
    assert identification["expected_user_id"] == str(player)
    assert identification["ranked"][0]["user_id"] == str(player)
    assert identification["ranked"][0]["name"] == name_of(player)
    assert identification["confident"] is True
    assert identification["readable_channels"] == 4
    # Everyone with an outfit is ranked, the photographed player included
    assert len(identification["ranked"]) == 2


@pytest.mark.asyncio
async def test_a_player_wearing_somebody_elses_colours_is_not_recognised(
    db_session, player, other_player
):
    client = FakeVisionClient(reply=outfit_reply(SLOT_B))

    await reference_photos.review_reference_photo(player, client)

    identification = AdminInterface().get_reference_review(player)["review"][
        "identification"
    ]
    assert identification["matches_expected"] is False
    assert identification["ranked"][0]["user_id"] == str(other_player)
    assert identification["ranked"][0]["name"] == name_of(other_player)


@pytest.mark.asyncio
async def test_a_player_who_has_not_picked_an_outfit_cannot_be_matched(
    db_session, user_in_team, other_player, test_image_string
):
    AdminInterface().set_reference_photo(user_in_team, test_image_string)

    await reference_photos.review_reference_photo(
        user_in_team, FakeVisionClient(reply=outfit_reply(SLOT_B))
    )

    identification = AdminInterface().get_reference_review(user_in_team)["review"][
        "identification"
    ]
    # Unknowable rather than wrong: there is nothing to compare them against
    assert identification["matches_expected"] is None
    assert identification["ranked"][0]["user_id"] == str(other_player)


@pytest.mark.asyncio
async def test_a_lone_player_with_no_outfits_in_the_game_has_no_identification(
    db_session, user_in_team, test_image_string
):
    AdminInterface().set_reference_photo(user_in_team, test_image_string)

    await reference_photos.review_reference_photo(
        user_in_team, FakeVisionClient(reply=outfit_reply(SLOT_A))
    )

    stored = AdminInterface().get_reference_review(user_in_team)
    assert stored["state"] == reference_photos.STATE_DONE
    assert stored["review"]["identification"] is None


@pytest.mark.asyncio
async def test_a_photo_with_no_readable_garment_identifies_nobody(
    db_session, player, other_player
):
    """The bug this guards: a photograph of a bare leg came back "recognised".

    With every channel erased the posterior is the flat prior handed straight
    back - an even split here - so there is no ranking worth reporting and
    certainly no match.
    """
    await reference_photos.review_reference_photo(
        player, FakeVisionClient(reply=unreadable_reply())
    )

    identification = AdminInterface().get_reference_review(player)["review"][
        "identification"
    ]
    assert identification["readable_channels"] == 0
    assert identification["matches_expected"] is None
    assert identification["confident"] is False
    assert identification["ranked"] == []


@pytest.mark.asyncio
async def test_an_unreadable_photo_of_the_only_player_identifies_nobody(
    db_session, player
):
    """The same, in its worst form: one candidate takes the whole prior, so an
    unreadable photo used to come back at p=1.00."""
    await reference_photos.review_reference_photo(
        player, FakeVisionClient(reply=unreadable_reply())
    )

    identification = AdminInterface().get_reference_review(player)["review"][
        "identification"
    ]
    assert identification["matches_expected"] is None
    assert identification["ranked"] == []


@pytest.mark.asyncio
async def test_one_readable_garment_is_still_scored(db_session, player, other_player):
    """The gate is "no evidence at all", not "less evidence than the code
    needs": a single garment still moves the posterior and is still reported."""
    reply = unreadable_reply()
    reply["channels"]["tshirt"] = {
        "visible": True,
        "colour": SCHEME.appearance_of_slot(SLOT_A)["tshirt"],
        "confidence": 0.9,
    }

    await reference_photos.review_reference_photo(player, FakeVisionClient(reply=reply))

    identification = AdminInterface().get_reference_review(player)["review"][
        "identification"
    ]
    assert identification["readable_channels"] == 1
    assert identification["ranked"][0]["user_id"] == str(player)


@pytest.mark.asyncio
async def test_a_failing_client_is_recorded_as_an_error(db_session, player):
    client = FakeVisionClient(error=VisionError("the model fell over"))

    await reference_photos.review_reference_photo(player, client)

    stored = AdminInterface().get_reference_review(player)
    assert stored["state"] == reference_photos.STATE_ERROR
    assert "fell over" in stored["review"]["error"]


@pytest.mark.asyncio
async def test_reviewing_a_player_with_no_photo_is_an_error(db_session, user_in_team):
    await reference_photos.review_reference_photo(
        user_in_team, FakeVisionClient(reply=outfit_reply(SLOT_A))
    )

    stored = AdminInterface().get_reference_review(user_in_team)
    assert stored["state"] == reference_photos.STATE_ERROR
    assert "No reference photo" in stored["review"]["error"]


@pytest.mark.asyncio
async def test_a_review_never_becomes_a_shot(db_session, player):
    await reference_photos.review_reference_photo(
        player, FakeVisionClient(reply=outfit_reply(SLOT_A))
    )

    assert db_session.query(Shot).count() == 0
    assert db_session.query(TickerEntry).count() == 0


@pytest.mark.asyncio
async def test_a_review_notifies_the_admin_stream(mocker, db_session, player):
    mocked = mocker.patch("backend.reference_photos.trigger_update_event")

    await reference_photos.review_reference_photo(
        player, FakeVisionClient(reply=outfit_reply(SLOT_A))
    )

    triggered = [call.args for call in mocked.call_args_list]
    assert ("user", player) in triggered
    assert ("shots", game_of(player)) in triggered


def test_without_an_api_key_nothing_is_queued(no_api_key, db_session, player):
    assert reference_photos.enqueue_review(player) is None
    assert AdminInterface().get_reference_review(player)["state"] is None


# -- the admin API ----------------------------------------------------------


def test_getting_a_stored_photo(admin_api_client, player, test_image_string):
    response = admin_api_client.get(f"/api/admin_get_reference_photo?user_id={player}")

    assert response.status_code == 200
    assert response.json() == test_image_string


def test_getting_a_photo_that_was_never_taken_404s(admin_api_client, user_in_team):
    response = admin_api_client.get(
        f"/api/admin_get_reference_photo?user_id={user_in_team}"
    )

    assert response.status_code == 404


def test_review_endpoint_reports_nothing_before_a_review(admin_api_client, player):
    response = admin_api_client.get(f"/api/admin_get_reference_review?user_id={player}")

    assert response.status_code == 200
    assert response.json() == {"state": None, "review": None}


def test_manual_review_without_a_key_is_a_clear_error(
    no_api_key, admin_api_client, player
):
    response = admin_api_client.post(
        f"/api/admin_review_reference_photo?user_id={player}"
    )

    assert response.status_code == 503
    assert "OPENROUTER_API_KEY" in response.json()["detail"]


def test_manual_review_of_a_player_with_no_photo_404s(
    no_api_key, admin_api_client, user_in_team
):
    response = admin_api_client.post(
        f"/api/admin_review_reference_photo?user_id={user_in_team}"
    )

    assert response.status_code == 404


@pytest.mark.parametrize(
    "method, path",
    [
        ("get", "/api/admin_get_reference_photo?user_id={user_id}"),
        ("get", "/api/admin_get_reference_review?user_id={user_id}"),
        ("post", "/api/admin_review_reference_photo?user_id={user_id}"),
        ("post", "/api/admin_delete_reference_photo?user_id={user_id}"),
        ("get", "/api/admin_get_reference_photo_status?game_id={game_id}"),
    ],
)
def test_the_endpoints_need_admin_auth(api_client, player, method, path):
    response = getattr(api_client, method)(
        path.format(user_id=player, game_id=game_of(player))
    )

    assert response.status_code == 403


def test_capture_needs_admin_auth(api_client, user_in_team, test_image_string):
    response = api_client.post(
        "/api/admin_capture_reference_photo",
        json={"user_id": str(user_in_team), "photo": test_image_string},
    )

    assert response.status_code == 403


# -- the roster -------------------------------------------------------------


def test_the_roster_lists_every_player_without_the_photos(
    admin_api_client, player, other_player, test_image_string
):
    response = admin_api_client.get(
        f"/api/admin_get_reference_photo_status?game_id={game_of(player)}"
    )

    assert response.status_code == 200
    rows = {row["user_id"]: row for row in response.json()}
    assert set(rows) == {str(player), str(other_player)}
    assert rows[str(player)]["has_photo"] is True
    assert rows[str(player)]["name"] == name_of(player)
    assert rows[str(player)]["team_name"] is not None
    assert rows[str(other_player)]["has_photo"] is False
    assert rows[str(other_player)]["review_state"] is None
    # The photo itself is never in the listing
    assert test_image_string not in response.text


@pytest.mark.asyncio
async def test_the_roster_carries_the_verdict_of_a_completed_review(
    admin_api_client, player, other_player
):
    await reference_photos.review_reference_photo(
        player, FakeVisionClient(reply=outfit_reply(SLOT_B))
    )

    rows = admin_api_client.get(
        f"/api/admin_get_reference_photo_status?game_id={game_of(player)}"
    ).json()
    row = next(r for r in rows if r["user_id"] == str(player))

    assert row["review_state"] == reference_photos.STATE_DONE
    assert row["matches_expected"] is False
    assert row["top_name"] == name_of(other_player)
    assert row["top_probability"] > 0.5
    assert row["confident"] is True
    assert row["readable_channels"] == 4


@pytest.mark.asyncio
async def test_the_roster_names_nobody_for_an_unreadable_photo(
    admin_api_client, player, other_player
):
    await reference_photos.review_reference_photo(
        player, FakeVisionClient(reply=unreadable_reply())
    )

    rows = admin_api_client.get(
        f"/api/admin_get_reference_photo_status?game_id={game_of(player)}"
    ).json()
    row = next(r for r in rows if r["user_id"] == str(player))

    assert row["readable_channels"] == 0
    assert row["matches_expected"] is None
    assert row["top_name"] is None


def test_the_roster_has_no_verdict_for_an_errored_review(admin_api_client, player):
    AdminInterface().store_reference_review(
        player, reference_photos.STATE_ERROR, "connection reset"
    )

    rows = admin_api_client.get(
        f"/api/admin_get_reference_photo_status?game_id={game_of(player)}"
    ).json()
    row = next(r for r in rows if r["user_id"] == str(player))

    assert row["review_state"] == reference_photos.STATE_ERROR
    assert row["matches_expected"] is None
    assert row["top_name"] is None


def test_the_roster_404s_on_an_unknown_game(admin_api_client, db_session):
    response = admin_api_client.get(
        f"/api/admin_get_reference_photo_status?game_id={get_uuid()}"
    )

    assert response.status_code == 404


# -- storage and reset ------------------------------------------------------


def test_a_review_is_stored_as_json_text(db_session, player):
    AdminInterface().store_reference_review(
        player, reference_photos.STATE_DONE, {"outcome": "hit"}
    )

    user = db_session.query(User).filter_by(id=player).one()
    assert json.loads(user.reference_review) == {"outcome": "hit"}


def test_an_error_message_survives_being_stored_as_non_json(db_session, player):
    AdminInterface().store_reference_review(
        player, reference_photos.STATE_ERROR, "connection reset"
    )

    assert AdminInterface().get_reference_review(player)["review"] == {
        "error": "connection reset"
    }


def test_resetting_the_game_wipes_the_reference_photos(db_session, player):
    """These are photographs of identifiable people: they do not outlive the
    game they were taken for."""
    AdminInterface().store_reference_review(
        player, reference_photos.STATE_DONE, {"outcome": "hit"}
    )

    AdminInterface().reset_game(game_of(player))

    db_session.expire_all()
    user = db_session.query(User).filter_by(id=player).one()
    assert user.reference_photo_base64 is None
    assert user.reference_review_state is None
    assert user.reference_review is None
