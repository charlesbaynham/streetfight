from pathlib import Path
from typing import Iterable

import click
import qrcode
from PIL import Image
from PIL import ImageDraw

from .admin_interface import AdminInterface


OUTPUT_PATH = Path(__file__, "../../logs/test.png").resolve()

# A4 dimensions in pixels (approximately)
A4_HEIGHT = 2480
A4_WIDTH = 3508


def make_qr_grid(qr_data: Iterable, num_x=4, num_y=2):
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
        im.save(OUTPUT_PATH, "PNG")


@click.command()
@click.option(
    "--type",
    prompt="Item type:",
    help='Item type to generate. Should be "ammo","medpack" or "armour".',
)
@click.option("--x", default=4, help="Grid size - width")
@click.option("--y", default=2, help="Grid size - height")
@click.option(
    "--num",
    "-n",
    default=1,
    help="If relevant for this item, the number that should be awarded per QR scan",
)
def generate(type: str, x: int, y: int, num: int):
    """
    Generates an A4 grid of QR codes that can be scanned to collect an item
    """

    qr_data = (AdminInterface().make_new_item(type, {"num": num}) for _ in range(x * y))
    make_qr_grid(qr_data, x, y)


if __name__ == "__main__":
    generate()
