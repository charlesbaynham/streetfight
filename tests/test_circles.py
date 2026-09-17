from backend.admin_interface import AdminInterface
from backend.admin_interface import CircleTypes
from backend.user_interface import UserInterface


def test_circles_start_empty(user_in_team):
    ui = UserInterface(user_in_team)

    for name, value in ui.get_circles().items():
        assert value is None


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
