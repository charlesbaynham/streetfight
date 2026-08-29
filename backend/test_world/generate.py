"""Plan and run image generation. Absence from the store is the only trigger.

Nothing here regenerates an image on a measurement, a recogniser
disagreement, or a retry after a gate. Wanting a different picture means
editing the scene description, which changes the prompt, which changes the
hash, which is the whole mechanism. There is deliberately no other way.

The work is planned before any of it is done, so ``--dry-run`` can say exactly
what would be sent and what it would cost -- which is what the spending gates
need, and which also makes the whole pipeline testable without a key.
"""

import asyncio
from pathlib import Path
from typing import Dict
from typing import List
from typing import NamedTuple
from typing import Optional

from backend.test_world import store as store_mod

PRIMARY_MODEL = "openai/gpt-5.4-image-2"
FALLBACK_MODEL = "openai/gpt-5-image"
CHEAP_MODEL = "openai/gpt-5-image-mini"

# Dollars per generated image, for the gate arithmetic. Approximate and
# deliberately rounded up; the point is an honest ceiling, not accountancy.
PRICE = {PRIMARY_MODEL: 0.03, FALLBACK_MODEL: 0.04, CHEAP_MODEL: 0.0075}

HARD_CEILING_USD = 8.00


class Job(NamedTuple):
    kind: str  # reference | shot | background | ab
    name: str  # player slug, scenario id, or a label
    prompt: str
    inputs: List[Path]
    model: str
    params: Dict
    image_id: str

    @property
    def price(self) -> float:
        return PRICE.get(self.model, PRICE[PRIMARY_MODEL])


def _fixture_dir(world_path: Path) -> Path:
    return Path(world_path).parent


def plan(
    world: dict,
    world_path: Path,
    gate: Optional[str] = None,
    seed: int = 1,
) -> List[Job]:
    """Every image the world calls for, whether or not it already exists."""
    fixtures = _fixture_dir(world_path)
    background = fixtures / "background_living_room.jpg"
    card = fixtures / "kit_swatches.png"

    if not card.exists():
        raise FileNotFoundError(f"{card} is missing - run `scenes` first")
    if not background.exists():
        raise FileNotFoundError(
            f"{background} is missing - supply the background photo, or "
            "generate one, before any reference photo"
        )

    scenes = world["scenes"]
    jobs: List[Job] = []

    def add(kind, name, prompt, inputs, model, params=None):
        params = params or {"seed": seed}
        jobs.append(
            Job(
                kind=kind,
                name=name,
                prompt=prompt,
                inputs=inputs,
                model=model,
                params=params,
                image_id=store_mod.image_id(kind, prompt, inputs, model, params),
            )
        )

    references = {r["slug"]: r for r in scenes["references"]}
    shots = {s["scenario"]: s for s in scenes["shots"]}

    if gate == "c":
        # The repeatability test: one person's reference photo, then that same
        # person rendered into a scene from it, so we can see whether the face
        # and the kit survive the trip. Plus the one-image A/B against the
        # cheap model, since it is a quarter of the price and worth knowing.
        probe = shots["S1"]["target"]["slug"]
        add(
            "reference",
            probe,
            references[probe]["prompt"],
            [background, card],
            PRIMARY_MODEL,
        )
        add(
            "ab",
            f"{probe}-mini",
            references[probe]["prompt"],
            [background, card],
            CHEAP_MODEL,
        )
        add("shot", "S1", shots["S1"]["prompt"], [card], PRIMARY_MODEL)
        return jobs

    if gate == "d":
        # Deliberately awkward: the extremes of the palette and the scene
        # whose whole point is that two garments are missing.
        for slug in _awkward_players(world)[:3]:
            add(
                "reference",
                slug,
                references[slug]["prompt"],
                [background, card],
                PRIMARY_MODEL,
            )
        add("shot", "S8", shots["S8"]["prompt"], [card], PRIMARY_MODEL)
        return jobs

    for reference in scenes["references"]:
        add(
            "reference",
            reference["slug"],
            reference["prompt"],
            [background, card],
            PRIMARY_MODEL,
        )
    for shot in scenes["shots"]:
        add("shot", shot["scenario"], shot["prompt"], [card], PRIMARY_MODEL)
    return jobs


def _awkward_players(world: dict) -> List[str]:
    """Players whose kit is hardest to render or read.

    A yellow cap over off-white trousers, an outfit that is dark on every
    channel, and the S8 player who has taken two garments off. Chosen by
    looking at the palette rather than by hand, so a new seed picks its own.
    """
    players = world["identity"]["players"]
    dark = {"black", "navy", "burgundy", "brown", "purple"}
    pale = {"off-white", "yellow", "mustard", "lime", "tan"}

    scored = []
    for slug, entry in players.items():
        colours = list(entry["appearance"].values())
        darkness = sum(1 for c in colours if c in dark)
        paleness = sum(1 for c in colours if c in pale)
        # Either extreme is awkward: all-dark loses every edge in low light,
        # all-pale blows out under a street lamp.
        scored.append((-max(darkness, paleness), slug))
    scored.sort()

    s8_target = next(
        s["target"]["slug"] for s in world["scenes"]["shots"] if s["scenario"] == "S8"
    )
    ordered = [slug for _, slug in scored if slug != s8_target]
    return [s8_target] + ordered


def summarise(jobs: List[Job], store: store_mod.ImageStore) -> Dict:
    missing = [j for j in jobs if not store.has(j.image_id)]
    cost = sum(j.price for j in missing)
    return {
        "total": len(jobs),
        "already_present": len(jobs) - len(missing),
        "to_generate": len(missing),
        "estimated_usd": round(cost, 2),
        "missing": missing,
    }


async def run(
    jobs: List[Job], store: store_mod.ImageStore, dry_run: bool = True
) -> Dict:
    """Generate whatever is missing. ``dry_run`` spends nothing."""
    from backend.vision_client import OpenRouterImageClient

    report = summarise(jobs, store)
    if dry_run:
        report["ran"] = False
        return report

    if report["estimated_usd"] > HARD_CEILING_USD:
        raise RuntimeError(
            f"planned spend ${report['estimated_usd']:.2f} exceeds the "
            f"${HARD_CEILING_USD:.2f} ceiling; refusing to start"
        )

    generated, failed = [], []
    for job in report["missing"]:
        client = OpenRouterImageClient(model=job.model)
        urls = [_data_url(path) for path in job.inputs]
        try:
            data_url = await client.generate(job.prompt, urls, **job.params)
            store.save_data_url(job.image_id, data_url)
            generated.append(job)
        except Exception as e:  # noqa: BLE001 - reported, not swallowed
            failed.append((job, str(e)))

    report["ran"] = True
    report["generated"] = [(j.kind, j.name, j.image_id) for j in generated]
    report["failed"] = [(j.kind, j.name, err) for j, err in failed]
    report["spent_usd"] = round(sum(j.price for j in generated), 2)
    return report


def _data_url(path: Path) -> str:
    import base64
    import mimetypes

    mime = mimetypes.guess_type(str(path))[0] or "image/jpeg"
    encoded = base64.b64encode(Path(path).read_bytes()).decode()
    return f"data:{mime};base64,{encoded}"


def run_sync(jobs, store, dry_run=True) -> Dict:
    return asyncio.run(run(jobs, store, dry_run=dry_run))
