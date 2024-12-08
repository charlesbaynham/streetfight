import logging
from pathlib import Path

from .admin_interface import AdminInterface
from .dotenv import load_env_vars
from .image_processing import save_image
from .model import ShotModel

POSTPROCESS_OUTPUT_DIR = Path(__file__, "../../processed_shots").resolve()

logger = logging.getLogger(__name__)

load_env_vars()


def output_images():
    """
    Outputs all shot images with markup
    """

    for shot_id in AdminInterface().get_all_shot_ids():
        shot_model: ShotModel = AdminInterface().get_shot_model(shot_id=shot_id)

        marked_up_shot = AdminInterface.markup_shot_model(
            shot_model, add_targetting=True, add_annotations=True
        )

        save_image(
            base64_image=marked_up_shot.image_base64,
            name=marked_up_shot.user.name,
            output_dir=POSTPROCESS_OUTPUT_DIR,
        )


if __name__ == "__main__":
    output_images()
