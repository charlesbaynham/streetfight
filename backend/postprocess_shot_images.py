import io
import logging
import os
import tempfile
import zipfile
from pathlib import Path

from .admin_interface import AdminInterface
from .dotenv import load_env_vars
from .image_processing import save_image
from .model import ShotModel

DEFAULT_POSTPROCESS_OUTPUT_DIR = Path(__file__, "../../processed_shots").resolve()

logger = logging.getLogger(__name__)

load_env_vars()


def _render_shot_images(output_dir: Path):
    """Render every shot's marked-up image into ``output_dir``."""

    for shot_id in AdminInterface().get_all_shot_ids():
        shot_model: ShotModel = AdminInterface().get_shot_model(shot_id=shot_id)

        marked_up_shot = AdminInterface.markup_shot_model(
            shot_model, add_targetting=True, add_annotations=True
        )

        save_image(
            base64_image=marked_up_shot.image_base64,
            name=marked_up_shot.user.name,
            output_dir=output_dir,
        )


def output_images():
    """
    Outputs all shot images with markup to POSTPROCESS_OUTPUT_DIR.

    For running by hand on a machine with a persistent disk (`npm run
    annotateShots`) - not what the admin UI's download button uses, since on
    the deployed container that directory isn't something the admin can get
    the files back out of.
    """

    output_dir = os.getenv(
        "POSTPROCESS_OUTPUT_DIR", str(DEFAULT_POSTPROCESS_OUTPUT_DIR)
    )

    _render_shot_images(Path(output_dir))


def zip_shot_images() -> bytes:
    """Render every shot's marked-up image to a scratch cache dir, zip it up,
    and return the zip's bytes - for handing straight back as a download
    rather than leaving files sitting on the (ephemeral) server disk.
    """

    with tempfile.TemporaryDirectory(prefix="shot_images_") as cache_dir:
        cache_dir = Path(cache_dir)
        _render_shot_images(cache_dir)

        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
            for image_path in sorted(cache_dir.glob("*.png")):
                zip_file.write(image_path, arcname=image_path.name)

        return buffer.getvalue()


if __name__ == "__main__":
    output_images()
