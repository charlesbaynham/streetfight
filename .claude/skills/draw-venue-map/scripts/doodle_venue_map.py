"""Draw the doodles for a venue map: one little line drawing per pub.

The map itself is rendered from OpenStreetMap geometry (`render_venue_map.py`)
because image models cannot trace - but the *doodles* are the one thing on
the Kingston map that only an illustrator can supply, and a doodle carries
no geometry to get wrong. So the image model is asked for exactly that and
nothing else: a small pen sketch of a cartwheel, an oak tree, a boar, on a
plain white sheet. Where it goes on the map is decided by the renderer, which
knows where the roads and the names are; the model never sees the map.

## What one costs, and not paying twice

Every doodle is content-addressed on the model and the whole prompt, so
re-running this when nothing has changed asks the model for nothing at all,
and editing one subject regenerates that one drawing. The model's raw answer
is kept beside the processed file (under `doodles/raw/`, which is not
committed) so the ink conversion below can be re-tuned for free.

## Transparency

Image models do not reliably return alpha - a request for a transparent
background comes back as a chequerboard drawn in pixels as often as not. The
model is asked for **black ink on pure white** instead, which it does well,
and the transparency is made here: luminance becomes alpha, the paper drops
out entirely and the ink is recoloured to the map's own sepia. That is
deterministic and it cannot leave a white square on the map.

Usage:

    OPENROUTER_API_KEY=... uv run python doodle_venue_map.py \
        --bundle docs/venue_map_westminster            # every doodle in doodles.json
    uv run python doodle_venue_map.py --bundle ... --dry-run     # say what it would spend
    uv run python doodle_venue_map.py --bundle ... --only "Royal Oak" --force
    uv run python doodle_venue_map.py --bundle ... --reprocess   # re-run the ink conversion

Then re-run `render_venue_map.py`, which picks the drawings up from the bundle.

`doodles.json` in the bundle is a list of entries:

    {"marker": "Royal Oak", "subject": "an oak tree"}
    {"at": [51.5016, -0.1236], "subject": "a rowing boat", "size": 130}

`marker` names a marker in `meta.json` and the doodle goes beside it; `at`
puts one anywhere by coordinate - the river, the park. `size` is its longest
side on the 2000 px sheet (default `DOODLE_PX`).
"""

import argparse
import base64
import hashlib
import io
import json
import os
import re
import sys
import urllib.error
import urllib.request

from PIL import Image

MODEL = "google/gemini-3.1-flash-image"
OPENROUTER_IMAGE_URL = "https://openrouter.ai/api/v1/images"
TIMEOUT_S = 120
ATTEMPTS = 3

# What a doodle is, spelled out for the model. "Black felt-tip on white" is
# the part that makes the transparency below work; "nothing else in the
# picture" is the part that stops it drawing a frame, a caption or a shadow,
# each of which has come back uninvited when it was not ruled out.
STYLE = (
    "A single small doodle to be pasted onto a hand-drawn map: {subject}. "
    "Quick sketch in black felt-tip pen, bold confident strokes, only a few "
    "lines, the way somebody doodles in the margin of a map. Line art only: "
    "no shading, no hatching, no fill, no grey, no colour. Pure white "
    "background with nothing else in the picture - no text, no caption, no "
    "border, no frame, no ground line, no shadow. The drawing is centred and "
    "fills most of the frame."
)

DOODLE_PX = 110  # longest side on the 2000 px sheet, about a block's width
STORE_PX = 400  # the processed file's longest side: 3x what the raster needs

# Luminance in, alpha out: anything lighter than PAPER_L is paper and drops
# out completely, anything darker than INK_L is solid ink, and the antialiased
# edge between them is a straight ramp.
PAPER_L = 225
INK_L = 110

# The map's ink, so a doodle is drawn in the same pen as the roads. Kept here
# rather than imported from the renderer so this file has no dependency on
# it: the renderer imports this one.
INK = "#2f2418"


class DoodleError(RuntimeError):
    pass


# --------------------------------------------------------------------------
# The manifest, and where each drawing lives
# --------------------------------------------------------------------------


def slug(text):
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")


def load_manifest(bundle):
    path = os.path.join(bundle, "doodles.json")
    if not os.path.exists(path):
        return []
    entries = json.load(open(path))
    for entry in entries:
        if "subject" not in entry or ("marker" not in entry and "at" not in entry):
            raise DoodleError(
                f"{path}: each entry needs 'subject' and 'marker' or 'at': {entry}"
            )
    return entries


def prompt_for(entry):
    return STYLE.format(subject=entry["subject"])


def doodle_id(entry, model=MODEL):
    """Content address: the model and the whole prompt, nothing else."""
    return hashlib.sha256(f"{model}\n{prompt_for(entry)}".encode()).hexdigest()[:12]


def doodle_name(entry):
    return slug(entry.get("marker") or entry["subject"])


def doodle_path(bundle, entry, model=MODEL):
    """The processed RGBA PNG the renderer pastes onto the map."""
    return os.path.join(
        bundle, "doodles", f"{doodle_name(entry)}.{doodle_id(entry, model)}.png"
    )


def raw_path(bundle, entry, model=MODEL):
    return os.path.join(
        bundle, "doodles", "raw", f"{doodle_name(entry)}.{doodle_id(entry, model)}.png"
    )


# --------------------------------------------------------------------------
# Asking the model
# --------------------------------------------------------------------------


def generate(prompt, api_key, model=MODEL):
    """Return the model's image as PNG bytes, via OpenRouter's Image API.

    The Image endpoint, not chat completions: that is where the image models
    are served and it answers with base64 (see `vision_client.py`'s
    `OpenRouterImageClient`, whose docstring records the evening spent
    finding that out). Not that class itself, because it refuses Google
    models on purpose - the test world must not be generated by the family
    that recognises it - and that reasoning does not apply to a doodle.
    """
    body = json.dumps({"model": model, "prompt": prompt, "n": 1}).encode()
    request = urllib.request.Request(
        OPENROUTER_IMAGE_URL,
        data=body,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
    )
    last = None
    for attempt in range(1, ATTEMPTS + 1):
        try:
            with urllib.request.urlopen(request, timeout=TIMEOUT_S) as response:
                reply = json.load(response)
            break
        except urllib.error.HTTPError as e:
            text = e.read()[:300].decode(errors="replace")
            if e.code == 429 or e.code >= 500:  # not billed; retrying is free
                last = DoodleError(f"OpenRouter returned {e.code}: {text}")
                continue
            raise DoodleError(f"OpenRouter rejected the request ({e.code}): {text}")
        except (urllib.error.URLError, TimeoutError) as e:
            last = DoodleError(f"could not reach OpenRouter: {e}")
    else:
        raise last

    for image in reply.get("data") or []:
        if image.get("b64_json"):
            cost = (reply.get("usage") or {}).get("cost")
            return base64.b64decode(image["b64_json"]), cost
    raise DoodleError(f"the model returned no image: {json.dumps(reply)[:300]}")


# --------------------------------------------------------------------------
# Ink on white -> sepia on nothing
# --------------------------------------------------------------------------


def _rgb(colour):
    value = int(colour[1:], 16)
    return (value >> 16, (value >> 8) & 0xFF, value & 0xFF)


def ink_to_alpha(image, paper_l=PAPER_L, ink_l=INK_L, ink=INK, store_px=STORE_PX):
    """Turn black-on-white line art into sepia ink on a transparent sheet.

    Luminance drives the alpha, so a grey antialiased edge becomes a
    half-transparent edge rather than a grey fringe; the colour is the map's
    ink everywhere. Then trimmed to the ink and scaled to `store_px`, since
    the model's frame is mostly paper and the renderer only needs a fraction
    of the pixels.
    """
    lum = image.convert("L")
    span = max(1, paper_l - ink_l)
    alpha = lum.point(
        lambda v: (
            255
            if v <= ink_l
            else 0 if v >= paper_l else int(255 * (paper_l - v) / span)
        )
    )
    out = Image.new("RGBA", image.size, _rgb(ink) + (0,))
    out.putalpha(alpha)

    bbox = alpha.point(lambda v: 255 if v > 24 else 0).getbbox()
    if bbox is None:
        raise DoodleError("the drawing came back blank")
    out = out.crop(bbox)
    if max(out.size) > store_px:
        scale = store_px / max(out.size)
        out = out.resize(
            (max(1, round(out.width * scale)), max(1, round(out.height * scale))),
            Image.LANCZOS,
        )
    # Sixteen levels of alpha are plenty for an antialiased edge and cost a
    # fraction of the bytes: these files are committed, and embedded in the SVG.
    out.putalpha(out.getchannel("A").point(lambda v: (v // 16) * 17))
    return out


def process(raw_bytes):
    return ink_to_alpha(Image.open(io.BytesIO(raw_bytes)))


# --------------------------------------------------------------------------
# The run
# --------------------------------------------------------------------------


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument(
        "--bundle", required=True, help="the venue bundle holding doodles.json"
    )
    ap.add_argument("--model", default=MODEL)
    ap.add_argument(
        "--only",
        action="append",
        default=[],
        help="a marker or subject to do; repeatable",
    )
    ap.add_argument(
        "--force", action="store_true", help="regenerate even if the drawing exists"
    )
    ap.add_argument(
        "--reprocess",
        action="store_true",
        help="redo the ink conversion from the raw files",
    )
    ap.add_argument(
        "--dry-run", action="store_true", help="list what would be asked for, and stop"
    )
    args = ap.parse_args()

    entries = load_manifest(args.bundle)
    if not entries:
        raise SystemExit(f"no doodles.json in {args.bundle}, or it is empty")
    if args.only:
        wanted = {slug(o) for o in args.only}
        entries = [
            e
            for e in entries
            if doodle_name(e) in wanted or slug(e["subject"]) in wanted
        ]
        if not entries:
            raise SystemExit(f"nothing in doodles.json matches {args.only}")

    os.makedirs(os.path.join(args.bundle, "doodles", "raw"), exist_ok=True)
    ignore = os.path.join(args.bundle, "doodles", "raw", ".gitignore")
    if not os.path.exists(ignore):
        open(ignore, "w").write("*\n!.gitignore\n")

    todo, kept = [], []
    for entry in entries:
        out = doodle_path(args.bundle, entry, args.model)
        raw = raw_path(args.bundle, entry, args.model)
        if args.reprocess and os.path.exists(raw):
            process(open(raw, "rb").read()).save(out, optimize=True)
            print(f"reprocessed {out}")
        elif os.path.exists(out) and not args.force:
            kept.append(entry)
        else:
            todo.append(entry)

    for entry in kept:
        print(f"have      {doodle_name(entry)}  ({doodle_id(entry, args.model)})")
    for entry in todo:
        print(f"generate  {doodle_name(entry)}: {entry['subject']}")
    if not todo:
        print("nothing to generate")
        return
    if args.dry_run:
        print(
            f"\n{len(todo)} to generate with {args.model}; run without --dry-run to spend it"
        )
        return

    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        raise SystemExit("OPENROUTER_API_KEY is not set")

    total = 0.0
    failed = []
    for entry in todo:
        name = doodle_name(entry)
        try:
            raw_bytes, cost = generate(prompt_for(entry), api_key, args.model)
            open(raw_path(args.bundle, entry, args.model), "wb").write(raw_bytes)
            drawn = process(raw_bytes)
            drawn.save(doodle_path(args.bundle, entry, args.model), optimize=True)
        except DoodleError as e:
            failed.append((name, str(e)))
            print(f"FAILED    {name}: {e}")
            continue
        total += cost or 0.0
        print(
            f"drew      {name}  {drawn.width}x{drawn.height}  ${cost if cost is not None else '?'}"
        )

    print(
        f"\n{len(todo) - len(failed)} drawn, ${total:.3f}; now re-run render_venue_map.py"
    )
    if failed:
        print(f"{len(failed)} failed - re-run to try them again:")
        for name, why in failed:
            print(f"  {name}: {why}")
        sys.exit(1)


if __name__ == "__main__":
    main()
