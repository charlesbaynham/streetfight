"""The printable map poster (backend/map_poster.py)."""

import re
from pathlib import Path

import pytest
from PIL import Image

from backend import map_poster
from backend.generate_pub_pages import _mm
from backend.venues import ACTIVE_VENUE
from backend.venues import VENUES


def page_count(pdf: bytes) -> int:
    return pdf.count(b"/Type /Page\n")


def test_the_poster_is_one_page_of_the_asked_for_paper():
    for size, (width_mm, height_mm) in map_poster.PAGE_SIZES_MM.items():
        page = map_poster.render_poster(size=size)
        assert page.size == (_mm(width_mm), _mm(height_mm))
        assert page_count(map_poster.render_pdf(size=size)) == 1


def test_an_unknown_paper_size_is_refused():
    """Rather than silently drawing an A3 when somebody asked for Letter."""
    with pytest.raises(ValueError):
        map_poster.render_poster(size="A5")


@pytest.mark.parametrize("venue_name", list(VENUES))
def test_every_venue_can_print_its_map(venue_name):
    """The image lives in react-ui/src/images/ because webpack has to bundle
    it, and the deployed backend is a wheel built from `backend*` alone - so
    backend/map_images/ carries a symlink to it. A venue whose map is not
    there renders a poster with no map on it, discovered at print time."""
    venue = VENUES[venue_name]
    path = map_poster.map_image_path(venue.map.image)

    assert path.exists()

    # The venue's width_px is its own unit rather than the file's pixel count
    # - Kingston says 2273 for a 2048 px image - so what has to agree is the
    # shape. A map whose aspect does not match its venue is covering a
    # different patch of ground than the reference points claim, and every
    # marker on the poster is then in the wrong street.
    with Image.open(path) as image:
        assert image.width / image.height == pytest.approx(
            venue.map.width_px / venue.map.height_px, rel=0.01
        )


MAP_IMAGES_JS = Path(__file__, "../../react-ui/src/mapImages.js").resolve()


def bundled_map_images() -> dict:
    """What react-ui/src/mapImages.js bundles, keyed as the venues key it:
    `import westminster from "./images/map_westminster.png"` and a
    `MAP_IMAGES = { ..., westminster, koyao_resort: koyaoResort }` entry."""
    source = MAP_IMAGES_JS.read_text()
    imports = dict(re.findall(r'import (\w+) from "\./images/([^"]+)"', source))
    table = re.search(r"MAP_IMAGES = \{(.*?)\}", source, re.S).group(1)
    keyed = {}
    for entry in filter(None, (e.strip() for e in table.split(","))):
        key, _, name = entry.partition(":")
        keyed[key.strip()] = imports[(name or key).strip()]
    return keyed


@pytest.mark.parametrize("venue_name", list(VENUES))
def test_the_backend_map_is_the_file_the_frontend_bundles(venue_name):
    """The symlink in backend/map_images/ has to follow the file mapImages.js
    imports: renaming map_westminster.jpg to .png left the link dangling,
    and every poster download on the night before the game failed with a
    500. The glob in map_image_path still matched the dead link, so this
    checks the target by name rather than trusting exists()."""
    key = VENUES[venue_name].map.image
    expected = (MAP_IMAGES_JS.parent / "images" / bundled_map_images()[key]).resolve()

    assert map_poster.map_image_path(key).resolve() == expected


def test_a_dangling_symlink_is_reported_as_a_missing_map(tmp_path, monkeypatch):
    (tmp_path / "westminster.jpg").symlink_to(tmp_path / "gone.jpg")
    monkeypatch.setattr(map_poster, "MAP_IMAGE_DIR", tmp_path)

    with pytest.raises(FileNotFoundError, match="no map image"):
        map_poster.map_image_path("westminster")


@pytest.mark.parametrize("venue_name", list(VENUES))
def test_the_legend_is_the_venues_own_landmarks(venue_name):
    """The whole point of building this from ACTIVE_VENUE: a pub added to
    venues.py appears on the poster, and the poster cannot name one the
    admin's circle dropdown does not have."""
    venue = VENUES[venue_name]
    named = map_poster.poster_landmarks(venue)

    assert set(named) <= set(venue.landmarks)
    # In the venue's own order, which is geographic: the numbers should walk
    # across the map rather than hop about it.
    assert named == [name for name in venue.landmarks if name in set(named)]


def test_the_legend_leaves_off_where_the_game_will_put_things():
    """Circles and drops are landmarks too, and this poster goes on a wall
    players read. Kingston has both, so it is the venue that proves it."""
    kingston = VENUES["kingston"]
    named = map_poster.poster_landmarks(kingston)

    assert "CIRCLE1" in kingston.landmarks
    assert "DROP_BRIDGE" in kingston.landmarks
    assert not [
        name for name in named if name.startswith(("CIRCLE", "DROP_", "COURIER"))
    ]
    assert "FORESTERS" in named


def test_a_landmark_lands_where_the_venue_says_it_is():
    """The markers are projected through the venue's own bounds, so this is
    the same sum the frontend does to draw a player's dot.

    Compass relationships rather than absolute positions: the crop is sized to
    fit the markers rather than centred on any one of them (M0.6), so nothing
    sits at a memorable fraction any more, but Big Ben is still north-east of
    House Absolute and Windsor Castle still west of it - which is what pins
    both axes and their sign.
    """
    westminster = VENUES["westminster"]
    names = map_poster.poster_landmarks(westminster)
    positions = dict(zip(names, map_poster._marker_positions(westminster, names)))

    house_x, house_y = positions["HOUSE_ABSOLUTE"]

    big_ben_x, big_ben_y = positions["BIG_BEN"]
    assert big_ben_x > house_x  # east
    assert big_ben_y < house_y  # north

    windsor_x, windsor_y = positions["WINDSOR_CASTLE"]
    assert windsor_x < house_x  # west
    assert positions["ROYAL_OAK"][1] > house_y  # south


def test_every_landmark_is_inside_the_crop_with_room_to_draw_it():
    """The crop is sized to fit the markers, so this is the property that
    sizing bought: shrink it and a pub falls off the poster."""
    westminster = VENUES["westminster"]
    names = map_poster.poster_landmarks(westminster)
    positions = map_poster._marker_positions(westminster, names)

    for name, (x, y) in zip(names, positions):
        assert 0.05 < x < 0.95, f"{name} is too close to an edge to label"
        assert 0.05 < y < 0.95, f"{name} is too close to an edge to label"


def test_a_landmark_key_is_written_the_way_the_pub_is():
    assert map_poster.legend_label("MARQUIS_OF_GRANBY") == "Marquis of Granby"
    assert map_poster.legend_label("ADAM_AND_EVE") == "Adam and Eve"
    assert map_poster.legend_label("THE_SPEAKER") == "The Speaker"


def test_the_route_serves_a_pdf(admin_api_client):
    response = admin_api_client.get("/api/admin_map_poster_pdf", params={"size": "A4"})

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert page_count(response.content) == 1


def test_the_route_refuses_paper_it_cannot_draw(admin_api_client):
    response = admin_api_client.get("/api/admin_map_poster_pdf", params={"size": "A5"})

    assert response.status_code == 400


def test_the_active_venue_prints():
    """`npm run mapgen` and the route draw the same poster, so this is the
    one that would catch an ACTIVE_VENUE the poster cannot render at all."""
    assert len(map_poster.poster_landmarks(ACTIVE_VENUE)) >= 1
    assert map_poster.render_pdf().startswith(b"%PDF")
