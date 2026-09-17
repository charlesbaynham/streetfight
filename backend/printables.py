"""The printables, built on demand by the running server.

Three things get printed for a game night, and two of them were CLIs only:
``npm run qrgen`` for the drop cards and ``npm run pubgen`` for the pub
certificates, both run from a checkout with a ``.env`` beside it. That is the
wrong machine. A code carries the ``WEBSITE_URL`` that minted it and is signed
with that machine's ``SECRET_KEY``, so a sheet printed at home from a checkout
whose ``.env`` has drifted is a sheet nobody at the party can scan, and the
failure only shows up when somebody in a pub points a phone at it. Building
them in the server makes both automatically right, and means a printable can
be run *during* the evening rather than only before it.

This module is the rendering half; ``main.py`` serves the PDFs
(``/admin_item_sheets_pdf``, ``/admin_pub_pages_pdf``) and
``react-ui/src/AdminPrintables.js`` is the page. The team cards
(:mod:`backend.team_cards`, ``/admin_team_cards_pdf``) already worked this way
and are unchanged - the page just collects them alongside the other two.

Nothing new is drawn here: the pages are exactly what the CLIs produce, from
the same functions, so a sheet printed from the admin page and one printed
from a terminal are the same sheet. The one difference is the file format -
the drop sheets come back as a PDF rather than a PNG, since a browser download
that is going straight to a printer wants a page size on it.

**Every call mints new codes**, and a second press mints a second set rather
than re-rendering the first. An item is a signed URL rather than a database
row - nothing exists server-side until somebody scans one - so a spare set
costs nothing but a confusing stack of paper and some rows in the log. The
page says so beside the button anyway: a sheet printed twice is two sets of
codes for one hiding place.
"""

import io
import logging
from typing import List
from typing import Optional
from typing import Sequence

from PIL import Image

from .admin_interface import AdminInterface
from .generate_pub_pages import BULLETS_PER_TEAM_MEMBER
from .generate_pub_pages import DPI
from .generate_pub_pages import log_items as log_pub_codes
from .generate_pub_pages import mint_pub_items
from .generate_pub_pages import render_page
from .generate_qr_items import DEFAULT_BATCH
from .generate_qr_items import base_image_path
from .generate_qr_items import build_qr_grid
from .generate_qr_items import item_data
from .generate_qr_items import log_items as log_item_codes
from .generate_qr_items import random_tag
from .utils import slugify_string

logger = logging.getLogger(__name__)

# The drop sheet's grid, matching `npm run qrgen`'s defaults: eight cards on a
# landscape A4 sheet, to be cut up and hidden.
SHEET_COLS = 4
SHEET_ROWS = 2
CARDS_PER_SHEET = SHEET_COLS * SHEET_ROWS

# A hundred sheets is a slip of a thumb rather than a request, and each one is
# a full-page 300 dpi image held in memory while the PDF is assembled.
MAX_SHEETS = 20
MAX_PUB_PAGES = 40


def _pdf(pages: Sequence[Image.Image]) -> bytes:
    """One multi-page PDF, at the resolution the pages were drawn for."""
    rgb = [page.convert("RGB") for page in pages]

    out = io.BytesIO()
    rgb[0].save(out, "PDF", resolution=DPI, save_all=True, append_images=rgb[1:])
    return out.getvalue()


def _record(log, *args) -> None:
    """Write a batch to ``qr_codes.csv``, if there is anywhere to write it.

    The log lives next to the source tree, which on a deployment is a
    read-only Nix store path. Losing the record of a print run is a nuisance;
    losing the PDF because the record could not be written would be worse, so
    a failure here is a warning and nothing else.
    """
    try:
        log(*args)
    except OSError as e:
        logger.warning("Could not record minted codes in qr_codes.csv: %s", e)


def item_sheets_pdf(
    itype: str,
    num: int,
    sheets: int = 1,
    damage: int = 1,
    timeout: float = 6,
    collected_only_once: bool = True,
    collected_as_team: bool = False,
    tag: str = "",
    batch: Optional[str] = DEFAULT_BATCH,
    unlimited: bool = False,
    minutes: Optional[int] = None,
) -> bytes:
    """The drop cards: ``sheets`` landscape A4 sheets of eight codes each.

    Every card is a distinct item, so a sheet is cut up and the pieces hidden
    separately. Card labels are numbered across the whole run rather than
    restarting per sheet, so they line up with the rows written to
    ``qr_codes.csv``.

    ``batch`` labels the whole run so it can be withdrawn at once, and
    ``unlimited`` is what makes a sandbox poster a poster rather than a card:
    the same player may scan it as often as they like.
    """
    if sheets < 1:
        raise ValueError("Nothing to print: ask for at least one sheet.")
    if sheets > MAX_SHEETS:
        raise ValueError(f"Too many sheets at once: the limit is {MAX_SHEETS}.")

    tag = slugify_string(tag) if tag else random_tag()

    admin = AdminInterface()
    urls: List[str] = [
        admin.make_new_item(
            itype,
            item_data(num, damage, timeout, minutes),
            collected_only_once=collected_only_once,
            collected_as_team=collected_as_team,
            batch=batch,
            unlimited=unlimited,
        )
        for _ in range(sheets * CARDS_PER_SHEET)
    ]

    artwork = base_image_path(itype, num, damage)
    codes = iter(urls)
    pages = [
        build_qr_grid(
            codes,
            SHEET_COLS,
            SHEET_ROWS,
            tag=tag,
            base_image=artwork,
            label_offset=sheet * CARDS_PER_SHEET,
        )
        for sheet in range(sheets)
    ]

    _record(
        log_item_codes,
        urls,
        tag,
        num,
        damage,
        timeout,
        collected_only_once,
        collected_as_team,
        batch,
    )

    return _pdf(pages)


def pub_pages_pdf(
    count: int,
    num_bullets: int = BULLETS_PER_TEAM_MEMBER,
    tag: str = "pub",
    batch: Optional[str] = DEFAULT_BATCH,
) -> bytes:
    """The pub certificates: ``count`` portrait A4 posters, one code each,
    worth ``num_bullets`` to every member of the first team to scan it."""
    if count < 1:
        raise ValueError("Nothing to print: ask for at least one page.")
    if count > MAX_PUB_PAGES:
        raise ValueError(f"Too many pages at once: the limit is {MAX_PUB_PAGES}.")

    tag = slugify_string(tag) if tag else "pub"

    urls = mint_pub_items(count, num_bullets, batch)
    pages = [render_page(url, f"{tag}{i}") for i, url in enumerate(urls)]

    _record(log_pub_codes, urls, tag, num_bullets, batch)

    return _pdf(pages)
