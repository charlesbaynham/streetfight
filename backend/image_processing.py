import base64
import logging
from io import BytesIO

from PIL import Image
from PIL import ImageDraw

logger = logging.getLogger(__name__)


def draw_cross_on_image(base64_image: str) -> str:
    logger.debug("Image = %s", base64_image)

    # Decode base64 string to bytes
    image_bytes = base64.b64decode(base64_image)

    # Load the image using PIL (Python Imaging Library)
    image = Image.open(BytesIO(image_bytes))

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

    # Optionally, you can convert the image back to base64 if needed
    modified_image_bytes = BytesIO()
    image.save(modified_image_bytes, format="PNG")
    modified_base64_image = base64.b64encode(modified_image_bytes.getvalue()).decode()

    # Close the image file
    image.close()

    return modified_base64_image
