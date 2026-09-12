import os

import numpy as np
import pytest
from click.testing import CliRunner
from fastapi.exceptions import HTTPException

os.environ["SECRET_KEY"] = "test_secret_key"
os.environ.setdefault("WEBSITE_URL", "https://example.com")

from backend import generate_pub_pages as pub  # noqa: E402
from backend.items import ItemModel  # noqa: E402
from backend.user_interface import UserInterface  # noqa: E402


@pytest.fixture(autouse=True)
def mock_asyncio_tasks(mocker):
    mocker.patch("backend.asyncio_triggers.schedule_update_event")


# The QR is placed by measurement rather than by eye, so the measurements are
# what the tests check. A re-drawn artwork should fail here rather than at the
# printer.


def test_qr_pocket_is_free_of_artwork():
    assert pub.pocket_ink_pixels() == 0


def test_qr_is_large_enough_to_scan_across_a_room():
    import qrcode

    url = pub.mint_pub_items(1)[0]
    _, _, (_, _, pocket) = pub._layout()
    qr = pub.make_qr(url, pocket)

    matrix = qrcode.QRCode(error_correction=qrcode.ERROR_CORRECT_M, border=0)
    matrix.add_data(url)
    matrix.make(fit=True)
    module_px = qr.width / matrix.modules_count

    assert qr.width / pub.DPI * 25.4 > 38, "code too small to read across a pub"
    assert module_px / pub.DPI * 25.4 > 0.55, "modules too fine to print reliably"
    # The code carries no border of its own: the pocket supplies the quiet zone
    assert (pocket - qr.width) / 2 >= pub.QUIET_MODULES * module_px


def test_artwork_keeps_its_aspect_ratio():
    """The whole point of the layout: nothing is stretched to fill the page."""
    art = pub._artwork()
    scale, _, _ = pub._layout()

    placed_w, placed_h = round(art.width * scale), round(art.height * scale)

    assert abs(placed_w / placed_h - art.width / art.height) < 0.002


def test_page_is_a4_portrait_and_the_artwork_fits_on_it():
    page = pub.render_page("https://example.com/?d=test")
    scale, (ox, oy), _ = pub._layout()
    art = pub._artwork()

    assert page.size == (pub._mm(210), pub._mm(297))
    assert ox >= 0 and oy >= 0
    assert ox + round(art.width * scale) <= page.width
    assert oy + round(art.height * scale) <= page.height


def test_minted_items_are_repeatable_team_ammo():
    urls = pub.mint_pub_items(3)
    items = [ItemModel.from_base64(u) for u in urls]

    assert len({i.id for i in items}) == 3, "every pub needs its own code"
    for item in items:
        assert item.itype == "ammo"
        assert item.data["num"] == pub.BULLETS_PER_TEAM_MEMBER
        assert item.collected_as_team is True
        assert item.collected_only_once is False
        assert item.validate_signature() is None


def test_one_page_arms_a_whole_team_once_and_the_next_team_too(
    two_users_in_different_teams, user_factory
):
    """The certificate's whole contract, end to end.

    One player scans; everybody on that team gets the bullets; nobody else on
    that team can claim it again; another team still can.
    """
    user_a1, user_b = two_users_in_different_teams
    user_a2 = user_factory()
    UserInterface(user_a2).join_team(UserInterface(user_a1).get_team_model().id)

    url = pub.mint_pub_items(1)[0]

    UserInterface(user_a1).collect_item(url)

    assert UserInterface(user_a1).get_user_model().num_bullets == 2
    assert UserInterface(user_a2).get_user_model().num_bullets == 2

    with pytest.raises(HTTPException):
        UserInterface(user_a2).collect_item(url)

    UserInterface(user_b).collect_item(url)
    assert UserInterface(user_b).get_user_model().num_bullets == 2


def test_cli_writes_one_pdf_page_per_pub(tmp_path):
    out = tmp_path / "pub_pages.pdf"
    result = CliRunner().invoke(
        pub.generate, ["--count", "3", "--no-log", "--outfile", str(out)]
    )

    assert result.exit_code == 0, result.output
    assert "Wrote 3 page(s)" in result.output
    assert out.stat().st_size > 0


def test_label_lets_the_admin_match_a_page_to_its_qr_codes_csv_row():
    """The tag+index printed on the page is the same pair logged for it.

    generate_qr_items.py prints this on every drop card so the admin can
    line a physical page up with its qr_codes.csv row without scanning it;
    the pub pages need the same mark.
    """
    url = "https://example.com/?d=test"
    blank = np.array(pub.render_page(url))
    labelled = np.array(pub.render_page(url, "pub7"))

    assert not np.array_equal(blank, labelled), "label was not drawn"

    _, (_, oy), _ = pub._layout()
    # Nothing outside the top margin - the artwork or the QR - may change.
    assert np.array_equal(blank[oy:], labelled[oy:])
