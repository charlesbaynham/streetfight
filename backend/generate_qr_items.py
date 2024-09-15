import logging
from pathlib import Path
from typing import Iterable
from typing import Optional

import click
import qrcode
from PIL import Image
from PIL import ImageDraw

from .admin_interface import AdminInterface
from .model import ItemType

logger = logging.getLogger(__name__)

# A4 dimensions in pixels (approximately)
A4_HEIGHT = 2480
A4_WIDTH = 3508

ITEM_TYPES = [i.value for i in ItemType]


def make_qr_grid(qr_data: Iterable, output_file_path: str, num_x=4, num_y=2):
    # Create an eighth-sized image
    box_width = A4_WIDTH // num_x
    box_height = A4_HEIGHT // num_y

    with Image.new("RGB", (A4_WIDTH, A4_HEIGHT), "white") as im:
        draw = ImageDraw.Draw(im)

        for i in range(1, num_y):
            draw.line(
                (0, i * A4_HEIGHT // num_y) + (A4_WIDTH, i * A4_HEIGHT // num_y),
                fill=128,
            )
        for i in range(1, num_x):
            draw.line((box_width * i, 0, box_width * i, A4_HEIGHT), fill=128)

        for i in range(num_x * num_y):
            # Generate a random QR code
            qr = qrcode.make(next(qr_data))
            qr_size = int(0.75 * min(box_width, box_height))
            qr = qr.resize((qr_size, qr_size))

            box_offset = ((i % num_x) * box_width, (i // num_x) * box_height)

            x_offset = box_width // 2 - qr_size // 2
            y_offset = box_height // 2 - qr_size // 2
            qr_offset_sz = min(x_offset, y_offset)
            qr_offset = (box_offset[0] + qr_offset_sz, box_offset[1] + qr_offset_sz)

            im.paste(qr, qr_offset)

        # show
        im.save(output_file_path, "PNG")


@click.command()
@click.option(
    "--type",
    "-t",
    type=click.Choice(ITEM_TYPES),
    prompt="Item type",
    help="Item type to generate.",
)
@click.option("-x", default=4, help="Grid size - width")
@click.option("-y", default=2, help="Grid size - height")
@click.option(
    "--num",
    "-n",
    default=1,
    help="If relevant for this item, the number that should be awarded per QR scan",
)
@click.option(
    "--damage",
    "-d",
    default=1,
    help="For weapons, the damage per shot",
)
@click.option(
    "--timeout",
    "-m",
    default=6,
    help="For weapons, the timeout",
)
@click.option(
    "--outdir",
    "-o",
    type=click.Path(
        exists=True, file_okay=False, dir_okay=True, writable=True, resolve_path=True
    ),
    default=".",
    help="Output path",
)
@click.option(
    "--outfile",
    type=click.Path(file_okay=True, dir_okay=False, writable=True, resolve_path=True),
    default=None,
    help=(
        "Normally output files will have random variations in their name. "
        "Pass this parameter to choose the name. "
        "Existing files will be overwritten."
    ),
)
def generate(
    type: str,
    x: int,
    y: int,
    num: int,
    outdir: str,
    outfile: Optional[str],
    damage: int,
    timeout: float,
):
    """
    Generates an A4 grid of QR codes that can be scanned to collect an item
    """

    def generate_random_string(length):
        import random
        import string

        characters = string.ascii_letters + string.digits
        return "".join(random.choice(characters) for _ in range(length))

    if not outfile:
        rand_chars = generate_random_string(6)
        filename = f"qrcodes_{rand_chars}_{type}_{num}.png"
        outfile = Path(outdir, filename)

    logger.debug("Outputting to %s", outfile)

    qr_data = (
        AdminInterface().make_new_item(
            type,
            {
                "num": num,
                "shot_damage": damage,
                "shot_timeout": timeout,
            },
        )
        for _ in range(x * y)
    )
    make_qr_grid(qr_data, outfile, x, y)


if __name__ == "__main__":
    generate()
