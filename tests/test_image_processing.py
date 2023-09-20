from pathlib import Path

from backend.image_processing import draw_cross_on_image
from backend.image_processing import load_image


def test_image_loading():
    test_image_string = (
        Path(__file__, "../sample_base64_image.txt").resolve().read_text()
    )

    load_image(test_image_string)


def test_image_processsing():
    test_image_string = (
        Path(__file__, "../sample_base64_image.txt").resolve().read_text()
    )
    draw_cross_on_image(test_image_string)


def test_image_processsing_save_output():
    test_image_string = (
        Path(__file__, "../sample_base64_image.txt").resolve().read_text()
    )

    image_out = draw_cross_on_image(test_image_string)
    image, _ = load_image(image_out)
    image.save(Path(__file__, "../../logs/test_output.png").resolve())
