import logging
from pathlib import Path
from typing import Iterable
from typing import Optional
from typing import Union

import click
import qrcode
from PIL import Image
from PIL import ImageDraw

from .model import ShotModel

from .admin_interface import AdminInterface
from .items import ItemModel
from .model import ItemType
from .utils import slugify_string

logger = logging.getLogger(__name__)


# @click.option(
#     "--log",
#     default=True,
#     help=(
#         "If true, keep a record of the QR codes generated in a file called `qr_codes.csv`"
#     ),
# )
def output_images():
    """
    Outputs all shot images with markup
    """

    for shot_model in AdminInterface().get_all_shots():
        shot_model: ShotModel

    if log:
        with open(QR_LOGFILE, "a") as f:
            for i, encoded_url in enumerate(qr_data):
                item = ItemModel.from_base64(encoded_url)
                f.write(
                    f"{item.id},{tag},{i},{item.itype},{num},{damage},{timeout},{onceonly},{asteam}\n"
                )


if __name__ == "__main__":
    generate()
