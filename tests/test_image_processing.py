from pathlib import Path

from backend.image_processing import draw_cross_on_image


def test_image_processsing():
    test_image_string = Path(__file__, "../sample_base64_image.txt").read_text()

    draw_cross_on_image(test_image_string)
