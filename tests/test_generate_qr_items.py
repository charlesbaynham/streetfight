"""The drop-card sheets (backend/generate_qr_items.py).

Mostly about the contact line (M0.5, roadmap #7): the cards are cut up and
hidden around a town nobody has told, so every one of them has to say what it
is and who to ring. What the tests here actually guard is where that line
lands - on the card, below the drawing, and far enough in from the edges to
survive both a printer's unprintable margin and the scissors.

The line is isolated by rendering the same sheet twice, once with it and once
without, and taking the difference: a sheet also carries cut guides and a run
label, and asking "is there ink in this band" would find those instead.
"""

import os
from contextlib import contextmanager

import numpy as np
import pytest
from PIL import Image

os.environ["SECRET_KEY"] = "test_secret_key"
os.environ.setdefault("WEBSITE_URL", "https://example.com")

from backend import generate_qr_items as qr  # noqa: E402

COLS, ROWS = 4, 2


@contextmanager
def _without_the_line():
    original = qr.CONTACT_LINE
    qr.CONTACT_LINE = ""
    try:
        yield
    finally:
        qr.CONTACT_LINE = original


def sheet(base_image=None, num_x=COLS, num_y=ROWS) -> Image.Image:
    codes = iter(f"https://example.com/?d=card{i}" for i in range(num_x * num_y))
    return qr.build_qr_grid(codes, num_x, num_y, base_image=base_image)


def ink(image: Image.Image) -> np.ndarray:
    return np.array(image.convert("L")) < 128


def only_the_line(base_image=None, num_x=COLS, num_y=ROWS) -> np.ndarray:
    """The pixels the contact line, and nothing else, puts on a sheet."""
    printed = ink(sheet(base_image, num_x, num_y))
    with _without_the_line():
        bare = ink(sheet(base_image, num_x, num_y))

    return printed & ~bare


def per_card(mask: np.ndarray, num_x=COLS, num_y=ROWS):
    box_w, box_h = qr.A4_WIDTH // num_x, qr.A4_HEIGHT // num_y

    return [
        mask[row * box_h : (row + 1) * box_h, col * box_w : (col + 1) * box_w]
        for row in range(num_y)
        for col in range(num_x)
    ]


@pytest.fixture(scope="module")
def artwork():
    return qr.base_image_path("ammo", 5, 1)


def test_the_line_says_what_the_card_is_and_who_to_ring():
    assert qr.CONTACT_NUMBER in qr.CONTACT_LINE
    assert "game" in qr.CONTACT_LINE


def test_every_card_carries_the_same_contact_line(artwork):
    """A sheet is cut up and the pieces hidden separately, so a line drawn
    once on the sheet would leave seven cards saying nothing."""
    cards = per_card(only_the_line(artwork))

    assert all(card.any() for card in cards)
    assert all((card == cards[0]).all() for card in cards)


def test_the_artwork_does_not_reach_into_the_contact_line(artwork):
    """The drawing is squashed to sit above the strip rather than printed
    under it, so the line is never read over a bullet or a duck."""
    box_h = qr.A4_HEIGHT // ROWS
    strip = slice(box_h - round(qr.IMAGE_GUTTER / 2) - qr.CONTACT_STRIP, box_h)

    with _without_the_line():
        drawn = per_card(ink(sheet(artwork)))[0][strip]
        blank = per_card(ink(sheet(None)))[0][strip]

    assert (drawn == blank).all()


def test_the_line_stays_inside_the_card_and_off_its_edges(artwork):
    """Two failures at once: a printer whose unprintable margin swallows the
    bottom row of a sheet, and a cut on the guide that takes the line off with
    the gutter. The line keeps the whole gutter between itself and the box
    edge, the same margin the artwork has."""
    margin = round(qr.IMAGE_GUTTER / 2)
    box_w, box_h = qr.A4_WIDTH // COLS, qr.A4_HEIGHT // ROWS

    for card in per_card(only_the_line(artwork)):
        rows = np.nonzero(card.any(axis=1))[0]
        columns = np.nonzero(card.any(axis=0))[0]

        assert columns.min() >= margin
        assert columns.max() <= box_w - margin
        assert rows.min() >= box_h - margin - qr.CONTACT_STRIP
        assert rows.max() <= box_h - margin


def test_the_line_is_resized_to_fit_a_narrower_card():
    """The grid is a parameter: eight codes across makes cards half as wide,
    and a fixed font size would run the line off the side of every one."""
    margin = round(qr.IMAGE_GUTTER / 2)
    box_w = qr.A4_WIDTH // 8

    for card in per_card(only_the_line(num_x=8, num_y=2), num_x=8, num_y=2):
        columns = np.nonzero(card.any(axis=0))[0]

        assert columns.size, "no contact line on a narrow card"
        assert columns.min() >= margin
        assert columns.max() <= box_w - margin
