import base64
import logging
import time
from io import BytesIO
from pathlib import Path
from typing import List
from typing import Tuple

from PIL import Image
from PIL import ImageDraw
from PIL import ImageFont

logger = logging.getLogger(__name__)

IMAGE_OUTPUT_DIR = Path("./logs/images").resolve()


def save_image(base64_image: str, name: str, output_dir: Path = None):
    """Save this image to the folder, tagged with the time

    Args:
        base64_image (str): base 64 image
    """

    if output_dir is None:
        output_dir = IMAGE_OUTPUT_DIR

    output_dir = Path(output_dir)

    image, _ = load_image(base64_image)
    filename = f"{name}_{time.time()}.png"
    output_dir.mkdir(exist_ok=True, parents=True)
    image.save(output_dir / filename)


def load_image(base64_image: str) -> Tuple[Image.Image, List[str]]:
    # Split off the metadata
    split_img = base64_image.split(",")
    raw_image = split_img[1]

    # Decode base64 string to bytes
    image_bytes = base64.b64decode(raw_image)

    # Load the image using PIL (Python Imaging Library)
    image = Image.open(BytesIO(image_bytes))

    return image, split_img


def annotate_image_with_stats(base64_image: str, stats: dict) -> str:
    image, split_img = load_image(base64_image)

    # Get image dimensions
    width, height = image.size

    # Create a drawing object
    draw = ImageDraw.Draw(image)

    # Define text color (white in RGB)
    text_color = (255, 255, 255)

    # Define text size (adjust as needed)
    text_size = 20

    # Define text position (bottom left corner)
    text_position = (10, height - text_size * 5)

    # Define text to display
    text = ""
    for key, value in stats.items():
        text += f"{key}: {value}\n"

    # Draw a black box in the bottom left. Pillow >= 10 rejects a rectangle
    # whose y1 is above its y0, so the top corner has to come first.
    draw.rectangle(
        [
            (0, height - 6 * text_size),
            (300, height),
        ],
        fill=(0, 0, 0),
    )

    # Add text to the image
    # TODO: Make this less fragile
    font = ImageFont.truetype(
        str(Path(__file__, "../UbuntuMono-R.ttf").resolve()), text_size
    )
    draw.text(text_position, text, font=font, fill=text_color, align="left")

    out = _to_base64(image, split_img)
    image.close()
    return out


def _to_base64(
    image: Image.Image, split_img: List[str], format: str = "JPEG", quality: int = 85
) -> str:
    """Re-encode a PIL image back into the data URL it came from.

    JPEG, not PNG: these are photographs, and PNG re-encoding inflated them
    roughly fivefold on a path that runs on every admin queue fetch.
    """
    if format == "JPEG" and image.mode not in ("RGB", "L"):
        image = image.convert("RGB")

    buffer = BytesIO()
    image.save(
        buffer, format=format, **({"quality": quality} if format == "JPEG" else {})
    )
    split_img = list(split_img)
    split_img[0] = f"data:image/{format.lower()};base64"
    split_img[1] = base64.b64encode(buffer.getvalue()).decode()
    return ",".join(split_img)


def _draw_aim_marker_on(image: Image.Image) -> None:
    """Draw the crosshair onto a PIL image, in place.

    A single-pixel-wide red cross spans the full frame -- one horizontal line,
    one vertical line -- so the marker survives downsizing and JPEG
    compression even far from the centre, rather than the old short arms
    which could visually touch a target without actually being over it
    (roadmap R1). The lines themselves are guides only: the one pixel where
    they cross is the aim point (see the vision prompt), nothing else they
    happen to pass over.
    """
    draw = ImageDraw.Draw(image)
    width, height = image.size
    centre_x, centre_y = width // 2, height // 2

    draw.line([(0, centre_y), (width - 1, centre_y)], fill=(255, 0, 0), width=1)
    draw.line([(centre_x, 0), (centre_x, height - 1)], fill=(255, 0, 0), width=1)


def draw_aim_marker(base64_image: str) -> str:
    """Mark where the shot landed: a crosshair at the centre of the frame.

    Deliberately *not* :func:`draw_cross_on_image`, which also pastes a
    magnified copy of the centre crop into the top-left corner. That is helpful
    for a human squinting at a phone, but it puts a second copy of the target
    into the picture, which is exactly the wrong thing to hand a vision model.
    """
    image, split_img = load_image(base64_image)
    _draw_aim_marker_on(image)
    out = _to_base64(image, split_img)
    image.close()
    return out


def downscale_jpeg(
    base64_image: str, max_dimension: int = 1024, quality: int = 85
) -> str:
    """Shrink an image to fit ``max_dimension`` and re-encode it as JPEG.

    Images already within ``max_dimension`` are re-encoded but not upscaled.
    """
    image, split_img = load_image(base64_image)

    width, height = image.size
    longest = max(width, height)
    if longest > max_dimension:
        scale = max_dimension / longest
        image = image.resize(
            (max(1, round(width * scale)), max(1, round(height * scale))),
            Image.LANCZOS,
        )

    # JPEG has no alpha channel, and shot photos never meaningfully have one
    if image.mode not in ("RGB", "L"):
        image = image.convert("RGB")

    buffer = BytesIO()
    image.save(buffer, format="JPEG", quality=quality)
    image.close()

    encoded = base64.b64encode(buffer.getvalue()).decode()
    return f"data:image/jpeg;base64,{encoded}"


def prepare_for_vision(
    base64_image: str, max_dimension: int = 1024, quality: int = 85
) -> str:
    """Downsize and re-encode a shot photo for sending to a vision model.

    Phone photos are far larger than any model needs, and image tokens are the
    dominant cost of reviewing a queue. 1024px is a floor rather than an
    aggressive shrink: the measured failure mode (plan §12.1) is that small
    targets get invented answers, so there is nothing to gain by going lower.
    """
    return downscale_jpeg(base64_image, max_dimension=max_dimension, quality=quality)


def zoom_image(
    base64_image: str, factor: int = 8, max_dimension: int = 1024, quality: int = 85
) -> str:
    """The centre of a photo, magnified: crop 1/``factor`` of each dimension.

    Feed this the **original** photo, never the output of
    :func:`prepare_for_vision`. The whole point is to spend camera resolution
    that the downsize threw away; zooming an already-downsized image just
    magnifies the blur.

    The shot lands at the centre of the frame, so a central crop keeps the
    target centred and a fresh aim marker is drawn afterwards, spanning the
    cropped frame the same way it spans the full photo.
    """
    if factor < 1:
        raise ValueError(f"zoom factor must be at least 1; got {factor}")

    image, _ = load_image(base64_image)
    width, height = image.size

    crop_width = max(1, width // factor)
    crop_height = max(1, height // factor)
    left = (width - crop_width) // 2
    top = (height - crop_height) // 2
    cropped = image.crop((left, top, left + crop_width, top + crop_height))
    image.close()

    if cropped.mode not in ("RGB", "L"):
        cropped = cropped.convert("RGB")

    # Scale back up to the same output size the un-zoomed image was sent at, so
    # the model sees the target eight times larger rather than a small crop.
    longest = max(cropped.size)
    if longest != max_dimension and longest > 0:
        scale = max_dimension / longest
        cropped = cropped.resize(
            (
                max(1, round(cropped.width * scale)),
                max(1, round(cropped.height * scale)),
            ),
            Image.LANCZOS,
        )

    _draw_aim_marker_on(cropped)

    buffer = BytesIO()
    cropped.save(buffer, format="JPEG", quality=quality)
    cropped.close()

    encoded = base64.b64encode(buffer.getvalue()).decode()
    return f"data:image/jpeg;base64,{encoded}"


def draw_cross_on_image(base64_image: str) -> str:
    image, split_img = load_image(base64_image)

    # Get image dimensions
    width, height = image.size

    # Create a drawing object
    draw = ImageDraw.Draw(image)

    # Define line color (white in RGB)
    line_color = (255, 255, 255)

    # Define line thickness (adjust as needed)
    line_thickness = 1

    # Add a horizontal line to the center
    draw.line(
        [(0, height // 2), (width, height // 2)], fill=line_color, width=line_thickness
    )

    # Add a vertical line to the center
    draw.line(
        [(width // 2, 0), (width // 2, height)], fill=line_color, width=line_thickness
    )

    # Calculate the coordinates for the middle 10% of the image
    width, height = image.size
    left = width * 0.45  # 45% from the left
    top = height * 0.45  # 45% from the top
    right = width * 0.55  # 55% from the left
    bottom = height * 0.55  # 55% from the top

    # Crop the middle 10%
    cropped = image.crop((left, top, right, bottom))

    # Create a new image with a white border
    border_size = 1
    cropped_with_border = Image.new(
        "RGB",
        (cropped.width + border_size, cropped.height + border_size),
        "white",
    )

    # Paste the cropped middle portion onto the new image
    cropped_with_border.paste(cropped)

    # Double this new image
    expansion_factor = 3
    cropped_with_border = cropped_with_border.resize(
        (
            cropped_with_border.width * expansion_factor,
            cropped_with_border.height * expansion_factor,
        )
    )

    # Paste the cropped image back into the original
    image.paste(cropped_with_border, (0, 0))

    out = _to_base64(image, split_img)
    image.close()
    return out
