"""The essay's figures (``GET /api/how_it_works``).

The page these feed explains the identity scheme to the players wearing it, so
the things worth testing are the ones that would let it lie: the grid's shape,
and the fact that a reader's neighbours arrive without names attached.
"""

import pytest

from backend.admin_interface import AdminInterface
from backend.how_it_works import NEIGHBOURS_SHOWN
from backend.how_it_works import codeword_grid
from backend.identity.config import default_scheme
from backend.model import User
from backend.user_interface import UserInterface


@pytest.fixture(autouse=True)
def mock_asyncio_tasks(mocker):
    mocker.patch("backend.asyncio_triggers.schedule_update_event")


def set_slot(db_session, user_id, slot):
    db_session.query(User).filter_by(id=user_id).update({"identity_slot": slot})
    db_session.commit()


def add_player(db_session, user_factory, team_id, slot):
    user_id = user_factory()
    with UserInterface(user_id) as ui:
        ui.join_team(team_id)
    set_slot(db_session, user_id, slot)
    return user_id


def test_grid_has_exactly_one_outfit_per_row_and_column():
    """The figure's whole point. Because the code is MDS with ``k = 2``, any
    two garments determine the other two, so no row and no column carries two
    codewords -- a claim about the scheme, not about the drawing.
    """
    scheme = default_scheme()
    grid = codeword_grid(scheme)

    assert len(grid["cells"]) == scheme.capacity
    assert grid["size"] ** 2 == grid["total"]
    assert len({cell["row"] for cell in grid["cells"]}) == len(grid["cells"])
    assert len({cell["col"] for cell in grid["cells"]}) == len(grid["cells"])


def test_grid_marks_the_withheld_slot_as_unusable():
    grid = codeword_grid(default_scheme())
    unusable = [cell for cell in grid["cells"] if not cell["usable"]]

    assert [cell["slot"] for cell in unusable] == [0]
    assert len(grid["cells"]) - len(unusable) == len(default_scheme().usable_slots())


def test_essay_serves_the_scheme_to_a_reader_with_no_outfit(api_client):
    response = api_client.get("/api/how_it_works")
    assert response.is_success

    body = response.json()
    scheme = default_scheme()
    assert body["scheme"]["combinations"] == scheme.code.q**scheme.code.n
    assert body["scheme"]["usable"] == len(scheme.usable_slots())
    assert body["you"] is None
    assert body["neighbours"] == []


def test_essay_tells_a_player_what_they_will_be_handed(
    db_session, api_client, api_user_id, one_team, user_factory
):
    with UserInterface(api_user_id) as ui:
        ui.join_team(one_team)
    set_slot(db_session, api_user_id, 5)

    body = api_client.get("/api/how_it_works").json()

    assert body["you"]["slot"] == 5
    assert body["you"]["provided"] == ["hat", "armbands"]
    handed = {
        name: entry["colour"]
        for name, entry in body["you"]["appearance"].items()
        if entry["provided"]
    }
    assert set(handed) == {"hat", "armbands"}
    assert all(colour for colour in handed.values())
    assert body["you"]["row"] is not None and body["you"]["col"] is not None


def test_neighbours_are_nearest_first_and_named(
    db_session, api_client, api_user_id, one_team, user_factory
):
    """Who is dressed most like the reader, closest first. Named on purpose -
    see ``how_it_works._neighbours``.
    """
    with UserInterface(api_user_id) as ui:
        ui.join_team(one_team)
    set_slot(db_session, api_user_id, 5)
    others = [
        add_player(db_session, user_factory, one_team, slot) for slot in (6, 7, 8, 9)
    ]

    body = api_client.get("/api/how_it_works").json()
    neighbours = body["neighbours"]

    assert len(neighbours) == NEIGHBOURS_SHOWN
    assert [n["distance"] for n in neighbours] == sorted(
        n["distance"] for n in neighbours
    )
    assert all(
        n["distance"] >= default_scheme().code.min_distance() for n in neighbours
    )

    names = {AdminInterface().get_user_model(other).name for other in others}
    assert {n["name"] for n in neighbours} <= names
    assert all(n["name"] for n in neighbours)


def test_the_page_is_told_how_many_players_share_the_nearest_distance(
    db_session, api_client, api_user_id, one_team, user_factory
):
    """Half of any codeword's neighbours sit at exactly the minimum distance
    (24 of the other 48 here), so the three names shown are a sample of a tie.
    The page has to be able to say how big that tie is, or it claims a ranking
    that is not there.
    """
    with UserInterface(api_user_id) as ui:
        ui.join_team(one_team)
    set_slot(db_session, api_user_id, 5)
    # Slots 9, 10 and 11 are each three garments from slot 5; slot 6 is four.
    for slot in (9, 10, 11, 6):
        add_player(db_session, user_factory, one_team, slot)

    body = api_client.get("/api/how_it_works").json()

    assert body["closest_count"] == 3
    assert [n["distance"] for n in body["neighbours"]] == [3, 3, 3]
