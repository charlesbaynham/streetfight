"""A4 pub certificates: one page, one QR code, two bullets for a whole team.

A different shape from the drop codes in :mod:`backend.generate_qr_items`,
which pack eight small cards onto a landscape sheet to be cut up and hidden.
A pub page is a poster: one portrait A4 sheet a landlord puts on display and a
passing team scans from across the room.

**The pages are deliberately anonymous.** Nothing on a page says which pub it
belongs to, so a stack of them can be dealt out in any order and nobody has to
keep a register of which code went where.

**The item is ammo, awarded to the team, and repeatable.** That combination -
``collected_as_team=True`` with ``collected_only_once=False`` - is what makes
one sheet serve a whole evening: the first player of a team to scan it
collects for everybody on that team, nobody else on that team can claim it
again, and every *other* team can still claim it once of their own. Ammo is
also the only item type that can be collected on behalf of a team at all;
``item_actions._ACTIONS`` has no team handler for armour, medpacks or weapons.

**Where the QR goes was measured, not chosen.** The artwork is a drawn A4
page with no ink-free square bigger than about a fifth of its width, so a QR
big enough to read across a pub cannot go wherever one likes: the top right
holds 28 mm, and a panel big enough to be comfortable covers the signature.
:data:`QR_POCKET` is the one place a useful-sized code fits without touching
anything - the gap between the signature and the frame, left of the bullets -
and ``tests/test_generate_pub_pages.py`` re-measures it against the artwork so
that a re-drawn picture fails a test rather than printing a QR over
handwriting.

Pages are sized for printing **at actual size**, not "fit to page".
"""

import logging
from pathlib import Path
from typing import Iterable
from typing import List
from typing import Tuple

import click
import qrcode
from PIL import Image
from PIL import ImageDraw

from .admin_interface import AdminInterface
from .generate_qr_items import IMAGES_DIR
from .generate_qr_items import QR_LOGFILE
from .items import ItemModel

logger = logging.getLogger(__name__)

DPI = 300
BULLETS_PER_TEAM_MEMBER = 2

ARTWORK = Path(IMAGES_DIR, "reusable bullets.png")


def _mm(mm: float) -> int:
    return round(mm * DPI / 25.4)


PAGE_W, PAGE_H = _mm(210), _mm(297)

# 4 mm: the artwork's outer edge is decorative frame, and the margin is what
# the QR's size comes out of - every millimetre given to white here is taken
# off the code. Tight enough to need a printer that does not shrink the page
# to fit, which is why the module docstring says so.
MARGIN = _mm(4)

# The ink-free pocket, in trimmed-artwork pixels: x, y, side. Measured off
# the alpha channel, not eyeballed.
QR_POCKET = (306, 1702, 378)

# The white margin a scanner needs around the code, in modules. The pocket
# supplies it - the QR itself is rendered with no border of its own and
# centred in the pocket, so the quiet zone is the artwork's own white paper.
QUIET_MODULES = 4


def _artwork() -> Image.Image:
    """The pub artwork, trimmed to its own ink.

    The drawing carries a band of empty pixels below the frame; left in, it
    becomes a stripe of white across the bottom of every page.
    """
    art = Image.open(ARTWORK).convert("RGBA")
    bbox = art.getbbox()
    return art.crop(bbox) if bbox else art


def _layout() -> Tuple[float, Tuple[int, int], Tuple[int, int, int]]:
    """Where the artwork and the QR pocket land on the page.

    Returns the artwork's scale factor, its top-left corner, and the pocket
    as ``(x, y, side)`` in page pixels.
    """
    art = _artwork()

    scale = min((PAGE_W - 2 * MARGIN) / art.width, (PAGE_H - 2 * MARGIN) / art.height)
    art_w, art_h = round(art.width * scale), round(art.height * scale)
    origin = ((PAGE_W - art_w) // 2, (PAGE_H - art_h) // 2)

    px, py, side = QR_POCKET

    return (
        scale,
        origin,
        (
            origin[0] + round(px * scale),
            origin[1] + round(py * scale),
            round(side * scale),
        ),
    )


def make_qr(url: str, pocket_px: int) -> Image.Image:
    """Render ``url`` as a QR code that fits ``pocket_px`` with its quiet zone.

    Sized in whole pixels per module rather than scaled to fit: resampling a
    finished QR smears every module edge by a fraction of a pixel, which is
    the one detail a scanner is looking at.
    """
    qr = qrcode.QRCode(error_correction=qrcode.ERROR_CORRECT_M, border=0)
    qr.add_data(url)
    qr.make(fit=True)

    qr.box_size = max(1, pocket_px // (qr.modules_count + 2 * QUIET_MODULES))

    return qr.make_image(fill_color="black", back_color="white").convert("RGB")


def render_page(url: str, label: str = "") -> Image.Image:
    """One A4 portrait page: the artwork, with ``url`` as a QR in its pocket.

    ``label`` (the same ``tag`` + index that lands beside this code's row in
    qr_codes.csv) is printed top-left, in the page margin - the same "match
    it to the log without scanning it" mark generate_qr_items.py puts on
    every drop card. The margin is blank there regardless of which axis
    the artwork's scale is bound by: :func:`_layout` fits the artwork inside
    ``PAGE_W - 2 * MARGIN`` and ``PAGE_H - 2 * MARGIN``, so its top edge never
    starts above ``y = MARGIN``, and the full-width strip above that is
    always free of ink to print on.
    """
    scale, origin, (px, py, side) = _layout()

    art = _artwork()
    art = art.resize(
        (round(art.width * scale), round(art.height * scale)), Image.LANCZOS
    )

    page = Image.new("RGB", (PAGE_W, PAGE_H), "white")
    page.paste(art, origin, mask=art)

    qr = make_qr(url, side)
    page.paste(qr, (px + (side - qr.width) // 2, py + (side - qr.height) // 2))

    if label:
        ImageDraw.Draw(page).text((MARGIN // 4, MARGIN // 4), label, fill="black")

    return page


def pocket_ink_pixels() -> int:
    """How much of the artwork lies inside :data:`QR_POCKET`.

    Zero, or the QR is printing over the drawing. The layout's one
    load-bearing invariant, and a function rather than a comment so that a
    re-drawn artwork fails a test instead of a print run.
    """
    x, y, side = QR_POCKET
    alpha = _artwork().crop((x, y, x + side, y + side)).getchannel("A")

    return sum(alpha.histogram()[17:])


def mint_pub_items(count: int, num_bullets: int = BULLETS_PER_TEAM_MEMBER) -> List[str]:
    """``count`` distinct ammo codes, each claimable once by every team."""
    admin = AdminInterface()

    return [
        admin.make_new_item(
            "ammo",
            {"num": num_bullets},
            collected_only_once=False,
            collected_as_team=True,
        )
        for _ in range(count)
    ]


def log_items(urls: Iterable[str], tag: str, num_bullets: int) -> None:
    """Append to the same ``qr_codes.csv`` the drop codes are recorded in."""
    with open(QR_LOGFILE, "a") as f:
        for i, url in enumerate(urls):
            item = ItemModel.from_base64(url)
            f.write(f"{item.id},{tag},{i},{item.itype},{num_bullets},,,False,True\n")


@click.command()
@click.option(
    "--count",
    "-c",
    type=int,
    prompt="How many pages (one per pub)",
    help="How many pages to mint. Each gets a code of its own.",
)
@click.option(
    "--num",
    "-n",
    type=int,
    default=BULLETS_PER_TEAM_MEMBER,
    show_default=True,
    help="Bullets awarded to each member of the collecting team.",
)
@click.option(
    "--outfile",
    "-o",
    type=click.Path(dir_okay=False, writable=True, resolve_path=True),
    default="pub_pages.pdf",
    show_default=True,
    help="Where to write the PDF. One page per pub.",
)
@click.option(
    "--tag",
    default="pub",
    help="Written into qr_codes.csv beside each code.",
)
@click.option("--log/--no-log", default=True, help="Record the codes minted.")
def generate(count: int, num: int, outfile: str, tag: str, log: bool):
    """Mint a PDF of A4 pub certificates, one page and one code per pub.

    Codes are signed with SECRET_KEY and carry WEBSITE_URL, so both must be
    the values the players' server is really running with - otherwise every
    scan fails on the signature.
    """
    if count < 1:
        raise click.ClickException("Nothing to print: --count must be at least 1.")

    urls = mint_pub_items(count, num)
    pages = [render_page(url, f"{tag}{i}") for i, url in enumerate(urls)]

    pages[0].save(
        outfile, "PDF", resolution=DPI, save_all=True, append_images=pages[1:]
    )
    click.echo(f"Wrote {len(pages)} page(s) to {outfile}")

    if log:
        log_items(urls, tag, num)
        click.echo(f"Recorded {len(urls)} code(s) in {QR_LOGFILE}")


if __name__ == "__main__":
    generate()
