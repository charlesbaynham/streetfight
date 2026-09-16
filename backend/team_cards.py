"""Printable team cards: one A4 page per team, in the form of a wartime
call-up notice, each carrying that team's door code (roadmap R15).

Teams are joined on the night by the players themselves: the team lead
holds a card, and each player scans its code to be put in that team. The
cards are handed out at the door, so they are printed - and since the point
of a party is the party, they are printed as a Ministry of War notice of
conscription rather than a QR on a blank sheet. Every line of copy is a
constant at the top of this module, so the wording is Charles's to tune in
one place.

Same toolchain as :mod:`backend.generate_pub_pages`: Pillow draws the page,
:func:`~backend.generate_pub_pages.make_qr` sizes the code in whole pixels
per module, and the pages are saved as one multi-page PDF. Everything is
drawn in code with the bundled typewriter face (``UbuntuMono-R.ttf``, which
``backend/image_processing.py`` already uses), so there is no artwork to
measure and nothing outside the package to fetch. Built by the running
server (``GET /admin_team_cards_pdf``) rather than a CLI, because the team
ids the codes carry only exist in the server's database.

Pages are sized for printing **at actual size**, not "fit to page".
"""

import io
import textwrap
from pathlib import Path
from typing import List
from typing import Sequence
from typing import Tuple

from PIL import Image
from PIL import ImageDraw
from PIL import ImageFont

from .generate_pub_pages import DPI
from .generate_pub_pages import _mm
from .generate_pub_pages import make_qr

FONT_PATH = Path(__file__, "../UbuntuMono-R.ttf").resolve()

PAGE_W, PAGE_H = _mm(210), _mm(297)

# ---------------------------------------------------------------------------
# The copy. Edit here.
# ---------------------------------------------------------------------------

MINISTRY = "MINISTRY OF WAR"
TITLE = "NOTICE OF CONSCRIPTION"
REFERENCE = "FORM SF/19  --  FOR THE ATTENTION OF THE PERSON NAMED HEREON"
ORDER = (
    "By order of the Ministry of War you are hereby required to report for "
    "duty and to fight for your compatriots in"
)
SCAN = "SCAN HERE TO REPORT FOR DUTY"
WARNING = "Failure to report will be looked upon most severely."
STAMP = "BY ORDER"

# ---------------------------------------------------------------------------
# The look.
# ---------------------------------------------------------------------------

PAPER = (243, 236, 218)
INK = (28, 26, 24)
RULE = (70, 64, 58)
STAMP_RED = (168, 32, 32)

MARGIN = _mm(14)
RULE_GAP = _mm(2.5)
RULE_WIDTH = max(1, _mm(0.5))
INNER = MARGIN + RULE_GAP + _mm(8)  # text margin inside the double rule

QR_SIDE = _mm(85)
# The white margin a scanner needs around the code, in page pixels. The QR
# is drawn on the paper tint, so give it a white plate of its own.
QR_PLATE = _mm(6)

STAMP_ANGLE_DEG = -11


def _font(size_px: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(FONT_PATH), size_px)


def _fit_font(
    text: str, max_width: int, start_px: int, min_px: int
) -> ImageFont.FreeTypeFont:
    """The largest size from ``start_px`` down at which ``text`` fits
    ``max_width`` on one line, floored at ``min_px``."""
    size = start_px
    while size > min_px and _font(size).getlength(text) > max_width:
        size -= 4
    return _font(size)


def _wrap(text: str, font: ImageFont.FreeTypeFont, max_width: int) -> List[str]:
    """Word-wrap ``text`` to ``max_width`` in ``font``. The face is
    monospace, so a character budget is exact rather than an estimate."""
    per_char = font.getlength("M")
    return textwrap.wrap(text, width=max(1, int(max_width // per_char)))


def _centred(draw: ImageDraw.ImageDraw, y: int, text: str, font, fill=INK) -> int:
    """Draw ``text`` centred at ``y``; return the y just below it."""
    width = font.getlength(text)
    draw.text(((PAGE_W - width) / 2, y), text, font=font, fill=fill)
    ascent, descent = font.getmetrics()
    return y + ascent + descent


def _rule(draw: ImageDraw.ImageDraw, y: int, inset: int = INNER) -> None:
    draw.line([(inset, y), (PAGE_W - inset, y)], fill=RULE, width=RULE_WIDTH)


def _border(draw: ImageDraw.ImageDraw) -> None:
    """A double rule around the page, the outer one heavier."""
    draw.rectangle(
        [MARGIN, MARGIN, PAGE_W - MARGIN, PAGE_H - MARGIN],
        outline=RULE,
        width=RULE_WIDTH * 3,
    )
    inner = MARGIN + RULE_GAP
    draw.rectangle(
        [inner, inner, PAGE_W - inner, PAGE_H - inner], outline=RULE, width=RULE_WIDTH
    )


def _stamp() -> Image.Image:
    """The red rubber stamp, as a transparent layer to paste at an angle."""
    font = _font(_mm(11))
    pad = _mm(4)
    text_w = font.getlength(STAMP)
    ascent, descent = font.getmetrics()
    w, h = int(text_w + 2 * pad), int(ascent + descent + 2 * pad)

    layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    draw.rectangle([0, 0, w - 1, h - 1], outline=STAMP_RED, width=max(1, _mm(1)))
    draw.text((pad, pad), STAMP, font=font, fill=STAMP_RED)

    # Rubber stamps are never quite solid: knock the ink back a little.
    alpha = layer.getchannel("A").point(lambda a: int(a * 0.82))
    layer.putalpha(alpha)

    return layer.rotate(STAMP_ANGLE_DEG, expand=True, resample=Image.BICUBIC)


def team_name_lines(team_name: str) -> Tuple[ImageFont.FreeTypeFont, List[str]]:
    """The team name as it is set: one big line if it fits, otherwise
    wrapped at a size that still reads from across the room, and only then
    shrunk - so a long name never runs into the rule."""
    width = PAGE_W - 2 * INNER
    name = team_name.upper()

    font = _fit_font(name, width, _mm(16), _mm(9))
    if font.getlength(name) <= width:
        return font, [name]

    lines = _wrap(name, font, width)
    longest = max(lines, key=font.getlength)
    return _fit_font(longest, width, _mm(9), _mm(3)), lines


def render_team_card(team_name: str, url: str) -> Image.Image:
    """One A4 portrait page: the notice, naming ``team_name``, with ``url``
    as the code to scan."""
    page = Image.new("RGB", (PAGE_W, PAGE_H), PAPER)
    draw = ImageDraw.Draw(page)
    _border(draw)

    text_width = PAGE_W - 2 * INNER

    y = INNER + _mm(4)
    y = _centred(draw, y, MINISTRY, _font(_mm(9)))
    y += _mm(2)
    _rule(draw, y)
    y += _mm(4)
    y = _centred(draw, y, TITLE, _font(_mm(6.5)))
    y += _mm(1)
    y = _centred(draw, y, REFERENCE, _font(_mm(2.6)), fill=RULE)
    y += _mm(2)
    _rule(draw, y)
    y += _mm(10)

    body_font = _font(_mm(4.2))
    for line in _wrap(ORDER, body_font, text_width):
        y = _centred(draw, y, line, body_font)
        y += _mm(1)
    y += _mm(6)

    name_font, name_lines = team_name_lines(team_name)
    for line in name_lines:
        y = _centred(draw, y, line, name_font)
    y += _mm(12)

    y = _centred(draw, y, SCAN, _font(_mm(4.2)))
    y += _mm(5)

    # The code, on a white plate so the quiet zone is white paper rather
    # than the tint - a scanner wants contrast, not atmosphere.
    qr = make_qr(url, QR_SIDE)
    plate_side = qr.width + 2 * QR_PLATE
    plate_x = (PAGE_W - plate_side) // 2
    draw.rectangle(
        [plate_x, y, plate_x + plate_side, y + plate_side], fill="white", outline=RULE
    )
    page.paste(qr, (plate_x + QR_PLATE, y + QR_PLATE))
    y += plate_side + _mm(12)

    y = _centred(draw, y, WARNING, _font(_mm(3.8)))
    y += _mm(10)

    # The stamp, at an angle in the lower right, as if it were the last
    # thing done to the page.
    stamp = _stamp()
    page.paste(stamp, (PAGE_W - INNER - stamp.width - _mm(10), y), mask=stamp)

    return page


def render_pdf(cards: Sequence[Tuple[str, str]]) -> bytes:
    """One multi-page A4 PDF with a card per ``(team_name, url)``."""
    if not cards:
        raise ValueError("no teams to print")

    pages = [render_team_card(name, url) for name, url in cards]
    out = io.BytesIO()
    pages[0].save(out, "PDF", resolution=DPI, save_all=True, append_images=pages[1:])
    return out.getvalue()
