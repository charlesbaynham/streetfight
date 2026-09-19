import pytest
from fastapi import HTTPException

from backend.admin_interface import AdminInterface
from backend.admin_interface import CircleTypes
from backend.circles import CIRCLE_PLAN
from backend.user_interface import UserInterface
from backend.venues import ACTIVE_VENUE
from backend.venues import landmarks_from_env


def test_circles_start_empty(user_in_team):
    ui = UserInterface(user_in_team)

    for name, value in ui.get_circles().items():
        # The courier's crates are a list rather than a triplet of
        # coordinates (M4.3), so "nothing there" is an empty one
        expected = [] if name == "drops" else None
        assert value == expected


def circles_of(user_id):
    return UserInterface(user_id).get_circles()


def test_placing_the_next_circle_shows_it_to_nobody(user_in_team):
    """M6.2: it exists, but it is not announced until it is cued - so a player
    with no early-warning card is sent nulls, which the map draws nothing
    for."""
    game_id = UserInterface(user_in_team).get_game_id()
    AdminInterface().set_circles(game_id, CircleTypes.NEXT, 51.5, -0.1, 0.42)

    circles = circles_of(user_in_team)
    assert circles["next_circle_lat"] is None
    assert circles["next_circle_long"] is None
    assert circles["next_circle_radius"] is None


def test_cueing_the_circle_is_what_announces_it(user_in_team):
    game_id = UserInterface(user_in_team).get_game_id()
    AdminInterface().set_circles(game_id, CircleTypes.NEXT, 51.5, -0.1, 0.42)

    AdminInterface().cue_next_event(game_id, "circle", seconds=600)

    circles = circles_of(user_in_team)
    assert circles["next_circle_lat"] == 51.5
    assert circles["next_circle_radius"] == 0.42


def test_moving_the_circle_mid_countdown_takes_it_off_every_phone_again(user_in_team):
    """Placing NEXT always makes it private again: a circle everybody can see
    must not be left drawn somewhere the admin has just moved it from."""
    game_id = UserInterface(user_in_team).get_game_id()
    AdminInterface().set_circles(game_id, CircleTypes.NEXT, 51.5, -0.1, 0.42)
    AdminInterface().cue_next_event(game_id, "circle", seconds=600)

    AdminInterface().set_circles(game_id, CircleTypes.NEXT, 51.6, -0.2, 0.3)

    assert circles_of(user_in_team)["next_circle_lat"] is None


def test_setting_both_circles_at_once_hides_nothing(user_in_team):
    """BOTH puts the next circle exactly where the exclusion circle everybody
    can already see is, so there is nothing left to keep back."""
    game_id = UserInterface(user_in_team).get_game_id()
    AdminInterface().set_circles(game_id, CircleTypes.BOTH, 51.5, -0.1, 0.42)

    assert circles_of(user_in_team)["next_circle_lat"] == 51.5


def test_the_admin_sees_the_next_circle_whether_or_not_it_is_public(user_in_team):
    """The filtering is on the player-facing endpoint only - the admin map and
    the spectator screen read the columns off a GameModel."""
    game_id = UserInterface(user_in_team).get_game_id()
    AdminInterface().set_circles(game_id, CircleTypes.NEXT, 51.5, -0.1, 0.42)

    game = AdminInterface().get_game_model(game_id)
    assert game.next_circle_lat == 51.5
    assert game.next_circle_public is False


def test_promoting_the_next_circle_makes_it_the_one_to_be_inside(user_in_team):
    game_id = UserInterface(user_in_team).get_game_id()
    AdminInterface().set_circles(game_id, CircleTypes.NEXT, 51.5, -0.1, 0.42)

    assert AdminInterface().promote_next_circle(game_id) is True

    circles = circles_of(user_in_team)
    assert circles["exclusion_circle_lat"] == 51.5
    assert circles["exclusion_circle_long"] == -0.1
    assert circles["exclusion_circle_radius"] == 0.42
    # The next circle is spent: what is coming after this one has not been
    # announced yet, and leaving the old one drawn would say it had.
    assert circles["next_circle_lat"] is None
    assert circles["next_circle_radius"] is None


def test_promoting_with_no_next_circle_leaves_the_play_area_alone(user_in_team):
    """An admin who cleared the next circle while the clock ran must not get
    the exclusion circle blanked out from under thirty players."""
    game_id = UserInterface(user_in_team).get_game_id()
    AdminInterface().set_circles(game_id, CircleTypes.EXCLUSION, 51.5, -0.1, 0.7)

    assert AdminInterface().promote_next_circle(game_id) is False

    assert circles_of(user_in_team)["exclusion_circle_radius"] == 0.7


def test_promoting_clears_the_countdown_that_asked_for_it(user_in_team):
    game_id = UserInterface(user_in_team).get_game_id()
    AdminInterface().set_circles(game_id, CircleTypes.NEXT, 51.5, -0.1, 0.42)
    AdminInterface().cue_next_event(game_id, "circle", seconds=600)

    AdminInterface().promote_next_circle(game_id)

    assert UserInterface(user_in_team).get_user_model().next_event_at is None


def test_a_circle_cue_reaching_zero_closes_the_circle(user_in_team):
    game_id = UserInterface(user_in_team).get_game_id()
    AdminInterface().set_circles(game_id, CircleTypes.NEXT, 51.5, -0.1, 0.42)
    deadline = AdminInterface().cue_next_event(game_id, "circle", seconds=600)

    AdminInterface().fire_next_event(game_id, expected_at=deadline)

    assert circles_of(user_in_team)["exclusion_circle_radius"] == 0.42
    assert UserInterface(user_in_team).get_user_model().next_event_at is None


def test_nobody_is_walking_a_crate_to_begin_with(user_in_team):
    assert circles_of(user_in_team)["courier"] is None


def test_the_courier_rides_out_with_the_circles(user_in_team):
    """One payload and one SSE event for both: the courier's dot arrives on
    the same refetch the circles do (M4.2)."""
    game_id = UserInterface(user_in_team).get_game_id()
    AdminInterface().set_courier_location(game_id, 51.5, -0.1, accuracy=8)

    courier = circles_of(user_in_team)["courier"]
    assert courier["lat"] == 51.5
    assert courier["long"] == -0.1
    assert courier["accuracy"] == 8
    assert courier["timestamp"] is not None


def test_a_courier_who_has_stopped_is_nobody(user_in_team):
    game_id = UserInterface(user_in_team).get_game_id()
    AdminInterface().set_courier_location(game_id, 51.5, -0.1)

    AdminInterface().clear_courier(game_id)

    assert circles_of(user_in_team)["courier"] is None


# ---------------------------------------------------------------------------
# The circle plan (backend/circles.py)
# ---------------------------------------------------------------------------


PLANNED_RADII_KM = (0.70, 0.42, 0.18, 0.05)


@pytest.fixture
def planned_circles(monkeypatch):
    """A venue that knows where the plan's circles are, and how big.

    Both halves arrive from the environment (`LANDMARK_CIRCLE0=...`,
    `CIRCLE_RADIUS_CIRCLE0=...`) and are deliberately not committed, so a test
    that wants them has to supply them.
    """
    landmarks = dict(ACTIVE_VENUE.landmarks)
    landmarks.update(
        {
            "CIRCLE0": (51.50, -0.10),
            "CIRCLE1": (51.51, -0.11),
            "CIRCLE2": (51.52, -0.12),
            "CIRCLE3": (51.53, -0.13),
        }
    )
    monkeypatch.setattr(ACTIVE_VENUE, "landmarks", landmarks)
    for name, radius_km in zip(CIRCLE_PLAN, PLANNED_RADII_KM):
        monkeypatch.setenv("CIRCLE_RADIUS_" + name, str(radius_km))


def test_the_first_planned_circle_is_placed_by_the_reset(user_in_team, planned_circles):
    """The one mistake the plan exists to prevent: arriving at the first
    countdown with NEXT empty, so nobody's early-warning card is worth
    anything."""
    game_id = UserInterface(user_in_team).get_game_id()
    AdminInterface().set_game_active(game_id, False)

    AdminInterface().reset_to_start_state(game_id)

    game = AdminInterface().get_game_model(game_id)
    assert (game.next_circle_lat, game.next_circle_long) == (51.50, -0.10)
    assert game.next_circle_radius == PLANNED_RADII_KM[0]
    # Placed, but nobody has been told
    assert game.next_circle_public is False
    assert circles_of(user_in_team)["next_circle_lat"] is None


def test_the_dev_reset_clears_the_play_area_too(user_in_team, planned_circles):
    """`reset_game` is a game starting again, so the play area starts again:
    every circle goes, every crate on the ground goes with it, and the plan is
    back at its first entry with that circle privately placed."""
    game_id = UserInterface(user_in_team).get_game_id()
    AdminInterface().set_circles(game_id, CircleTypes.EXCLUSION, 51.9, -0.9, 0.3)
    AdminInterface().set_circles(game_id, CircleTypes.DROP, 51.8, -0.8, 0.02)
    AdminInterface().place_drop(game_id, 51.7, -0.7, 0.02)

    AdminInterface().reset_game(game_id)

    game = AdminInterface().get_game_model(game_id)
    assert game.exclusion_circle_lat is None
    assert game.drop_circle_lat is None
    assert AdminInterface().get_drops(game_id) == []
    # Back to the top of the plan, placed but not yet announced
    assert game.circle_plan_index == 0
    assert (game.next_circle_lat, game.next_circle_long) == (51.50, -0.10)
    assert game.next_circle_public is False


def test_closing_a_circle_arms_the_one_after_it(user_in_team, planned_circles):
    game_id = UserInterface(user_in_team).get_game_id()
    AdminInterface().set_game_active(game_id, False)
    AdminInterface().reset_to_start_state(game_id)

    AdminInterface().promote_next_circle(game_id)

    game = AdminInterface().get_game_model(game_id)
    assert game.exclusion_circle_lat == 51.50
    assert game.next_circle_lat == 51.51
    assert game.circle_plan_index == 1
    assert game.next_circle_public is False


def test_the_plan_running_out_leaves_the_last_circle_standing(
    user_in_team, planned_circles
):
    game_id = UserInterface(user_in_team).get_game_id()
    AdminInterface().set_game_active(game_id, False)
    AdminInterface().reset_to_start_state(game_id)

    for _ in range(len(CIRCLE_PLAN)):
        AdminInterface().promote_next_circle(game_id)

    game = AdminInterface().get_game_model(game_id)
    assert game.exclusion_circle_lat == 51.53
    assert game.next_circle_lat is None


def test_a_circle_the_environment_never_supplied_is_left_to_the_admin(
    user_in_team, monkeypatch
):
    """No `LANDMARK_CIRCLE0` anywhere - which is the state of every checkout,
    since the real coordinates are not committed. The game must still start."""
    monkeypatch.setattr(
        ACTIVE_VENUE,
        "landmarks",
        {
            name: point
            for name, point in ACTIVE_VENUE.landmarks.items()
            if not name.startswith("CIRCLE")
        },
    )
    game_id = UserInterface(user_in_team).get_game_id()
    AdminInterface().set_game_active(game_id, False)

    AdminInterface().reset_to_start_state(game_id)

    assert AdminInterface().get_game_model(game_id).next_circle_lat is None


def test_a_circle_with_no_radius_is_left_to_the_admin_too(
    user_in_team, planned_circles, monkeypatch
):
    """Half a plan entry is not an entry: a circle whose coordinates are known
    but whose `CIRCLE_RADIUS_<name>` is unset has no size to be placed at."""
    monkeypatch.delenv("CIRCLE_RADIUS_" + CIRCLE_PLAN[0])
    game_id = UserInterface(user_in_team).get_game_id()
    AdminInterface().set_game_active(game_id, False)

    AdminInterface().reset_to_start_state(game_id)

    assert AdminInterface().get_game_model(game_id).next_circle_lat is None


def test_starting_a_game_arms_the_plan_but_never_overrides_a_placed_circle(
    user_in_team, planned_circles
):
    game_id = UserInterface(user_in_team).get_game_id()
    AdminInterface().set_circles(game_id, CircleTypes.NEXT, 51.9, -0.9, 0.3)

    AdminInterface().set_game_active(game_id, True)

    assert AdminInterface().get_game_model(game_id).next_circle_lat == 51.9


def test_skipping_a_circle_carries_the_plan_on_from_there(
    user_in_team, planned_circles
):
    game_id = UserInterface(user_in_team).get_game_id()

    AdminInterface().arm_planned_circle(game_id, index=2)

    game = AdminInterface().get_game_model(game_id)
    assert game.next_circle_lat == 51.52
    assert game.circle_plan_index == 2

    AdminInterface().promote_next_circle(game_id)
    assert AdminInterface().get_game_model(game_id).next_circle_lat == 51.53


def test_landmarks_come_out_of_the_environment_one_variable_at_a_time():
    """`LANDMARK_<NAME>="<lat>,<long>"`, which is how the circles and later the
    drops stay out of a public repository."""
    landmarks = landmarks_from_env(
        {
            "LANDMARK_CIRCLE0": "51.4958,-0.1309",
            "LANDMARK_DROP_BRIDGE": "51.4112, -0.3105",
            "WEBSITE_URL": "https://example.com",
        }
    )

    assert landmarks == {
        "CIRCLE0": (51.4958, -0.1309),
        "DROP_BRIDGE": (51.4112, -0.3105),
    }


def test_a_mistyped_landmark_is_skipped_rather_than_stopping_the_server():
    """Read at import time on a machine running a game: a typo in a secrets
    file must cost one circle, not the evening."""
    assert landmarks_from_env({"LANDMARK_CIRCLE0": "51.4958 -0.1309"}) == {}


def test_stepping_back_puts_the_play_area_back(user_in_team, planned_circles):
    """A circle that closed by mistake: the pointer, NEXT and the exclusion
    circle all go back one, so nobody is left held inside a circle that was
    never meant to close."""
    game_id = UserInterface(user_in_team).get_game_id()
    AdminInterface().arm_planned_circle(game_id, index=1)
    AdminInterface().promote_next_circle(game_id)

    # CIRCLE1 has closed, and CIRCLE2 is armed behind it
    game = AdminInterface().get_game_model(game_id)
    assert (game.exclusion_circle_lat, game.circle_plan_index) == (51.51, 2)

    AdminInterface().step_back_circle_plan(game_id)

    game = AdminInterface().get_game_model(game_id)
    assert game.circle_plan_index == 1
    assert game.next_circle_lat == 51.51
    assert game.next_circle_public is False
    # ...and the circle people are held inside is the one before it again
    assert game.exclusion_circle_lat == 51.50
    assert game.exclusion_circle_radius == PLANNED_RADII_KM[0]


def test_stepping_back_to_the_first_circle_reopens_the_whole_venue(
    user_in_team, planned_circles
):
    """There is no circle before the first one, so there is nothing to hold
    people inside: the exclusion circle goes rather than staying put."""
    game_id = UserInterface(user_in_team).get_game_id()
    AdminInterface().arm_planned_circle(game_id, index=0)
    AdminInterface().promote_next_circle(game_id)

    AdminInterface().step_back_circle_plan(game_id)

    game = AdminInterface().get_game_model(game_id)
    assert game.circle_plan_index == 0
    assert game.next_circle_lat == 51.50
    assert game.exclusion_circle_lat is None


def test_stepping_back_from_the_start_of_the_plan_refuses(
    user_in_team, planned_circles
):
    """Nothing to undo, so the button says so rather than silently arming the
    circle that is already armed."""
    game_id = UserInterface(user_in_team).get_game_id()
    AdminInterface().arm_planned_circle(game_id, index=0)

    with pytest.raises(HTTPException) as excinfo:
        AdminInterface().step_back_circle_plan(game_id)

    assert excinfo.value.status_code == 400


def test_stepping_back_tells_the_players(user_in_team, planned_circles):
    game_id = UserInterface(user_in_team).get_game_id()
    AdminInterface().arm_planned_circle(game_id, index=1)
    AdminInterface().promote_next_circle(game_id)

    AdminInterface().step_back_circle_plan(game_id)

    messages = UserInterface(user_in_team).get_messages(num=9999)
    assert any("closed by mistake" in message[1] for message in messages)
