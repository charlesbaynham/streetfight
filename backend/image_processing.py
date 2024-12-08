import base64
import logging
import time
from io import BytesIO
from pathlib import Path
from typing import List
from typing import Tuple

from PIL import Image
from PIL import ImageDraw

logger = logging.getLogger(__name__)

IMAGE_OUTPUT_DIR = Path("./logs/images").resolve()


def save_image(base64_image: str, name: str, output_dir: Path = None):
    """Save this image to the folder, tagged with the time

    Args:
        base64_image (str): base 64 image
    """
    if output_dir is None:
        output_dir = IMAGE_OUTPUT_DIR

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

    # Define text position (top right corner)
    text_position = (width - 20, 20)

    # Define text to display
    text = ""
    for key, value in stats.items():
        text += f"{key}: {value}\n"

    # Add text to the image
    draw.text(text_position, text, fill=text_color, size=text_size, align="right")

    # Convert the image back to base64
    modified_image_bytes = BytesIO()
    image.save(modified_image_bytes, format="PNG")
    modified_base64_image = base64.b64encode(modified_image_bytes.getvalue()).decode()

    # Close the image file
    image.close()

    # Put the metadata back
    split_img[1] = modified_base64_image

    return ",".join(split_img)


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
