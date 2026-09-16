import os
from uuid import uuid4 as get_uuid

import pytest
import qrcode

os.environ["SECRET_KEY"] = "test_secret_key"
os.environ.setdefault("WEBSITE_URL", "https://example.com")

from backend import team_cards  # noqa: E402
from backend.generate_pub_pages import DPI  # noqa: E402
from backend.generate_pub_pages import QUIET_MODULES  # noqa: E402
from backend.generate_pub_pages import make_qr  # noqa: E402
from backend.join_codes import make_team_join_url  # noqa: E402


@pytest.fixture(autouse=True)
def mock_asyncio_tasks(mocker):
    mocker.patch("backend.asyncio_triggers.schedule_update_event")


def a_url():
    return make_team_join_url(get_uuid(), get_uuid())


def page_count(pdf: bytes) -> int:
    return pdf.count(b"/Type /Page\n")


def test_a_card_is_a4_portrait():
    page = team_cards.render_team_card("Team Alpha", a_url())
    assert page.size == (team_cards._mm(210), team_cards._mm(297))


def test_the_code_is_large_enough_to_scan_at_the_door():
    """The same thresholds the pub pages hold themselves to."""
    url = a_url()
    qr = make_qr(url, team_cards.QR_SIDE)

    matrix = qrcode.QRCode(error_correction=qrcode.ERROR_CORRECT_M, border=0)
    matrix.add_data(url)
    matrix.make(fit=True)
    module_px = qr.width / matrix.modules_count

    assert qr.width / DPI * 25.4 > 38, "code too small to read at the door"
    assert module_px / DPI * 25.4 > 0.55, "modules too fine to print reliably"
    # The white plate around the code is its quiet zone
    assert team_cards.QR_PLATE >= QUIET_MODULES * module_px


def test_a_long_team_name_wraps_and_still_fits_inside_the_rule():
    width = team_cards.PAGE_W - 2 * team_cards.INNER

    font, lines = team_cards.team_name_lines("Alpha")
    assert lines == ["ALPHA"]

    name = "The Westminster Irregulars and Auxiliary Volunteer Reserve"
    font, lines = team_cards.team_name_lines(name)
    assert len(lines) > 1
    assert " ".join(lines) == name.upper()
    assert all(font.getlength(line) <= width for line in lines)


def test_render_pdf_writes_one_page_per_team():
    pdf = team_cards.render_pdf([("Alpha", a_url()), ("Bravo", a_url())])
    assert pdf.startswith(b"%PDF")
    assert page_count(pdf) == 2


def test_render_pdf_refuses_an_empty_run():
    with pytest.raises(ValueError):
        team_cards.render_pdf([])


def test_the_endpoint_streams_a_pdf_with_a_page_per_team(
    admin_api_client, one_game, team_factory
):
    team_factory()
    team_factory()
    team_factory()

    response = admin_api_client.get(f"/api/admin_team_cards_pdf?game_id={one_game}")

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert "team_cards.pdf" in response.headers["content-disposition"]
    assert page_count(response.content) == 3


def test_the_endpoint_needs_admin_auth(api_client, one_game):
    response = api_client.get(f"/api/admin_team_cards_pdf?game_id={one_game}")
    assert response.status_code in (401, 403)


def test_the_endpoint_needs_teams(admin_api_client, one_game):
    # No teams yet: build_join_codes' own complaint, as a 400
    response = admin_api_client.get(f"/api/admin_team_cards_pdf?game_id={one_game}")
    assert response.status_code == 400
