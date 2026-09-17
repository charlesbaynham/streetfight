"""A printable poster of the venue map, to pin up where people will read it.

One page: the game's name and date, the venue's own map image, and a numbered
legend of everywhere on it worth naming. A player standing in front of it in a
pub should be able to find a pub they have not been to yet.

Built from :data:`backend.venues.ACTIVE_VENUE`, so the legend cannot drift
from the map: the numbers on the page are the venue's own landmarks, projected
onto the image by the same reference points the app draws the player's dot
with. Add a pub to `venues.py` and it appears here; misplace one and it is
visibly in the wrong street.

**What is deliberately left off**: circles, drop locations, and anywhere else
the game is going to put something. Those are landmarks too, and this poster
goes on a wall that players read - so they are excluded by rule
(:data:`OPERATIONAL_PREFIXES`) rather than by somebody remembering.

Same toolchain as :mod:`backend.team_cards`: Pillow draws the page, sizes come
from :func:`~backend.generate_pub_pages._mm` at that module's ``DPI``, and the
type is the bundled typewriter face. Nothing is minted and nothing is
recorded, which is why the route that serves it (``GET /admin_map_poster_pdf``)
is a GET where the code-minting printables are POSTs.

Pages are sized for printing **at actual size**, not "fit to page".
"""

import io
from pathlib import Path
from typing import Dict
from typing import List
from typing import Tuple

from PIL import Image
from PIL import ImageDraw
from PIL import ImageFont

from .generate_pub_pages import DPI
from .generate_pub_pages import _mm
from .venues import ACTIVE_VENUE
from .venues import Venue

FONT_PATH = Path(__file__, "../UbuntuMono-R.ttf").resolve()

# The map images, keyed exactly as `VenueMap.image` keys them - which is also
# how react-ui/src/mapImages.js keys them, so the two stay in step. Each entry
# is a symlink to the one real file in react-ui/src/images/: webpack has to
# bundle it from there, and the deployed backend is a wheel built from
# `backend*` alone, so a copy in the package is what makes this work on the
# droplet. A symlink rather than a second file means there is nothing to drift,
# and tests/test_map_poster.py checks every venue has one.
MAP_IMAGE_DIR = Path(__file__).parent / "map_images"

# ---------------------------------------------------------------------------
# The copy. Edit here.
# ---------------------------------------------------------------------------

GAME_NAME = "STREET FIGHT"
GAME_DATE = "SATURDAY 19 SEPTEMBER 2026"
LEGEND_HEADING = "WHERE EVERYTHING IS"

# A landmark whose name starts with one of these is somewhere the game puts
# something, not somewhere that is already there. Players read this poster, so
# it says where the pubs are and nothing about where the circles will be.
OPERATIONAL_PREFIXES = ("CIRCLE", "DROP_", "COURIER")

# Title-casing a landmark key gives "Marquis Of Granby", which is not how the
# pub is written on its own sign. Anything here is lowered unless it starts
# the name.
MINOR_WORDS = frozenset({"a", "and", "at", "in", "of", "on", "the"})

# ---------------------------------------------------------------------------
# The look. Millimetres are A3 millimetres; A4 is the same design scaled.
# ---------------------------------------------------------------------------

PAGE_SIZES_MM: Dict[str, Tuple[float, float]] = {
    "A3": (297.0, 420.0),
    "A4": (210.0, 297.0),
}
DEFAULT_PAGE_SIZE = "A3"

PAPER = (243, 236, 218)
INK = (28, 26, 24)
RULE = (70, 64, 58)

MARGIN_MM = 12.0
TITLE_MM = 17.0
VENUE_MM = 6.0
LEGEND_HEADING_MM = 4.5
LEGEND_MM = 4.0

MARKER_MM = 5.6
MARKER_NUMBER_MM = 3.4
LEGEND_ROW_MM = 7.0
LEGEND_COLUMNS = 3


class _Page:
    """One page's geometry. Every length below is written in A3 millimetres
    and scaled, so A3 and A4 are the same design rather than two layouts -
    the two sizes share an aspect ratio, so nothing has to move."""

    def __init__(self, size: str):
        try:
            width_mm, height_mm = PAGE_SIZES_MM[size]
        except KeyError:
            raise ValueError(
                f"unknown page size {size!r}; expected one of "
                f"{', '.join(sorted(PAGE_SIZES_MM))}"
            )
        self.size = size
        self.scale = width_mm / PAGE_SIZES_MM["A3"][0]
        self.width = _mm(width_mm)
        self.height = _mm(height_mm)

    def px(self, a3_mm: float) -> int:
        return _mm(a3_mm * self.scale)

    def font(self, a3_mm: float) -> ImageFont.FreeTypeFont:
        return ImageFont.truetype(str(FONT_PATH), max(1, self.px(a3_mm)))


def map_image_path(image_key: str) -> Path:
    """The file behind a venue's `map.image` key, as shipped with the
    package. Raises if it is missing, since a poster without its map is not
    something to hand somebody quietly."""
    matches = sorted(MAP_IMAGE_DIR.glob(f"{image_key}.*"))
    if not matches:
        raise FileNotFoundError(
            f"no map image for venue key {image_key!r} in {MAP_IMAGE_DIR}. "
            "Add a symlink there to the file react-ui/src/images/ bundles."
        )
    return matches[0]


def poster_landmarks(venue: Venue) -> List[str]:
    """The landmarks this poster names, in the venue's own order - which is
    geographic rather than alphabetical, so the numbers walk across the map
    instead of hopping about."""
    return [
        name for name in venue.landmarks if not name.startswith(OPERATIONAL_PREFIXES)
    ]


def legend_label(name: str) -> str:
    """A landmark key as it is written on the page. `venues.py` is the source
    of truth for the words, so nothing here can call a pub something the
    admin's own circle dropdown does not."""
    words = name.replace("_", " ").title().split()
    return " ".join(
        word if i == 0 or word.lower() not in MINOR_WORDS else word.lower()
        for i, word in enumerate(words)
    )


def _marker_positions(venue: Venue, names: List[str]) -> List[Tuple[float, float]]:
    """Each landmark's place on the map image, as a fraction of its width and
    height. Fractions rather than pixels because a venue's `width_px` is its
    own unit - Kingston's is 2273 for a 2048 px file - while the bounds are
    the ground truth both this and the frontend project against."""
    bounds = venue.map.bounds
    span_long = bounds.east - bounds.west
    span_lat = bounds.north - bounds.south

    return [
        (
            (venue.landmarks[name][1] - bounds.west) / span_long,
            (bounds.north - venue.landmarks[name][0]) / span_lat,
        )
        for name in names
    ]


def _centred(
    draw: ImageDraw.ImageDraw, page: _Page, y: int, text: str, font, fill=INK
) -> int:
    width = font.getlength(text)
    draw.text(((page.width - width) / 2, y), text, font=font, fill=fill)
    ascent, descent = font.getmetrics()
    return y + ascent + descent


def _fitted(image: Image.Image, box_w: int, box_h: int) -> Image.Image:
    """`image` scaled to sit inside the box, keeping its aspect - Kingston's
    map is not square, and a poster that stretched it would put every marker
    in the wrong place."""
    scale = min(box_w / image.width, box_h / image.height)
    size = (max(1, round(image.width * scale)), max(1, round(image.height * scale)))
    return image.resize(size, Image.LANCZOS)


def _load_map(image_key: str) -> Image.Image:
    """The map, flattened onto white - Kingston's is an RGBA PNG, and the
    poster's paper tint showing through the streets would read as staining."""
    raw = Image.open(map_image_path(image_key))
    if raw.mode in ("RGBA", "LA", "P"):
        raw = raw.convert("RGBA")
        flat = Image.new("RGB", raw.size, "white")
        flat.paste(raw, mask=raw.getchannel("A"))
        return flat
    return raw.convert("RGB")


def _draw_markers(
    canvas: Image.Image, page: _Page, positions: List[Tuple[float, float]]
) -> None:
    """A numbered dot per landmark, drawn onto the map itself. The legend is
    only usable if the numbers are on the map, and the drawing labels the
    pubs it was traced with rather than the ones in play."""
    draw = ImageDraw.Draw(canvas)
    radius = page.px(MARKER_MM) / 2
    font = page.font(MARKER_NUMBER_MM)

    for index, (x_frac, y_frac) in enumerate(positions, 1):
        x = x_frac * canvas.width
        y = y_frac * canvas.height
        draw.ellipse(
            [x - radius, y - radius, x + radius, y + radius],
            fill=INK,
            outline="white",
            width=max(1, page.px(0.5)),
        )
        draw.text((x, y), str(index), font=font, fill="white", anchor="mm")


def _draw_legend(
    draw: ImageDraw.ImageDraw, page: _Page, top: int, names: List[str]
) -> None:
    """The legend, filled column by column so the numbers read downwards."""
    font = page.font(LEGEND_MM)
    row_height = page.px(LEGEND_ROW_MM)
    inner = page.px(MARGIN_MM) + page.px(4)
    column_width = (page.width - 2 * inner) // LEGEND_COLUMNS
    rows = -(-len(names) // LEGEND_COLUMNS)  # ceiling: the last column may be short

    for index, name in enumerate(names, 1):
        column, row = divmod(index - 1, rows)
        x = inner + column * column_width
        y = top + row * row_height
        draw.text((x, y), f"{index:>2}. {legend_label(name)}", font=font, fill=INK)


def render_poster(venue: Venue = None, size: str = DEFAULT_PAGE_SIZE) -> Image.Image:
    """One page: title, the venue's map with numbered markers, and the legend
    those numbers belong to."""
    venue = venue if venue is not None else ACTIVE_VENUE
    page = _Page(size)
    names = poster_landmarks(venue)

    sheet = Image.new("RGB", (page.width, page.height), PAPER)
    draw = ImageDraw.Draw(sheet)
    margin = page.px(MARGIN_MM)

    y = margin + page.px(4)
    y = _centred(draw, page, y, GAME_NAME, page.font(TITLE_MM))
    y += page.px(1)
    y = _centred(
        draw,
        page,
        y,
        f"{venue.name.upper()}  -  {GAME_DATE}",
        page.font(VENUE_MM),
        fill=RULE,
    )
    y += page.px(4)

    # The legend's height is known, so the map takes whatever is left: the
    # biggest map that leaves room to name what is on it.
    legend_rows = -(-len(names) // LEGEND_COLUMNS)
    legend_height = page.px(LEGEND_HEADING_MM) * 2 + legend_rows * page.px(
        LEGEND_ROW_MM
    )
    map_top = y
    map_height = page.height - margin - legend_height - map_top - page.px(4)
    map_width = page.width - 2 * margin

    art = _fitted(_load_map(venue.map.image), map_width, map_height)
    _draw_markers(art, page, _marker_positions(venue, names))

    art_x = (page.width - art.width) // 2
    draw.rectangle(
        [
            art_x - page.px(1),
            map_top - page.px(1),
            art_x + art.width + page.px(1),
            map_top + art.height + page.px(1),
        ],
        fill="white",
        outline=RULE,
        width=max(1, page.px(0.4)),
    )
    sheet.paste(art, (art_x, map_top))

    y = map_top + art.height + page.px(6)
    y = _centred(draw, page, y, LEGEND_HEADING, page.font(LEGEND_HEADING_MM), fill=RULE)
    y += page.px(2)
    _draw_legend(draw, page, y, names)

    return sheet


def render_pdf(venue: Venue = None, size: str = DEFAULT_PAGE_SIZE) -> bytes:
    """The poster as a one-page PDF at ``size``."""
    out = io.BytesIO()
    render_poster(venue, size).save(out, "PDF", resolution=DPI)
    return out.getvalue()


def main() -> None:
    """``npm run mapgen``: write the active venue's poster beside you.

    Unlike the other printables this mints nothing and signs nothing, so a
    poster made from a checkout is the same poster the server would make.
    """
    import click

    @click.command()
    @click.option(
        "--size",
        type=click.Choice(sorted(PAGE_SIZES_MM), case_sensitive=False),
        default=DEFAULT_PAGE_SIZE,
        show_default=True,
        help="Paper size. Print at actual size, not 'fit to page'.",
    )
    @click.option(
        "--outfile",
        "-o",
        type=click.Path(dir_okay=False, writable=True, resolve_path=True),
        default="map_poster.pdf",
        show_default=True,
        help="Where to write the PDF.",
    )
    def generate(size: str, outfile: str) -> None:
        """Print the active venue's map, with a numbered legend."""
        Path(outfile).write_bytes(render_pdf(size=size.upper()))
        click.echo(
            f"Wrote {ACTIVE_VENUE.name} at {size.upper()} to {outfile} "
            f"({len(poster_landmarks(ACTIVE_VENUE))} places named)"
        )

    generate()


if __name__ == "__main__":
    main()
