"""A content-addressed image store: the hash *is* the identity.

An image's name is the digest of everything that determines what it looks
like -- the prompt verbatim, the bytes of every input image, the model id and
the generation parameters. Two consequences follow, and both are the point:

* **Present in the store means no API call.** The only trigger for generation
  is absence. So a second run costs nothing, and editing one scene
  description costs exactly the images it touches.
* **Changing an input cascades correctly.** Because the input images are
  hashed by content, replacing the background or a reference photo changes
  the id of every image conditioned on it. Nothing can go stale silently.

The filesystem carries no human-readable names. ``world.json`` maps slug and
scenario id to image id, so two identical prompts cannot produce two copies of
the same bytes under different names.
"""

import base64
import hashlib
import json
from pathlib import Path
from typing import Dict
from typing import List
from typing import Optional


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(Path(path).read_bytes())


def image_id(
    kind: str,
    prompt: str,
    input_paths: List[Path],
    model: str,
    params: Optional[Dict] = None,
) -> str:
    """The identity of an image that has not been generated yet."""
    payload = {
        "kind": kind,
        "prompt": prompt,
        "inputs": [sha256_file(p) for p in input_paths],
        "model": model,
        "params": params or {},
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()[:16]


class ImageStore:
    """The flat directory of generated images."""

    def __init__(self, root: Path):
        self.root = Path(root)

    def path_for(self, image_id_: str) -> Path:
        return self.root / f"{image_id_}.jpg"

    def has(self, image_id_: str) -> bool:
        return self.path_for(image_id_).exists()

    def save_data_url(self, image_id_: str, data_url: str) -> Path:
        """Write a ``data:image/...;base64,...`` URL out as JPEG.

        JPEG specifically, because ``scripts/replay_shot_reviews`` hard-codes
        a ``data:image/jpeg;base64,`` prefix when it loads a fixture, so a PNG
        here would be mislabelled the moment anybody replayed it.
        """
        if "," not in data_url:
            raise ValueError("not a data URL")
        header, encoded = data_url.split(",", 1)
        raw = base64.b64decode(encoded)

        self.root.mkdir(parents=True, exist_ok=True)
        path = self.path_for(image_id_)

        if "image/jpeg" not in header and "image/jpg" not in header:
            from io import BytesIO

            from PIL import Image

            image = Image.open(BytesIO(raw)).convert("RGB")
            image.save(path, "JPEG", quality=92)
        else:
            path.write_bytes(raw)
        return path

    def stats(self) -> Dict:
        if not self.root.exists():
            return {"count": 0, "bytes": 0}
        files = list(self.root.glob("*.jpg"))
        return {"count": len(files), "bytes": sum(f.stat().st_size for f in files)}
