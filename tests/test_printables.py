"""The printables the admin page builds on demand (backend/printables.py)."""

import os

import pytest

os.environ["SECRET_KEY"] = "test_secret_key"
os.environ.setdefault("WEBSITE_URL", "https://example.com")

from backend import printables  # noqa: E402


@pytest.fixture(autouse=True)
def mock_asyncio_tasks(mocker):
    mocker.patch("backend.asyncio_triggers.schedule_update_event")


@pytest.fixture(autouse=True)
def log_to_tmp(tmp_path, mocker):
    """Keep the tests out of the repository's own qr_codes.csv."""
    logfile = tmp_path / "qr_codes.csv"
    mocker.patch("backend.generate_qr_items.QR_LOGFILE", logfile)
    mocker.patch("backend.generate_pub_pages.QR_LOGFILE", logfile)
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
    pdf = printables.pub_pages_pdf(3, num_bullets=2)

    assert page_count(pdf) == 3

    rows = [row.split(",") for row in logged_codes(log_to_tmp)]
    assert len(rows) == 3
    # The two flags that make one sheet serve every team once: claimed for the
    # whole team, and claimable again by the next team along.
    assert all((row[7], row[8]) == ("False", "True") for row in rows)


def test_a_read_only_log_costs_the_record_but_not_the_pdf(mocker):
    """The log sits beside the source tree, which on a deployment is a
    read-only Nix store: a print run must survive not being able to write it."""
    mocker.patch(
        "backend.generate_qr_items.log_items", side_effect=OSError("read-only")
    )

    assert page_count(printables.item_sheets_pdf("ammo", num=5)) == 1


@pytest.mark.parametrize(
    "call",
    [
        lambda: printables.item_sheets_pdf("ammo", num=1, sheets=0),
        lambda: printables.item_sheets_pdf(
            "ammo", num=1, sheets=printables.MAX_SHEETS + 1
        ),
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


def test_printables_need_an_admin(api_client, log_to_tmp):
    response = api_client.post("/api/admin_pub_pages_pdf?count=1")

    assert response.status_code == 403
