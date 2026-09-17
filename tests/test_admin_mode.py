import datetime
import io
import time
import zipfile
from uuid import uuid4

import pytest
from fastapi.exceptions import HTTPException

from backend import admin_interface
from backend.admin_interface import AdminInterface
from backend.image_processing import load_image
from backend.model import APPEALS_PER_GAME
from backend.model import BASIC_WEAPON
from backend.model import STARTING_HIT_POINTS
from backend.model import Drop
from backend.model import Game
from backend.model import Item
from backend.model import ItemType
from backend.model import Shot
from backend.model import TickerEntry
from backend.model import User
from backend.user_interface import UserInterface

from .shared_fixtures import NO_FIRE_DELAY
from .shared_fixtures import strip_armour


# Mock "schedule_update_event" since we don't have an asyncio loop
@pytest.fixture(autouse=True)
def mock_asyncio_tasks(mocker):
    mocker.patch("backend.asyncio_triggers.schedule_update_event")


def test_making_item():
    assert isinstance(AdminInterface().make_new_item("ammo", {"num": 123}), str)


def test_using_made_item(user_in_team):
    encoded_item = AdminInterface().make_new_item("ammo", {"num": 123})

    UserInterface(user_in_team).collect_item(encoded_item)


def test_making_item_fail():
    with pytest.raises(HTTPException):
        AdminInterface().make_new_item("whatever", {"num": 123})


def submit_shot_and_get_id(db_session, user_id, image):
    """Fire a shot and return *that* shot's id.

    Ids are uuid4 and time_created has 1s resolution, so neither
    "highest id" nor "latest timestamp" identifies the shot just created once
    there is more than one. Taking the difference does.
    """
    before = {row[0] for row in db_session.query(Shot.id).all()}
    UserInterface(user_id).submit_shot(image)
    after = {row[0] for row in db_session.query(Shot.id).all()}

    (new_id,) = after - before
    return new_id


@pytest.fixture
def old_shot_prep(
    admin_api_client, db_session, user_factory, team_factory, test_image_string
):
    team_a = team_factory()
    team_b = team_factory()

    user_a = user_factory()
    user_b = user_factory()

    UserInterface(user_a).join_team(team_a)
    UserInterface(user_b).join_team(team_b)

    # Everything below turns on one shot killing user B - the invalidation
    # cascade, the refund, the queue emptying - so neither player wears the
    # starting armour M1.2 gave them.
    strip_armour(user_a, user_b)

    AdminInterface().award_user_ammo(user_a, 1000)
    AdminInterface().award_user_ammo(user_b, 1000)

    # Give both users the basic weapon
    UserInterface(user_a).set_weapon_data(1, NO_FIRE_DELAY)
    UserInterface(user_b).set_weapon_data(1, NO_FIRE_DELAY)

    # User A shoots user B (the admin hasn't checked it yet)
    shot_a = submit_shot_and_get_id(db_session, user_a, test_image_string)

    # User B shoots user A (though they should be dead) - pinned strictly
    # after shot_a, since the invalidation cascade below only clears a
    # victim's own queued shots fired at or after the photo that kills them,
    # and time_created's 1s resolution can't be trusted to keep these two
    # shots in submission order on its own.
    shot_b = submit_shot_and_get_id(db_session, user_b, test_image_string)
    db_session.query(Shot).filter_by(id=shot_a).update(
        {"time_created": datetime.datetime(2026, 1, 1, 12, 0, 0)}
    )
    db_session.query(Shot).filter_by(id=shot_b).update(
        {"time_created": datetime.datetime(2026, 1, 1, 12, 0, 5)}
    )
    db_session.commit()

    # The admin checks user A and awards the shot to them
    response = admin_api_client.post(
        f"/api/admin_shot_hit_user?shot_id={shot_a}&target_user_id={user_b}"
    )
    assert response.is_success

    return user_a, user_b, shot_a, shot_b


# Now, shot A should have been marked as checked (because it was)
def test_alive_user_shot_checked(old_shot_prep, db_session):
    user_a, user_b, shot_a, shot_b = old_shot_prep
    shot_a_model: Shot = db_session.get(Shot, shot_a)
    assert shot_a_model.checked


# Shot B should be marked as checked because it's now invalid
def test_dead_user_shot_checked(old_shot_prep, db_session):
    user_a, user_b, shot_a, shot_b = old_shot_prep
    shot_b_model: Shot = db_session.get(Shot, shot_b)
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
# Named apart from the check below it: the two shared a name, so this one was
# shadowed and had never actually run.
def test_awarded_shot_records_shooter_and_target(old_shot_prep):
    user_a, user_b, shot_a, shot_b = old_shot_prep
    # get_shot_model, not _get_shot_orm: the ORM instance is detached once
    # @db_scoped closes its session, so reading off it raises.
    shot = AdminInterface().get_shot_model(shot_a)

    assert shot.user_id == user_a
    assert shot.target_user_id == user_b


# The refunded Shot should be only the shooter.
# This was xfail'd as "fails sometimes... suspicious": the cause was
# old_shot_prep identifying the shot it had just created by highest uuid4,
# which picks an arbitrary shot once there are two. See
# submit_shot_and_get_id.
def test_shots_record_targets(old_shot_prep):
    user_a, user_b, shot_a, shot_b = old_shot_prep
    shot = AdminInterface().get_shot_model(shot_b)

    assert shot.user_id == user_b
    assert shot.target_user_id is None


@pytest.mark.parametrize("execution_number", range(10))
def test_target_recorded_reliably(
    db_session, user_factory, team_factory, test_image_string, execution_number
):
    user_a = user_factory()
    user_b = user_factory()
    team_a = team_factory()
    team_b = team_factory()
    UserInterface(user_a).join_team(team_a)
    UserInterface(user_b).join_team(team_b)

    AdminInterface().award_user_ammo(user_a, 1000)

    UserInterface(user_a).submit_shot(test_image_string)

    shot_id = db_session.query(Shot.id).order_by(Shot.id.desc()).first()[0]
    assert AdminInterface().get_shot_model(shot_id).user_id == user_a


def test_scoreboard_builds(db_session, team_factory, user_factory):
    team_id = team_factory()
    user_id_1 = user_factory()
    user_id_2 = user_factory()
    UserInterface(user_id_1).join_team(team_id)
    UserInterface(user_id_2).join_team(team_id)
    UserInterface(user_id_2).award_HP(2)
    game_id = db_session.get(User, user_id_1).team.game.id

    print(game_id)
    print(AdminInterface().get_scoreboard(game_id))


def test_hit_user(user_in_team):
    AdminInterface().hit_user_by_admin(user_id=user_in_team)


def test_dump_images_returns_zip_download(admin_api_client, old_shot_prep):
    response = admin_api_client.post("/api/admin_dump_images")

    assert response.is_success
    assert response.headers["content-type"] == "application/zip"
    assert (
        'attachment; filename="shot_images.zip"'
        in response.headers["content-disposition"]
    )

    with zipfile.ZipFile(io.BytesIO(response.content)) as zip_file:
        names = zip_file.namelist()
        # One marked-up image per shot submitted in old_shot_prep
        assert len(names) == 2
        assert all(name.endswith(".png") for name in names)


def test_shot_notes_roundtrip(admin_api_client, old_shot_prep):
    _, _, _, shot_b = old_shot_prep

    response = admin_api_client.get(
        "/api/admin_get_shot_notes", params={"shot_id": str(shot_b)}
    )
    assert response.is_success
    assert response.json() == {"notes": ""}

    # Deliberately full of URL-hostile characters: notes are prose.
    note = "Crosshair passes just above the head & into the leaves? A miss."
    response = admin_api_client.post(
        "/api/admin_set_shot_notes", params={"shot_id": str(shot_b), "notes": note}
    )
    assert response.is_success

    response = admin_api_client.get(
        "/api/admin_get_shot_notes", params={"shot_id": str(shot_b)}
    )
    assert response.json() == {"notes": note}


def test_shot_notes_unknown_shot_404s(admin_api_client):
    response = admin_api_client.get(
        "/api/admin_get_shot_notes", params={"shot_id": str(uuid4())}
    )
    assert response.status_code == 404


def test_shots_info_includes_checked_only_when_asked(
    admin_api_client, db_session, user_in_team, test_image_string
):
    AdminInterface().award_user_ammo(user_in_team, 10)
    UserInterface(user_in_team).set_weapon_data(1, NO_FIRE_DELAY)
    UserInterface(user_in_team).submit_shot(test_image_string)
    shot_id = db_session.query(Shot.id).one()[0]

    def queue_ids(**params):
        response = admin_api_client.get("/api/admin_get_shots_info", params=params)
        assert response.is_success
        return response.json()

    assert queue_ids() == [str(shot_id)]

    response = admin_api_client.post(
        "/api/admin_mark_shot_missed", params={"shot_id": str(shot_id)}
    )
    assert response.is_success

    assert queue_ids() == []
    assert queue_ids(include_checked=True) == [str(shot_id)]


# -- re-adjudicating a contested shot (roadmap R8) ---------------------------


def contest(db_session, shot_id):
    """Mark a shot contested without going through the appeal endpoint."""
    db_session.query(Shot).filter_by(id=shot_id).update({"appeal_state": "open"})
    db_session.commit()


def test_a_contested_checked_shot_can_be_re_adjudicated(
    db_session, two_users_in_different_teams, test_image_string
):
    shooter, target = two_users_in_different_teams
    UserInterface(shooter).award_ammo(1)
    UserInterface(shooter).set_weapon_data(1, NO_FIRE_DELAY)
    shot_id = UserInterface(shooter).submit_shot(test_image_string)
    AdminInterface().hit_user(shot_id, target)

    contest(db_session, shot_id)
    AdminInterface().mark_shot_missed(shot_id)

    db_session.expire_all()
    shot = db_session.get(Shot, shot_id)
    assert shot.result == "miss"
    # A shot that is no longer a hit is nobody's hit
    assert shot.target_user_id is None


def test_a_plain_checked_shot_still_cannot_be_re_adjudicated(
    db_session, user_in_team, test_image_string
):
    UserInterface(user_in_team).award_ammo(1)
    UserInterface(user_in_team).set_weapon_data(1, NO_FIRE_DELAY)
    shot_id = UserInterface(user_in_team).submit_shot(test_image_string)
    AdminInterface().mark_shot_missed(shot_id)

    with pytest.raises(HTTPException) as excinfo:
        AdminInterface().mark_shot_bystander(shot_id)

    assert excinfo.value.status_code == 400


# -- settling the appeal (roadmap R8) ----------------------------------------


@pytest.fixture
def contested_hit(two_users_in_different_teams, test_image_string):
    """A shot ruled a hit and then appealed by its target."""
    shooter, target = two_users_in_different_teams
    # The hit knocks the target out, which is what makes the appeal worth
    # lodging, so one hit has to be fatal.
    strip_armour(target)
    UserInterface(shooter).award_ammo(1)
    UserInterface(shooter).set_weapon_data(1, NO_FIRE_DELAY)
    shot_id = UserInterface(shooter).submit_shot(test_image_string)
    AdminInterface().hit_user(shot_id, target)
    UserInterface(target).appeal_shot(shot_id, "missed")
    return shooter, target, shot_id


def appeal_state(db_session, shot_id):
    db_session.expire_all()
    return db_session.get(Shot, shot_id).appeal_state


def test_a_different_ruling_upholds_the_appeal(db_session, contested_hit):
    shooter, target, shot_id = contested_hit
    assert UserInterface(target).get_user_model().appeals_remaining == 2

    AdminInterface().mark_shot_missed(shot_id)

    assert appeal_state(db_session, shot_id) == "upheld"
    assert UserInterface(target).get_user_model().appeals_remaining == 3


def test_the_same_ruling_rejects_the_appeal(db_session, contested_hit):
    shooter, target, shot_id = contested_hit

    AdminInterface().hit_user(shot_id, target)

    assert appeal_state(db_session, shot_id) == "rejected"
    # The price is on being wrong, not on appealing - and this appeal was wrong
    assert UserInterface(target).get_user_model().appeals_remaining == 2


def test_re_ruling_the_hit_onto_somebody_else_upholds_it(
    db_session, contested_hit, user_factory, team_factory
):
    shooter, target, shot_id = contested_hit
    somebody_else = user_factory()
    UserInterface(somebody_else).join_team(team_factory())

    AdminInterface().hit_user(shot_id, somebody_else)

    assert appeal_state(db_session, shot_id) == "upheld"
    assert UserInterface(target).get_user_model().appeals_remaining == 3
    assert db_session.get(Shot, shot_id).target_user_id == somebody_else


def test_a_refund_gives_the_benefit_of_the_doubt(db_session, contested_hit):
    # Not a judgement either way, so the appeal comes back. Falls out of the
    # rule - "refunded" differs from "hit" - rather than needing a special case
    shooter, target, shot_id = contested_hit

    AdminInterface().refund_shot(shot_id)

    assert appeal_state(db_session, shot_id) == "upheld"
    assert UserInterface(target).get_user_model().appeals_remaining == 3


@pytest.fixture
def contested_no_hit(two_users_in_different_teams, test_image_string):
    """A shot ruled a miss or a bystander, then appealed by the shooter.

    Only the shooter can contest either ruling: neither takes anything off
    anybody else.
    """

    def _make(ruling):
        shooter, target = two_users_in_different_teams
        UserInterface(shooter).award_ammo(1)
        UserInterface(shooter).set_weapon_data(1, NO_FIRE_DELAY)
        shot_id = UserInterface(shooter).submit_shot(test_image_string)
        if ruling == "miss":
            AdminInterface().mark_shot_missed(shot_id)
        else:
            AdminInterface().mark_shot_bystander(shot_id)
        UserInterface(shooter).appeal_shot(shot_id, "actually_hit")
        return shooter, target, shot_id

    return _make


@pytest.mark.parametrize(
    "ruled, re_ruled", [("miss", "bystander"), ("bystander", "miss")]
)
def test_swapping_miss_and_bystander_rejects_the_appeal(
    db_session, contested_no_hit, ruled, re_ruled
):
    # Both rulings say the same thing to the appellant - the shot hit no player
    # - so trading one for the other overturns nothing
    shooter, target, shot_id = contested_no_hit(ruled)
    assert UserInterface(shooter).get_user_model().appeals_remaining == 2

    if re_ruled == "miss":
        AdminInterface().mark_shot_missed(shot_id)
    else:
        AdminInterface().mark_shot_bystander(shot_id)

    assert appeal_state(db_session, shot_id) == "rejected"
    assert UserInterface(shooter).get_user_model().appeals_remaining == 2

    public = UserInterface(shooter).get_messages(20, private=False)
    assert not any("referee overturned" in message for _, message, _ in public)


def test_re_ruling_a_miss_as_a_hit_still_upholds_it(db_session, contested_no_hit):
    shooter, target, shot_id = contested_no_hit("miss")

    AdminInterface().hit_user(shot_id, target)

    assert appeal_state(db_session, shot_id) == "upheld"
    assert UserInterface(shooter).get_user_model().appeals_remaining == 3


def test_refunding_a_contested_miss_gives_the_benefit_of_the_doubt(
    db_session, contested_no_hit
):
    shooter, target, shot_id = contested_no_hit("miss")

    AdminInterface().refund_shot(shot_id)

    assert appeal_state(db_session, shot_id) == "upheld"
    assert UserInterface(shooter).get_user_model().appeals_remaining == 3


def test_both_appellants_are_refunded_when_both_appealed(db_session, contested_hit):
    shooter, target, shot_id = contested_hit
    UserInterface(shooter).appeal_shot(shot_id, "actually_hit")

    AdminInterface().mark_shot_bystander(shot_id)

    assert appeal_state(db_session, shot_id) == "upheld"
    assert UserInterface(target).get_user_model().appeals_remaining == 3
    assert UserInterface(shooter).get_user_model().appeals_remaining == 3


def test_a_ruled_appeal_is_terminal(db_session, contested_hit):
    shooter, target, shot_id = contested_hit
    AdminInterface().mark_shot_missed(shot_id)

    # The admin's word ends the loop: nobody appeals the same shot twice, and
    # the shot cannot be re-adjudicated again either
    (shot,) = UserInterface(shooter).get_own_shots()
    assert shot["can_appeal"] is False

    with pytest.raises(HTTPException) as excinfo:
        AdminInterface().mark_shot_bystander(shot_id)

    assert excinfo.value.status_code == 400


def test_upholding_an_appeal_is_announced(db_session, contested_hit):
    shooter, target, shot_id = contested_hit

    AdminInterface().mark_shot_missed(shot_id)

    public = UserInterface(shooter).get_messages(20, private=False)
    assert any("referee overturned" in message for _, message, _ in public)

    private = UserInterface(target).get_messages(20, private=True)
    assert any("appeal was upheld" in message for _, message, _ in private)


def test_rejecting_an_appeal_tells_the_appellant_only(db_session, contested_hit):
    shooter, target, shot_id = contested_hit

    AdminInterface().hit_user(shot_id, target)

    private = UserInterface(target).get_messages(20, private=True)
    assert any("appeal was rejected" in message for _, message, _ in private)

    public = UserInterface(shooter).get_messages(20, private=False)
    assert not any("referee overturned" in message for _, message, _ in public)


def test_re_ruling_never_unwinds_hit_points(db_session, contested_hit):
    """The admin repairs a wrongly-taken life by hand, with set_user_HP: there
    is no compensating action for a knockout's cascade anywhere here."""
    shooter, target, shot_id = contested_hit
    assert UserInterface(target).get_user_model().hit_points == 0

    AdminInterface().mark_shot_missed(shot_id)

    assert UserInterface(target).get_user_model().hit_points == 0


def test_the_private_hit_message_carries_the_shot_id(db_session, contested_hit):
    shooter, target, shot_id = contested_hit

    entry = (
        db_session.query(TickerEntry)
        .filter_by(private_user_id=target)
        .order_by(TickerEntry.id)
        .first()
    )
    assert entry.shot_id == shot_id


# -- the contested queue -----------------------------------------------------


def test_contested_shots_are_listed_oldest_complaint_first(
    db_session, contested_hit, user_factory, team_factory, test_image_string
):
    shooter, target, first = contested_hit

    UserInterface(shooter).award_ammo(1)
    second = UserInterface(shooter).submit_shot(test_image_string)
    AdminInterface().mark_shot_missed(second)
    UserInterface(shooter).appeal_shot(second, "actually_hit")

    assert AdminInterface().get_contested_shot_ids() == [first, second]

    AdminInterface().mark_shot_missed(first)
    assert AdminInterface().get_contested_shot_ids() == [second]


def test_contested_shots_endpoint(admin_api_client, contested_hit):
    shooter, target, shot_id = contested_hit

    response = admin_api_client.get("/api/admin_get_contested_shots_info")
    assert response.is_success
    assert response.json() == [str(shot_id)]


def test_shot_appeal_endpoint(admin_api_client, contested_hit):
    shooter, target, shot_id = contested_hit

    response = admin_api_client.get(
        "/api/admin_get_shot_appeal", params={"shot_id": str(shot_id)}
    )
    assert response.is_success

    appeal = response.json()
    assert appeal["appeal_state"] == "open"
    assert appeal["target_appeal_reason"] == "missed"
    assert appeal["shooter_appeal_reason"] is None
    assert appeal["result"] == "hit"
    assert appeal["appealed_at"] is not None
    assert appeal["shooter_name"] == UserInterface(shooter).get_user_model().name
    assert appeal["target_name"] == UserInterface(target).get_user_model().name


def test_resetting_the_game_restores_the_appeal_budget(contested_hit):
    shooter, target, shot_id = contested_hit
    assert UserInterface(target).get_user_model().appeals_remaining == 2

    AdminInterface().reset_game(UserInterface(target).get_game_id())

    assert UserInterface(target).get_user_model().appeals_remaining == 3


def test_set_circle(admin_api_client, user_in_team):
    game_id = UserInterface(user_in_team).get_game_id()

    query_params = {
        "game_id": game_id,
        "name": "BOTH",
        "lat": 51.0,
        "long": 0.0,
        "radius_km": 1.0,
    }
    endpoint = "/api/admin_set_circle"

    # Format query params into the url:
    endpoint += "?" + "&".join(
        [f"{key}={value}" for key, value in query_params.items()]
    )

    response = admin_api_client.post(endpoint)

    assert response.is_success


# -- the countdown cue (backend/next_event.py) -------------------------------


def cue_of(user_id):
    """The cue as the player's own phone sees it."""
    model = UserInterface(user_id).get_user_model()
    return model.next_event_kind, model.next_event_at, model.next_event_note


def test_cueing_the_next_circle_starts_a_countdown(user_in_team):
    game_id = game_of_user(user_in_team)

    deadline = AdminInterface().cue_next_event(game_id, "circle", seconds=600)

    kind, at, note = cue_of(user_in_team)
    assert kind == "circle"
    assert at == pytest.approx(deadline)
    assert at == pytest.approx(time.time() + 600, abs=5)
    assert note is None


def test_a_cue_carries_the_note_the_admin_typed(user_in_team):
    game_id = game_of_user(user_in_team)

    AdminInterface().cue_next_event(
        game_id, "drop", seconds=300, note="  a medpack and two armour  "
    )

    assert cue_of(user_in_team)[2] == "a medpack and two armour"


def test_a_blank_note_is_no_note(user_in_team):
    """The admin's input box arrives as an empty string, not as None."""
    game_id = game_of_user(user_in_team)

    AdminInterface().cue_next_event(game_id, "drop", seconds=300, note="   ")

    assert cue_of(user_in_team)[2] is None


def test_cueing_again_replaces_the_first_cue(user_in_team):
    game_id = game_of_user(user_in_team)

    AdminInterface().cue_next_event(game_id, "circle", seconds=600)
    second = AdminInterface().cue_next_event(game_id, "drop", seconds=120)

    kind, at, _note = cue_of(user_in_team)
    assert kind == "drop"
    assert at == pytest.approx(second)


def test_an_unknown_kind_is_refused(user_in_team):
    with pytest.raises(HTTPException):
        AdminInterface().cue_next_event(
            game_of_user(user_in_team), "fireworks", seconds=60
        )


def test_a_countdown_to_the_past_is_refused(user_in_team):
    with pytest.raises(HTTPException):
        AdminInterface().cue_next_event(
            game_of_user(user_in_team), "circle", seconds=-60
        )


def test_cancelling_the_cue_clears_all_three_columns(user_in_team):
    game_id = game_of_user(user_in_team)
    AdminInterface().cue_next_event(game_id, "drop", seconds=300, note="a medpack")

    AdminInterface().cancel_cue(game_id)

    assert cue_of(user_in_team) == (None, None, None)


def test_cancelling_when_nothing_is_cued_is_harmless(user_in_team):
    AdminInterface().cancel_cue(game_of_user(user_in_team))

    assert cue_of(user_in_team) == (None, None, None)


def test_the_cue_is_announced_in_the_ticker(db_session, user_in_team):
    game_id = game_of_user(user_in_team)

    AdminInterface().cue_next_event(game_id, "circle", seconds=600)

    messages = [entry.message for entry in db_session.query(TickerEntry).all()]
    assert any("10 minutes" in message for message in messages)


def test_a_short_countdown_is_announced_in_seconds(db_session, user_in_team):
    """The ticker line is read in passing by somebody walking, so the unit
    follows the number rather than the other way round."""
    game_id = game_of_user(user_in_team)

    AdminInterface().cue_next_event(game_id, "circle", seconds=45)

    messages = [entry.message for entry in db_session.query(TickerEntry).all()]
    assert any("45 seconds" in message for message in messages)


def test_firing_a_cue_that_has_been_replaced_does_nothing(user_in_team):
    """The double-firing guard: a timer that slept through a re-cue must not
    close the circle on the deadline it was armed for."""
    game_id = game_of_user(user_in_team)
    stale = AdminInterface().cue_next_event(game_id, "circle", seconds=600)
    AdminInterface().cue_next_event(game_id, "circle", seconds=1200)

    assert AdminInterface().fire_next_event(game_id, expected_at=stale) is False
    assert cue_of(user_in_team)[0] == "circle"


def test_firing_a_cue_that_has_been_cancelled_does_nothing(user_in_team):
    game_id = game_of_user(user_in_team)
    deadline = AdminInterface().cue_next_event(game_id, "circle", seconds=600)
    AdminInterface().cancel_cue(game_id)

    assert AdminInterface().fire_next_event(game_id, expected_at=deadline) is False


def test_firing_a_drop_cue_clears_it(user_in_team):
    game_id = game_of_user(user_in_team)
    deadline = AdminInterface().cue_next_event(game_id, "drop", seconds=300)

    assert AdminInterface().fire_next_event(game_id, expected_at=deadline) is True
    assert cue_of(user_in_team) == (None, None, None)


def test_a_drop_reaching_zero_sends_the_courier(db_session, user_in_team):
    """The drop's whole effect at zero is the announcement (M3.3): the crate
    is not on the map until the courier broadcasts, so nothing is placed."""
    game_id = game_of_user(user_in_team)
    deadline = AdminInterface().cue_next_event(game_id, "drop", seconds=300)

    AdminInterface().fire_next_event(game_id, expected_at=deadline)

    messages = [entry.message for entry in db_session.query(TickerEntry).all()]
    assert "The courier has set off" in messages
    assert UserInterface(user_in_team).get_circles()["drop_circle_lat"] is None


def test_the_drop_announcement_says_what_is_in_it(db_session, user_in_team):
    AdminInterface().cue_next_event(
        game_of_user(user_in_team), "drop", seconds=300, note="a medpack"
    )

    messages = [entry.message for entry in db_session.query(TickerEntry).all()]
    assert any("a medpack" in message for message in messages)


def test_a_drop_with_no_contents_does_not_trail_off(db_session, user_in_team):
    """An empty note must not leave the ticker saying "...in 5 minutes - "."""
    AdminInterface().cue_next_event(game_of_user(user_in_team), "drop", seconds=300)

    messages = [entry.message for entry in db_session.query(TickerEntry).all()]
    assert any(message.endswith("5 minutes") for message in messages)


def test_a_signed_up_player_with_no_team_is_told_about_the_cue(
    db_session, user_factory, one_game, mocker
):
    """A player who has signed up but not been handed a team sits on the
    waiting page, which is exactly where the countdown is worth reading."""
    bumped = mocker.patch("backend.admin_interface.trigger_update_event")
    user_id = user_factory()
    db_session.query(User).filter_by(id=user_id).one().game_id = one_game
    db_session.commit()

    AdminInterface().cue_next_event(one_game, "circle", seconds=600)

    assert mocker.call("user", user_id) in bumped.call_args_list


def test_only_live_cues_are_swept_up(user_in_team, one_game):
    assert AdminInterface().get_cued_games() == []

    game_id = game_of_user(user_in_team)
    deadline = AdminInterface().cue_next_event(game_id, "circle", seconds=600)

    assert AdminInterface().get_cued_games() == [(game_id, pytest.approx(deadline))]

    AdminInterface().cancel_cue(game_id)
    assert AdminInterface().get_cued_games() == []


def test_cue_endpoints(admin_api_client, user_in_team):
    game_id = game_of_user(user_in_team)

    response = admin_api_client.post(
        "/api/admin_cue_next_event",
        params={"game_id": str(game_id), "kind": "circle", "minutes": 10},
    )
    assert response.is_success
    assert cue_of(user_in_team)[0] == "circle"

    response = admin_api_client.post(
        "/api/admin_cancel_cue", params={"game_id": str(game_id)}
    )
    assert response.is_success
    assert cue_of(user_in_team) == (None, None, None)


def test_the_cue_endpoint_refuses_a_kind_it_does_not_know(
    admin_api_client, user_in_team
):
    response = admin_api_client.post(
        "/api/admin_cue_next_event",
        params={
            "game_id": str(game_of_user(user_in_team)),
            "kind": "fireworks",
            "minutes": 10,
        },
    )
    assert response.status_code == 422


# -- the spectator screen's reads (react-ui/src/SpectatorView.js) ------------


def game_of_user(user_id):
    return UserInterface(user_id).get_user_model().game_id


def shots_a_second_apart(db_session, shot_ids):
    """Push the given shots' timestamps apart, oldest first.

    time_created has 1s resolution, so shots fired inside one test tie and sort
    by the uuid4 tiebreak. Ordering is only testable once they differ.
    """
    for offset, shot_id in enumerate(shot_ids):
        db_session.query(Shot).filter_by(id=shot_id).update(
            {"time_created": datetime.datetime(2026, 9, 19, 20, offset)}
        )
    db_session.commit()


def test_recent_shots_are_newest_first(admin_api_client, old_shot_prep, db_session):
    user_a, _user_b, shot_a, shot_b = old_shot_prep
    shots_a_second_apart(db_session, [shot_a, shot_b])

    response = admin_api_client.get(
        "/api/admin_get_recent_shots", params={"game_id": str(game_of_user(user_a))}
    )
    assert response.is_success

    assert [row["id"] for row in response.json()] == [str(shot_b), str(shot_a)]


def test_recent_shots_include_checked_ones(admin_api_client, old_shot_prep):
    """The feed is a history of what just happened, not a queue of work.

    old_shot_prep adjudicates shot A, so a queue-shaped read would drop it.
    """
    user_a, _user_b, shot_a, shot_b = old_shot_prep

    response = admin_api_client.get(
        "/api/admin_get_recent_shots", params={"game_id": str(game_of_user(user_a))}
    )

    assert {row["id"] for row in response.json()} == {str(shot_a), str(shot_b)}


def test_recent_shots_say_who_fired_and_carry_the_verdict(
    admin_api_client, old_shot_prep, db_session
):
    user_a, user_b, shot_a, _shot_b = old_shot_prep

    names = {u_id: db_session.get(User, u_id).name for u_id in (user_a, user_b)}

    response = admin_api_client.get(
        "/api/admin_get_recent_shots", params={"game_id": str(game_of_user(user_a))}
    )
    row = next(r for r in response.json() if r["id"] == str(shot_a))

    assert row["shooter_name"] == names[user_a]
    assert row["target_name"] == names[user_b]
    assert row["checked"] is True
    assert row["result"] == "hit"
    # The review block the screen renders through ShotQueue's charlesBotVerdict
    assert set(row) >= {"state", "review", "identification", "escalation_state"}


def test_recent_shots_never_carry_the_photograph(admin_api_client, old_shot_prep):
    """It is refetched on every SSE bump - a megabyte per shot would be fatal."""
    user_a, _user_b, _shot_a, _shot_b = old_shot_prep

    response = admin_api_client.get(
        "/api/admin_get_recent_shots", params={"game_id": str(game_of_user(user_a))}
    )

    for row in response.json():
        assert "image_base64" not in row


def test_recent_shots_respects_its_limit(admin_api_client, old_shot_prep, db_session):
    user_a, _user_b, shot_a, shot_b = old_shot_prep
    shots_a_second_apart(db_session, [shot_a, shot_b])

    response = admin_api_client.get(
        "/api/admin_get_recent_shots",
        params={"game_id": str(game_of_user(user_a)), "limit": 1},
    )

    assert [row["id"] for row in response.json()] == [str(shot_b)]


def test_a_thumbnail_is_bounded_by_the_thumbnail_dimension(
    admin_api_client, old_shot_prep
):
    """The contract is the pixel size, not the byte count.

    A phone photo is thousands of pixels across; the spectator screen's biggest
    frame is 600x900. Asserting on encoded length instead would pass or fail
    on whether the fixture image happened to be larger than the cap.
    """
    _user_a, _user_b, shot_a, _shot_b = old_shot_prep

    response = admin_api_client.get(
        "/api/admin_get_shot_thumbnail", params={"shot_id": str(shot_a)}
    )
    assert response.is_success

    thumbnail = response.json()["image_base64"]
    assert thumbnail.startswith("data:image/")

    image, _ = load_image(thumbnail)
    assert max(image.size) <= admin_interface.THUMBNAIL_MAX_DIMENSION


def test_the_admin_scoreboard_answers_without_a_player_session(
    admin_api_client, old_shot_prep
):
    """The whole reason it exists: a browser wired to a TV never joined a game,
    so the player-facing /get_scoreboard 404s for it."""
    user_a, _user_b, _shot_a, _shot_b = old_shot_prep

    assert admin_api_client.get("/api/get_scoreboard").status_code == 404

    response = admin_api_client.get(
        "/api/admin_get_scoreboard", params={"game_id": str(game_of_user(user_a))}
    )
    assert response.is_success
    assert len(response.json()["table"]) == 2


@pytest.fixture
def game_mid_sandbox(db_session, team_factory, user_factory, test_image_string):
    """A game part-way through the sandbox hour, with everything M2.1 has an
    opinion about: a player in a team who has shot, scanned and been shot at,
    a signed-up player who has not reached the door yet, a reference photo, a
    location, a nominated leader, circles, a ticker and a cued event.

    Returns (game_id, player_in_team, signup_with_no_team).
    """
    team_id = team_factory()
    player = user_factory()
    with UserInterface(player) as ui:
        ui.join_team(team_id)

    game_id = game_of_user(player)

    # The player who signed up through the game link and has not scanned a
    # team card yet - invisible to reset_game's walk over the teams
    signup = user_factory()
    db_session.query(User).filter_by(id=signup).update({"game_id": game_id})
    db_session.commit()

    # An hour of sandbox: ammo, armour, a weapon, a shot fired, a hit taken
    with UserInterface(player) as ui:
        ui.award_ammo(5)
        ui.set_HP(4)
        ui.set_weapon_data(3, NO_FIRE_DELAY)
        ui.submit_shot(test_image_string)
    UserInterface(player).set_location(51.0, 0.0, accuracy=10.0)

    # The door's work, which must survive
    AdminInterface().set_reference_photo(player, test_image_string)
    AdminInterface().set_team_leader(player, True)
    db_session.query(User).filter_by(id=player).update({"identity_slot": 7})

    # An appeal spent, so the budget has visibly moved
    db_session.query(User).filter_by(id=player).update({"appeals_remaining": 1})

    # A scanned item, a circle, a ticker entry and a cue
    item = Item(id=uuid4(), item_type=ItemType.AMMO, data="{}", game_id=game_id)
    item.users.append(db_session.query(User).filter_by(id=player).one())
    db_session.add(item)

    game = db_session.query(Game).filter_by(id=game_id).one()
    game.exclusion_circle_lat = 51.0
    game.exclusion_circle_long = 0.0
    game.exclusion_circle_radius = 1.0
    game.next_event_kind = "drop"
    game.next_event_at = 1_000_000.0
    game.next_event_note = "a medpack"
    db_session.add(TickerEntry(game_id=game_id, message="something happened"))
    db_session.commit()

    return game_id, player, signup


def test_reset_to_start_state_clears_the_sandbox_but_keeps_the_door(
    db_session, game_mid_sandbox
):
    game_id, player, _signup = game_mid_sandbox

    AdminInterface().reset_to_start_state(game_id)

    model = UserInterface(player).get_user_model()
    assert model.num_bullets == 0
    assert model.hit_points == STARTING_HIT_POINTS
    assert (model.shot_damage, model.shot_timeout) == BASIC_WEAPON
    assert model.appeals_remaining == APPEALS_PER_GAME
    assert model.time_of_death is None

    user = db_session.query(User).filter_by(id=player).one()
    assert user.last_shot_at is None

    # Nothing of the sandbox hour is left
    assert db_session.query(Shot).filter_by(game_id=game_id).count() == 0
    assert db_session.query(Item).filter_by(game_id=game_id).count() == 0
    assert db_session.query(TickerEntry).filter_by(game_id=game_id).count() == 0

    game = db_session.query(Game).filter_by(id=game_id).one()
    assert game.exclusion_circle_lat is None
    assert game.exclusion_circle_radius is None
    assert game.next_event_kind is None
    assert game.next_event_at is None
    assert game.next_event_note is None

    # ...but everything the door did survives it
    assert user.reference_photo_base64 is not None
    assert user.identity_slot == 7
    assert user.team_id is not None
    assert user.is_team_leader is True
    assert user.latitude == 51.0


def test_reset_to_start_state_includes_signups_with_no_team(
    db_session, game_mid_sandbox
):
    """reset_game walks the teams, so it cannot see a player who has signed up
    and not yet scanned a team card at the door (roadmap R15)."""
    game_id, _player, signup = game_mid_sandbox

    db_session.query(User).filter_by(id=signup).update(
        {"num_bullets": 9, "hit_points": 1, "appeals_remaining": 0}
    )
    db_session.commit()

    AdminInterface().reset_to_start_state(game_id)

    stray = db_session.query(User).filter_by(id=signup).one()
    assert stray.team_id is None
    assert stray.num_bullets == 0
    assert stray.hit_points == STARTING_HIT_POINTS
    assert (stray.shot_damage, stray.shot_timeout) == BASIC_WEAPON
    assert stray.appeals_remaining == APPEALS_PER_GAME


def test_reset_to_start_state_refuses_while_the_game_is_running(
    db_session, game_mid_sandbox
):
    """The friction is deliberate - see reset_to_start_state's docstring."""
    game_id, player, _signup = game_mid_sandbox
    AdminInterface().set_game_active(game_id, True)

    with pytest.raises(HTTPException) as excinfo:
        AdminInterface().reset_to_start_state(game_id)
    assert excinfo.value.status_code == 400

    # And it refused before touching anything
    assert db_session.query(Shot).filter_by(game_id=game_id).count() == 1
    assert UserInterface(player).get_user_model().num_bullets == 4


def test_setting_the_courier_location_writes_it_to_the_game(db_session, user_in_team):
    game_id = game_of_user(user_in_team)

    AdminInterface().set_courier_location(game_id, 51.5, -0.13, accuracy=8.0)

    game = db_session.query(Game).filter_by(id=game_id).one()
    assert game.courier_lat == 51.5
    assert game.courier_long == -0.13
    assert game.courier_accuracy == 8.0
    assert game.courier_timestamp is not None


def test_clearing_the_courier_puts_the_dot_away(db_session, user_in_team):
    game_id = game_of_user(user_in_team)
    AdminInterface().set_courier_location(game_id, 51.5, -0.13, accuracy=8.0)

    AdminInterface().clear_courier(game_id)

    game = db_session.query(Game).filter_by(id=game_id).one()
    assert game.courier_lat is None
    assert game.courier_long is None
    assert game.courier_timestamp is None
    assert game.courier_accuracy is None


def test_placing_a_drop_puts_a_crate_on_the_map_and_says_so(db_session, user_in_team):
    game_id = game_of_user(user_in_team)

    drop_id = AdminInterface().place_drop(game_id, 51.5, -0.13, radius=0.02)

    drops = UserInterface(user_in_team).get_circles()["drops"]
    assert [(d["id"], d["lat"], d["long"], d["radius"]) for d in drops] == [
        (drop_id, 51.5, -0.13, 0.02)
    ]
    assert drops[0]["time_created"] > 0

    messages = [entry.message for entry in db_session.query(TickerEntry).all()]
    assert "A supply drop has appeared! It's marked in blue" in messages


def test_a_second_drop_does_not_take_the_first_off_the_map(user_in_team):
    """The reason drops are a table at all (M4.3): the single drop_circle_*
    triplet could only hold the newest crate, so putting out a second one
    silently cleared the first while it was still on the ground."""
    game_id = game_of_user(user_in_team)

    first = AdminInterface().place_drop(game_id, 51.5, -0.13, radius=0.02)
    second = AdminInterface().place_drop(game_id, 51.6, -0.14, radius=0.02)

    drops = UserInterface(user_in_team).get_circles()["drops"]
    assert [d["id"] for d in drops] == [first, second]


def test_clearing_a_drop_removes_only_that_one_and_announces_it(
    db_session, user_in_team
):
    game_id = game_of_user(user_in_team)
    first = AdminInterface().place_drop(game_id, 51.5, -0.13, radius=0.02)
    second = AdminInterface().place_drop(game_id, 51.6, -0.14, radius=0.02)

    AdminInterface().clear_drop(first)

    assert [d.id for d in AdminInterface().get_drops(game_id)] == [second]
    assert [d["id"] for d in UserInterface(user_in_team).get_circles()["drops"]] == [
        second
    ]
    assert db_session.query(Drop).count() == 1

    messages = [entry.message for entry in db_session.query(TickerEntry).all()]
    assert "The supply drop has been claimed!" in messages


def test_clearing_a_drop_that_is_already_gone_is_a_404(user_in_team):
    """Two couriers on the same list, or one who double-taps a reload apart."""
    game_id = game_of_user(user_in_team)
    drop_id = AdminInterface().place_drop(game_id, 51.5, -0.13, radius=0.02)
    AdminInterface().clear_drop(drop_id)

    with pytest.raises(HTTPException) as excinfo:
        AdminInterface().clear_drop(drop_id)
    assert excinfo.value.status_code == 404


def test_resetting_to_the_start_state_clears_the_crates(db_session, user_in_team):
    game_id = game_of_user(user_in_team)
    AdminInterface().place_drop(game_id, 51.5, -0.13, radius=0.02)
    AdminInterface().set_game_active(game_id, False)

    AdminInterface().reset_to_start_state(game_id)

    assert db_session.query(Drop).count() == 0


def test_the_courier_fan_out_is_throttled_but_the_position_is_not(
    db_session, user_in_team, mocker
):
    """A courier posts about once a second and every announcement wakes every
    player's circle stream, so the announcement is throttled - but the
    position itself is written every time, or the map would lag the throttle
    as well as the fix."""
    game_id = game_of_user(user_in_team)
    announce = mocker.patch("backend.admin_interface.trigger_circle_update")

    AdminInterface().set_courier_location(game_id, 51.5, -0.13)
    assert announce.call_count == 1

    # Three more inside the window: written, not announced
    for offset in (0.0001, 0.0002, 0.0003):
        AdminInterface().set_courier_location(game_id, 51.5 + offset, -0.13)
    assert announce.call_count == 1

    game = db_session.query(Game).filter_by(id=game_id).one()
    assert game.courier_lat == pytest.approx(51.5003)

    # Once the window is past, the next fix is announced again. Backdating the
    # recorded announcement rather than patching time.time: that patch is
    # process-wide (admin_interface.time *is* the stdlib module), and a clock
    # moved under the session machinery breaks tests that run after this one.
    admin_interface._courier_announced_at[game_id] -= (
        admin_interface.COURIER_ANNOUNCE_INTERVAL_S + 1
    )
    AdminInterface().set_courier_location(game_id, 51.6, -0.13)
    assert announce.call_count == 2


def test_clearing_the_courier_always_announces(user_in_team, mocker):
    """A dot left on the map after the crate is down is the one staleness that
    actually misleads, so the clear ignores the throttle."""
    game_id = game_of_user(user_in_team)
    AdminInterface().set_courier_location(game_id, 51.5, -0.13)

    announce = mocker.patch("backend.admin_interface.trigger_circle_update")
    AdminInterface().clear_courier(game_id)

    assert announce.call_count == 1
