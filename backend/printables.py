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
from typing import NamedTuple
from typing import Optional
from typing import Sequence
from typing import Tuple

from PIL import Image
from PIL import ImageDraw

from .admin_interface import AdminInterface
from .generate_pub_pages import BULLETS_PER_TEAM_MEMBER
from .generate_pub_pages import DPI
from .generate_pub_pages import MARGIN as PAGE_MARGIN
from .generate_pub_pages import PAGE_H
from .generate_pub_pages import PAGE_W
from .generate_pub_pages import _mm
from .generate_pub_pages import log_items as log_pub_codes
from .generate_pub_pages import mint_pub_items
from .generate_pub_pages import render_page
from .generate_qr_items import A4_HEIGHT
from .generate_qr_items import A4_WIDTH
from .generate_qr_items import CONTACT_LINE
from .generate_qr_items import DEFAULT_BATCH
from .generate_qr_items import base_image_path
from .generate_qr_items import build_qr_grid
from .generate_qr_items import card_face
from .generate_qr_items import fit_font
from .generate_qr_items import item_data
from .generate_qr_items import load_base_image
from .generate_qr_items import log_items as log_item_codes
from .generate_qr_items import random_tag
from .model import DEFAULT_SHOT_TIMEOUT
from .utils import slugify_string

logger = logging.getLogger(__name__)

# The drop sheet's grid, matching `npm run qrgen`'s defaults: eight cards on a
# landscape A4 sheet, to be cut up and hidden.
SHEET_COLS = 4
SHEET_ROWS = 2
CARDS_PER_SHEET = SHEET_COLS * SHEET_ROWS

# The shape of one of those cards, which is A4's own: it is what the artwork
# is drawn squashed to, so the infinite posters lay their card face out at it
# rather than at whatever is left of the paper once their banner is taken off.
CARD_ASPECT = (A4_WIDTH / SHEET_COLS) / (A4_HEIGHT / SHEET_ROWS)

# A hundred sheets is a slip of a thumb rather than a request, and each one is
# a full-page 300 dpi image held in memory while the PDF is assembled.
MAX_SHEETS = 20
MAX_PUB_PAGES = 40

# The warm-up room's walls (M0.4). Every code here is `unlimited`, which is
# what makes a poster a poster rather than a card: a player walks back to the
# ammunition sheet and scans it again, as often as they like. All of it is
# minted into one batch, so the whole room is withdrawn in a single press at
# 16:00 (M2.2) rather than card by card.
SANDBOX_BATCH = "sandbox"

# Six kinds of poster times this many pages, so it is a stack of paper
# rather than a sheet: a smaller cap than the drop cards'.
MAX_SANDBOX_COPIES = 5

# What the sandbox poster says it is, and how deep the band it says it in is.
# The word is the whole reason this page exists rather than a sheet of eight
# drop cards: an infinite code and a one-shot one carry the same drawing, so a
# sandbox poster that looked like a card was one gust of wind away from being
# shuffled into the box of cards to be hidden round the town.
INFINITE_WORD = "INFINITE"
INFINITE_BAND = _mm(28)

# The strip at the foot of the page for the contact line every printed code
# carries (generate_qr_items.CONTACT_LINE).
POSTER_CONTACT_BAND = _mm(12)

# The card face on a poster: as tall as the paper leaves once the two bands
# are taken off it, and as wide as that height makes it at a card's own
# proportions. The width follows the height rather than filling the paper,
# because stretching the drawing would move the QR out of the pocket it is
# drawn around.
_POSTER_CARD_H = PAGE_H - INFINITE_BAND - POSTER_CONTACT_BAND - PAGE_MARGIN
POSTER_CARD_BOX = (round(_POSTER_CARD_H * CARD_ASPECT), _POSTER_CARD_H)


class SandboxCard(NamedTuple):
    """One kind of poster: what it hands out, and what it is called in the log.

    ``num`` picks the drawing as well as the amount for everything but a
    weapon, which is drawn by its damage - so a card's numbers are not free.
    That is why the ammunition poster is five bullets and not twenty: there is
    an ``ammo_5.png`` and no ``ammo_20.png``, and a poster read across a room
    has to say what it is. Being unlimited, five a scan is no less than twenty.
    """

    label: str
    itype: str
    num: int = 1
    damage: int = 1
    timeout: float = DEFAULT_SHOT_TIMEOUT


SANDBOX_CARDS = (
    SandboxCard("ammo", "ammo", num=5),
    SandboxCard("armour", "armour", num=2),
    SandboxCard("medpack", "medpack"),
    # The weapons' (damage, delay) pairs are written out as literals, the way
    # item_actions.WEAPON_NAME_LOOKUP writes its own: tests/test_printables.py
    # reads them back out of that table, so a weapon retuned or renamed there
    # fails a test rather than quietly changing what the sandbox hands out.
    SandboxCard("pewster", "weapon", damage=1, timeout=25),
    SandboxCard("eat-a-bullet", "weapon", damage=1, timeout=5),
    SandboxCard("tracka-tracka", "weapon", damage=2, timeout=25),
)


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
    timeout: float = DEFAULT_SHOT_TIMEOUT,
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


def sandbox_items() -> List[Tuple[SandboxCard, str]]:
    """One code for each kind of poster, every one unlimited and batched.

    One code per kind rather than one per card: an unlimited code is claimable
    by everybody as often as they like, so eight distinct ones on a sheet would
    be eight identical powers and eight rows in the log to read instead of one.
    They are withdrawn together either way.
    """
    admin = AdminInterface()

    return [
        (
            card,
            admin.make_new_item(
                card.itype,
                item_data(card.num, card.damage, card.timeout),
                collected_only_once=False,
                collected_as_team=False,
                batch=SANDBOX_BATCH,
                unlimited=True,
            ),
        )
        for card in SANDBOX_CARDS
    ]


def infinite_poster(url: str, card: SandboxCard, label: str = "") -> Image.Image:
    """One portrait A4 page: ``INFINITE`` over the card's own drawing.

    The artwork and the code are exactly what a drop card carries - the same
    :func:`backend.generate_qr_items.card_face`, so the picture is the card's
    picture blown up rather than a second drawing to keep in step. What is
    added is the word, and it is added because the two are otherwise
    indistinguishable: a sandbox code hands out its item as often as anybody
    asks, and one that ended up in the box of cards to be hidden round the
    town would be an infinite ammunition supply taped under a pub bench.

    The card face is laid out at the proportions of a card on a sheet of
    eight, which are A4's own (``A4_WIDTH / 4`` by ``A4_HEIGHT / 2``), so the
    QR lands in the same pocket of the drawing here as it does there. That is
    what the side margins are: the bands above and below cost the page some
    height, and the width follows the height rather than the drawing being
    stretched to fill the paper.
    """
    art_w, art_h = POSTER_CARD_BOX

    face = card_face(
        url,
        art_w,
        art_h,
        load_base_image(
            base_image_path(card.itype, card.num, card.damage), art_w, art_h
        ),
    )

    page = Image.new("RGB", (PAGE_W, PAGE_H), "white")
    page.paste(face, ((PAGE_W - art_w) // 2, INFINITE_BAND), mask=face)

    draw = ImageDraw.Draw(page)

    word_font = fit_font(draw, INFINITE_WORD, PAGE_W - 2 * PAGE_MARGIN, INFINITE_BAND)
    draw.text(
        (PAGE_W // 2, INFINITE_BAND // 2),
        INFINITE_WORD,
        font=word_font,
        fill="black",
        anchor="mm",
    )

    contact_font = fit_font(
        draw, CONTACT_LINE, PAGE_W - 2 * PAGE_MARGIN, POSTER_CONTACT_BAND
    )
    draw.text(
        (PAGE_W // 2, PAGE_H - PAGE_MARGIN - POSTER_CONTACT_BAND // 2),
        CONTACT_LINE,
        font=contact_font,
        fill="black",
        anchor="mm",
    )

    if label:
        draw.text((PAGE_MARGIN // 4, PAGE_MARGIN // 4), label, fill="black")

    return page


def poster_artwork_ink(card: SandboxCard) -> float:
    """The fraction of a poster's QR code its own drawing is painted over.

    The artwork is drawn around an ink-free pocket and the code goes in it,
    but the pocket is a property of a picture rather than of the layout - so
    this is measured off the alpha channel, the way
    ``generate_pub_pages.pocket_ink_pixels`` is, and a test holds it down. A
    re-drawn card that closed the pocket up would otherwise print a stack of
    posters nobody can scan.
    """
    art_w, art_h = POSTER_CARD_BOX
    art = load_base_image(
        base_image_path(card.itype, card.num, card.damage), art_w, art_h
    )
    if art is None:
        return 0.0

    size = int(0.75 * min(art_w, art_h))
    offset = min(art_w // 2 - size // 2, art_h // 2 - size // 2)
    alpha = art.crop((offset, offset, offset + size, offset + size)).getchannel("A")

    return sum(alpha.histogram()[17:]) / (size * size)


def sandbox_sheets_pdf(copies: int = 1) -> bytes:
    """The sandbox posters: one A4 page per kind of card, ``copies`` of each.

    One code to a page, which for these is not a waste of paper: every code
    here is unlimited, so eight to a sheet was eight copies of one thing that
    only ever needed to be scanned once by anybody standing in front of it.
    A page each also means each poster is the size it is read at, from across
    a warm-up room.
    """
    if copies < 1:
        raise ValueError("Nothing to print: ask for at least one copy.")
    if copies > MAX_SANDBOX_COPIES:
        raise ValueError(f"Too many copies at once: the limit is {MAX_SANDBOX_COPIES}.")

    pages: List[Image.Image] = []

    for card, url in sandbox_items():
        label = f"{SANDBOX_BATCH}-{card.label}"

        pages.extend(infinite_poster(url, card, label) for _ in range(copies))

        _record(
            log_item_codes,
            [url],
            label,
            card.num,
            card.damage,
            card.timeout,
            False,
            False,
            SANDBOX_BATCH,
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
