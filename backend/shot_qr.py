"""Whether a shot photograph is really a QR code somebody meant to scan.

The fire button and the scanner are a tap apart, so now and then a player
photographs a card instead of collecting it. Such a shot is refunded before
the vision model is asked anything about it.

Only a code this game signed counts: somebody else's QR in the background of a
real shot - a pub's wifi, a poster - is no evidence the shooter was scanning.
"""

import json
import logging
from typing import Optional

import zxingcpp

from .image_processing import load_image
from .items import ItemModel
from .join_codes import JoinCodeModel
from .utils import parse_code_or_none

logger = logging.getLogger(__name__)


def _signed_code(text: str):
    """The item or join code ``text`` is, or None unless the game signed it."""
    for parser in (ItemModel.from_base64, JoinCodeModel.from_base64):
        code = parse_code_or_none(parser, text)
        if code is not None and code.validate_signature() is None:
            return code
    return None


def _is_streetfight_code(text: str) -> bool:
    return _signed_code(text) is not None


def refund_note(text: str) -> str:
    """Why the shot was refunded, in the admin's notes on it."""
    code = _signed_code(text)
    if isinstance(code, ItemModel):
        what = f"{code.itype.value} item code {json.dumps(code.data)}"
        if code.batch:
            what += f", batch {code.batch!r}"
    else:
        what = "join code"
    return (
        f"Refunded automatically: the photo shows one of the game's QR codes "
        f"({what}), so the player was most likely trying to scan it."
    )


def streetfight_code_in(image_base64: str) -> Optional[str]:
    """The text of the first signed game code visible in the photo, if any."""
    try:
        image, _ = load_image(image_base64)
        image = image.convert("L")
    except Exception:
        return None

    for result in zxingcpp.read_barcodes(image, formats=zxingcpp.BarcodeFormat.QRCode):
        if _is_streetfight_code(result.text):
            return result.text
        logger.debug("Ignoring a QR code that is not ours: %s", result.text[:200])

    return None
