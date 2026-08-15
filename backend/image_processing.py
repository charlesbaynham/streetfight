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

    # Draw a black box in the bottom left
    draw.rectangle(
        [
            (0, height),
            (300, height - 6 * text_size),
        ],
        fill=(0, 0, 0),
    )

    # Add text to the image
    # TODO: Make this less fragile
    font = ImageFont.truetype(
        str(Path(__file__, "../UbuntuMono-R.ttf").resolve()), text_size
    )
    draw.text(text_position, text, font=font, fill=text_color, align="left")

    # Convert the image back to base64
    modified_image_bytes = BytesIO()
    image.save(modified_image_bytes, format="PNG")
    modified_base64_image = base64.b64encode(modified_image_bytes.getvalue()).decode()

    # Close the image file
    image.close()

    # Put the metadata back
    split_img[1] = modified_base64_image

    return ",".join(split_img)


def _to_base64(image: Image.Image, split_img: List[str], format: str = "PNG") -> str:
    """Re-encode a PIL image back into the data URL it came from."""
    buffer = BytesIO()
    image.save(buffer, format=format)
    split_img = list(split_img)
    split_img[0] = f"data:image/{format.lower()};base64"
    split_img[1] = base64.b64encode(buffer.getvalue()).decode()
    return ",".join(split_img)


def draw_aim_marker(base64_image: str) -> str:
    """Mark where the shot landed: a crosshair at the centre of the frame.

    Deliberately *not* :func:`draw_cross_on_image`, which also pastes a
    magnified copy of the centre crop into the top-left corner. That is helpful
    for a human squinting at a phone, but it puts a second copy of the target
    into the picture, which is exactly the wrong thing to hand a vision model.
    """
    image, split_img = load_image(base64_image)

    draw = ImageDraw.Draw(image)
    width, height = image.size
    centre_x, centre_y = width // 2, height // 2

    # Scale the marker with the image so it stays visible after downsizing
    arm = max(width, height) // 20
    gap = arm // 3
    thickness = max(2, max(width, height) // 300)

    for colour, offset in (((0, 0, 0), thickness), ((255, 255, 255), 0)):
        for x0, y0, x1, y1 in (
            (centre_x - arm, centre_y, centre_x - gap, centre_y),
            (centre_x + gap, centre_y, centre_x + arm, centre_y),
            (centre_x, centre_y - arm, centre_x, centre_y - gap),
            (centre_x, centre_y + gap, centre_x, centre_y + arm),
        ):
            draw.line(
                [(x0 + offset, y0 + offset), (x1 + offset, y1 + offset)],
                fill=colour,
                width=thickness,
            )

    out = _to_base64(image, split_img)
    image.close()
    return out


def prepare_for_vision(
    base64_image: str, max_dimension: int = 1024, quality: int = 85
) -> str:
    """Downsize and re-encode a shot photo for sending to a vision model.

    Phone photos are far larger than any model needs, and image tokens are the
    dominant cost of reviewing a queue. 1024px is a floor rather than an
    aggressive shrink: the measured failure mode (plan §12.1) is that small
    targets get invented answers, so there is nothing to gain by going lower.

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

    # Convert the image back to base64
    modified_image_bytes = BytesIO()
    image.save(modified_image_bytes, format="PNG")
    modified_base64_image = base64.b64encode(modified_image_bytes.getvalue()).decode()

    # Close the image file
    image.close()

    # Put the metadata back
    split_img[1] = modified_base64_image

    return ",".join(split_img)
