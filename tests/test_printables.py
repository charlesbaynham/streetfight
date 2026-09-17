"""The printables the admin page builds on demand (backend/printables.py)."""

import logging
import os

import pytest
from PIL import Image
from PIL import ImageChops

os.environ["SECRET_KEY"] = "test_secret_key"
os.environ.setdefault("WEBSITE_URL", "https://example.com")

from backend import printables  # noqa: E402
from backend import qr_log  # noqa: E402
from backend.generate_qr_items import base_image_path  # noqa: E402
from backend.item_actions import WEAPON_NAME_LOOKUP  # noqa: E402
from backend.items import ItemModel  # noqa: E402


@pytest.fixture(autouse=True)
def mock_asyncio_tasks(mocker):
    mocker.patch("backend.asyncio_triggers.schedule_update_event")


@pytest.fixture(autouse=True)
def log_to_tmp(tmp_path, monkeypatch):
    """Keep the tests out of the repository's own qr_codes.csv."""
    logfile = tmp_path / "qr_codes.csv"
    monkeypatch.setenv(qr_log.QR_LOGFILE_ENV, str(logfile))
    return logfile


def page_count(pdf: bytes) -> int:
    return pdf.count(b"/Type /Page\n")


def logged_codes(logfile):
    return logfile.read_text().splitlines() if logfile.exists() else []


def test_a_drop_run_prints_and_records_a_card_per_box(log_to_tmp):
    pdf = printables.item_sheets_pdf("ammo", num=5, sheets=2)

    assert page_count(pdf) == 2
    assert len(logged_codes(log_to_tmp)) == 2 * printables.CARDS_PER_SHEET


def test_every_drop_card_is_a_different_item(log_to_tmp):
    """A sheet is cut up and the pieces hidden separately, so two cards
    collecting the same item would be a hiding place wasted."""
    printables.item_sheets_pdf("medpack", num=1, sheets=2)

    ids = [row.split(",")[0] for row in logged_codes(log_to_tmp)]

    assert len(set(ids)) == len(ids) == 2 * printables.CARDS_PER_SHEET


def test_pub_pages_mint_repeatable_team_ammo(log_to_tmp):
    pdf = printables.pub_pages_pdf(3, num_bullets=5)

    assert page_count(pdf) == 3

    rows = [row.split(",") for row in logged_codes(log_to_tmp)]
    assert len(rows) == 3
    # The two flags that make one sheet serve every team once: claimed for the
    # whole team, and claimable again by the next team along.
    assert all((row[7], row[8]) == ("False", "True") for row in rows)


def test_a_run_labels_its_codes_with_its_batch(log_to_tmp):
    """A batch is how a whole print run is withdrawn at once later (M2.2), so
    it has to reach both the payload and the log."""
    printables.item_sheets_pdf("ammo", num=5, batch="sandbox", unlimited=True)

    rows = [row.split(",") for row in logged_codes(log_to_tmp)]
    assert all(row[-1] == "sandbox" for row in rows)


def test_the_new_timed_cards_print(log_to_tmp):
    """Radar and circle-warning cards are printed before their handlers are
    written, so what must work now is minting and drawing them."""
    pdf = printables.item_sheets_pdf("radar", num=1, minutes=7)

    assert page_count(pdf) == 1
    assert all(
        row.split(",")[3] == "ItemType.RADAR" for row in logged_codes(log_to_tmp)
    )


def test_a_sandbox_run_prints_a_page_for_every_kind_of_poster(log_to_tmp):
    pdf = printables.sandbox_sheets_pdf(copies=2)

    assert page_count(pdf) == 2 * len(printables.SANDBOX_CARDS)
    # One code per kind, not one per card: an unlimited code is claimable by
    # everybody as often as they like, so a second would be the same power and
    # a second row to read.
    assert len(logged_codes(log_to_tmp)) == len(printables.SANDBOX_CARDS)


def test_a_sandbox_poster_is_a_portrait_a4_page_saying_what_it_is():
    """The word is the whole reason this is a page of its own rather than a
    card on a sheet of eight: an unlimited code carries the same drawing as
    the ones being hidden round the town, so a poster without it gets
    shuffled into the box."""
    card = printables.SANDBOX_CARDS[0]
    page = printables.infinite_poster("https://example.com/item", card)

    assert page.size == (printables.PAGE_W, printables.PAGE_H)

    band = page.crop((0, 0, printables.PAGE_W, printables.INFINITE_BAND))
    blank = Image.new("RGB", band.size, "white")
    assert ImageChops.difference(band, blank).getbbox() is not None


def test_no_sandbox_poster_buries_its_own_qr_code():
    """The drawings are drawn around an ink-free pocket and the code goes in
    it. Measured rather than eyeballed, so a re-drawn card that closed the
    pocket up fails here rather than in a warm-up room."""
    for card in printables.SANDBOX_CARDS:
        assert printables.poster_artwork_ink(card) < 0.05, card


def test_every_sandbox_code_is_unlimited_and_withdrawable_as_one_batch():
    """The two properties the warm-up room depends on: a poster can be scanned
    again by the same player, and the whole room goes off in one press."""
    for _, url in printables.sandbox_items():
        item = ItemModel.from_base64(url)

        assert item.validate_signature() is None
        assert item.unlimited is True
        assert item.batch == printables.SANDBOX_BATCH


def test_every_sandbox_poster_has_a_drawing():
    """A poster is read across a room, so a bare QR code will not do - and
    the drawing a card gets is decided by what it awards. This is the test
    that says why the ammunition poster is 5 bullets and not 20: there is no
    ammo_20.png."""
    for card in printables.SANDBOX_CARDS:
        assert base_image_path(card.itype, card.num, card.damage) is not None, card


def test_the_sandbox_hands_out_the_weapons_it_names():
    """The pairs in SANDBOX_CARDS are literals, so this is what keeps them in
    step with the weapon table: retune or rename a weapon there and this
    fails, rather than the sandbox quietly handing out something else."""
    named = {
        "pewster": "Pewster",
        "eat-a-bullet": "Eat-a-bullet",
        "tracka-tracka": "Tracka-Tracka",
    }

    weapons = [card for card in printables.SANDBOX_CARDS if card.itype == "weapon"]
    assert {card.label for card in weapons} == set(named)

    for card in weapons:
        assert WEAPON_NAME_LOOKUP[(card.damage, card.timeout)] == named[card.label]


def test_a_configured_log_is_where_a_print_run_is_recorded(tmp_path, monkeypatch):
    """The deployment's backend runs from a read-only store path, so the log
    has to be somewhere else entirely - and the rows have to arrive there."""
    configured = tmp_path / "state" / "qr_codes.csv"
    configured.parent.mkdir()
    monkeypatch.setenv(qr_log.QR_LOGFILE_ENV, str(configured))

    printables.item_sheets_pdf("ammo", num=5)
    printables.pub_pages_pdf(1)

    assert len(logged_codes(configured)) == printables.CARDS_PER_SHEET + 1


def test_an_unconfigured_log_stays_beside_the_checkout(monkeypatch):
    """A dev checkout is unchanged: no QR_LOGFILE, same file as ever."""
    monkeypatch.delenv(qr_log.QR_LOGFILE_ENV)

    assert qr_log.qr_logfile() == qr_log.DEFAULT_QR_LOGFILE


@pytest.mark.skipif(os.geteuid() == 0, reason="root ignores a read-only directory")
def test_a_read_only_log_costs_the_record_but_not_the_pdf(
    tmp_path, monkeypatch, caplog
):
    """Losing the record is a nuisance; losing the paper would be worse."""
    unwritable = tmp_path / "store"
    unwritable.mkdir(mode=0o500)
    monkeypatch.setenv(qr_log.QR_LOGFILE_ENV, str(unwritable / "qr_codes.csv"))

    with caplog.at_level(logging.WARNING):
        assert page_count(printables.item_sheets_pdf("ammo", num=5)) == 1

    assert "Could not record minted codes" in caplog.text


@pytest.mark.parametrize(
    "call",
    [
        lambda: printables.item_sheets_pdf("ammo", num=1, sheets=0),
        lambda: printables.item_sheets_pdf(
            "ammo", num=1, sheets=printables.MAX_SHEETS + 1
        ),
        lambda: printables.sandbox_sheets_pdf(copies=0),
        lambda: printables.sandbox_sheets_pdf(copies=printables.MAX_SANDBOX_COPIES + 1),
        lambda: printables.pub_pages_pdf(0),
        lambda: printables.pub_pages_pdf(printables.MAX_PUB_PAGES + 1),
    ],
)
def test_nonsense_quantities_are_refused(call):
    with pytest.raises(ValueError):
        call()


def test_item_sheet_endpoint_returns_a_pdf(admin_api_client, log_to_tmp):
    response = admin_api_client.post(
        "/api/admin_item_sheets_pdf?itype=ammo&num=5&sheets=1"
    )

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert response.content.startswith(b"%PDF")


def test_pub_pages_endpoint_returns_a_pdf(admin_api_client, log_to_tmp):
    response = admin_api_client.post("/api/admin_pub_pages_pdf?count=2")

    assert response.status_code == 200
    assert page_count(response.content) == 2


def test_endpoints_refuse_nonsense_quantities(admin_api_client, log_to_tmp):
    response = admin_api_client.post(
        "/api/admin_item_sheets_pdf?itype=ammo&num=5&sheets=0"
    )

    assert response.status_code == 400


def test_sandbox_endpoint_returns_a_pdf(admin_api_client, log_to_tmp):
    response = admin_api_client.post("/api/admin_sandbox_sheets_pdf?copies=1")

    assert response.status_code == 200
    assert page_count(response.content) == len(printables.SANDBOX_CARDS)


def test_withdrawing_a_batch_over_the_api_returns_the_new_list(admin_api_client):
    admin_api_client.post("/api/admin_withdraw_batch?batch=sandbox")

    listed = admin_api_client.get("/api/admin_revoked_batches")
    assert [entry["batch"] for entry in listed.json()] == ["sandbox"]

    restored = admin_api_client.post("/api/admin_restore_batch?batch=sandbox")
    assert restored.json() == []


def test_withdrawing_needs_an_admin(api_client):
    response = api_client.post("/api/admin_withdraw_batch?batch=game")

    assert response.status_code == 403


def test_printables_need_an_admin(api_client, log_to_tmp):
    response = api_client.post("/api/admin_pub_pages_pdf?count=1")

    assert response.status_code == 403
