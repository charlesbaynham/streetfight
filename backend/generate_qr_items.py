import logging
from pathlib import Path
from typing import Iterable
from typing import Optional
from typing import Union

import click
import qrcode
from PIL import Image
from PIL import ImageDraw

from .admin_interface import AdminInterface
from .items import ItemModel
from .model import ItemType
from .utils import slugify_string

logger = logging.getLogger(__name__)

# A4 dimensions in pixels (approximately)
A4_HEIGHT = 2480
A4_WIDTH = 3508

# Space between images
IMAGE_GUTTER = 100

QR_LOGFILE = Path(__file__, "../../qr_codes.csv").resolve()
IMAGES_DIR = Path(__file__, "../image_templates").resolve()

ITEM_TYPES = [i.value for i in ItemType]


def make_qr_grid(
    qr_data: Iterable,
    output_file_path: str,
    num_x=4,
    num_y=2,
    tag: str = "",
    base_image: Union[str, Path] = None,
):
    # Create an eighth-sized image
    box_width = A4_WIDTH // num_x
    box_height = A4_HEIGHT // num_y

    if base_image:
        base_image_loaded = Image.open(base_image)

        # Crop the base image to remove all transparent borders
        bbox = base_image_loaded.getbbox()
        if bbox:
            base_image_loaded = base_image_loaded.crop(bbox)

        # Resize it to fill the box
        base_image_loaded = base_image_loaded.resize((box_width, box_height))
    else:
        base_image_loaded = None

    # Make the boxes
    sub_images = []
    for i in range(num_x * num_y):
        # Make a new image for this box
        sub_img = Image.new("RGBA", (box_width, box_height), "white")
        draw_subimg = ImageDraw.Draw(sub_img)

        # Generate the next QR code
        qr = qrcode.make(next(qr_data))
        qr_size = int(0.75 * min(box_width, box_height))
        qr = qr.resize((qr_size, qr_size))

        # Paste the QR code
        qr_x_offset = box_width // 2 - qr_size // 2
        qr_y_offset = box_height // 2 - qr_size // 2
        qr_offset_sz = min(qr_x_offset, qr_y_offset)
        qr_offset = (qr_offset_sz, qr_offset_sz)
        sub_img.paste(qr, qr_offset)

        # Paste the base image if it exists
        if base_image_loaded:
            sub_img.paste(base_image_loaded, (0, 0), mask=base_image_loaded)

        # Add a text tag
        draw_subimg.text((10, 10), tag + f"{i}", fill="black")

        # Add the sub-image to the list
        sub_images.append(sub_img)

    # Make the main output image
    with Image.new("RGBA", (A4_WIDTH, A4_HEIGHT), "white") as im:
        draw = ImageDraw.Draw(im)

        # Build a grid
        for i in range(1, num_y):
            draw.line(
                (0, i * A4_HEIGHT // num_y) + (A4_WIDTH, i * A4_HEIGHT // num_y),
                fill=128,
            )
        for i in range(1, num_x):
            draw.line((box_width * i, 0, box_width * i, A4_HEIGHT), fill=128)

        # Paste the sub-images
        for i in range(num_x * num_y):
            sub_img = sub_images[i]

            # Calculate the position of this box
            img_offset = (
                (i % num_x) * box_width + round(IMAGE_GUTTER / 2),
                (i // num_x) * box_height + round(IMAGE_GUTTER / 2),
            )
            new_width = box_width - round(IMAGE_GUTTER)
            new_height = box_height - round(IMAGE_GUTTER)

            im.paste(sub_img.resize((new_width, new_height)), img_offset)

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
    prompt="Number of item",
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
@click.option(
    "--tag",
    default=None,
    help=("Pass a tag to be included in the filename and image"),
)
@click.option(
    "--onceonly",
    default=True,
    help=("If true, the item can only be collected once"),
)
@click.option(
    "--asteam",
    default=False,
    help=("If true, the item is awarded to everyone in the team"),
)
@click.option(
    "--log",
    default=True,
    help=(
        "If true, keep a record of the QR codes generated in a file called `qr_codes.csv`"
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
    log: bool,
    timeout: float,
    tag: str,
    onceonly: bool,
    asteam: bool,
):
    """
    Generates an A4 grid of QR codes that can be scanned to collect an item
    """

    def generate_random_string(length):
        import random
        import string

        characters = string.ascii_letters + string.digits
        return "".join(random.choice(characters) for _ in range(length))

    if not tag:
        tag = generate_random_string(6)

    tag = slugify_string(tag)

    # Get path to base image if one exists
    if type == "weapon":
        path_to_base_image = Path(IMAGES_DIR, f"{type}_{damage}.png")
    else:
        path_to_base_image = Path(IMAGES_DIR, f"{type}_{num}.png")

    if not path_to_base_image.exists():
        logger.warning("No base image found for %s", type)
        path_to_base_image = None

    if not outfile:
        filename = f"qrcodes_{tag}_{type}_{num}.png"
        outfile = Path(outdir, filename)

    logger.debug("Outputting to %s", outfile)

    qr_data = [
        AdminInterface().make_new_item(
            type,
            {
                "num": num,
                "shot_damage": damage,
                "shot_timeout": timeout,
            },
            collected_only_once=onceonly,
            collected_as_team=asteam,
        )
        for _ in range(x * y)
    ]
    make_qr_grid(iter(qr_data), outfile, x, y, tag=tag, base_image=path_to_base_image)

    if log:
        with open(QR_LOGFILE, "a") as f:
            for i, encoded_url in enumerate(qr_data):
                item = ItemModel.from_base64(encoded_url)
                f.write(
                    f"{item.id},{tag},{i},{item.itype},{num},{damage},{timeout},{onceonly},{asteam}\n"
                )


if __name__ == "__main__":
    generate()
