import pytest

from backend.user_interface import UserInterface
from backend.venues import ACTIVE_VENUE
from backend.venues import VENUES


@pytest.mark.parametrize("venue_name", list(VENUES))
def test_landmarks_are_on_the_map(venue_name):
    """A landmark outside its own map can't be seen, and a circle placed there
    is invisible - so this catches a mistyped coordinate, or a map swapped for
    one covering a different patch of ground."""
    venue = VENUES[venue_name]
    bounds = venue.map.bounds

    off_map = {
        name: coords
        for name, coords in venue.landmarks.items()
        if not bounds.contains(*coords)
    }
    assert off_map == {}


@pytest.mark.parametrize("venue_name", list(VENUES))
def test_map_is_north_up_and_the_right_way_round(venue_name):
    bounds = VENUES[venue_name].map.bounds
    assert bounds.north > bounds.south
    assert bounds.east > bounds.west


def test_get_venue(api_client):
    response = api_client.get("/api/get_venue")
    assert response.status_code == 200

    venue = response.json()
    assert venue["name"] == ACTIVE_VENUE.name
    assert venue["map"]["image"] == ACTIVE_VENUE.map.image
    assert set(venue["landmarks"]) == set(ACTIVE_VENUE.landmarks)


def test_landmark_list_is_the_active_venues(admin_api_client):
    response = admin_api_client.get("/api/admin_get_landmarks")
    assert response.status_code == 200
    assert response.json() == list(ACTIVE_VENUE.landmarks)


def test_set_circle_at_landmark(admin_api_client, user_in_team, one_game):
    """The landmarks the admin picks from and the coordinates a circle ends up
    at come from the same venue."""
    landmark, (lat, long) = next(iter(ACTIVE_VENUE.landmarks.items()))

    response = admin_api_client.post(
        "/api/admin_set_circle_by_location",
        params={
            "game_id": str(one_game),
            "name": "EXCLUSION",
            "location": landmark,
            "radius_km": 0.05,
        },
    )
    assert response.status_code == 200

    circles = UserInterface(user_in_team).get_circles()
    assert circles["exclusion_circle_lat"] == pytest.approx(lat)
    assert circles["exclusion_circle_long"] == pytest.approx(long)
