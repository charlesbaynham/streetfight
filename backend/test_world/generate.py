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

# Dollars per generated image, for the gate arithmetic *before* anything is
# sent; what a run actually cost is read back from OpenRouter. Measured at
# Gate C rather than taken off the rate card: a capped primary image billed
# $0.051, four times what the per-token arithmetic suggested, because the
# model bills its own reasoning tokens too. The other two are scaled from
# that by their published image-output rates.
PRICE = {PRIMARY_MODEL: 0.06, FALLBACK_MODEL: 0.08, CHEAP_MODEL: 0.02}

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


class Plan(NamedTuple):
    """What can be sent now, and what is still waiting on something else."""

    jobs: List[Job]
    blocked: List[str]  # shots whose target has no reference photo yet


def _fixture_dir(world_path: Path) -> Path:
    return Path(world_path).parent


def plan(
    world: dict,
    world_path: Path,
    gate: Optional[str] = None,
    seed: int = 1,
    store: Optional[store_mod.ImageStore] = None,
) -> Plan:
    """Every image the world calls for, whether or not it already exists.

    A shot is conditioned on its target's reference photo, so it cannot be
    planned until that photo exists -- its bytes are part of the shot's
    identity, which is what makes a regenerated reference cascade into the
    shots taken of that person. Such a shot comes back as ``blocked`` rather
    than as an unconditioned job, and planning again after the references
    have been generated picks it up.
    """
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
    blocked: List[str] = []

    def add_shot(shot):
        """Plan a shot, if the reference photo it is conditioned on is here."""
        slug = shot["target"]["slug"]
        reference_id = store_mod.image_id(
            "reference",
            references[slug]["prompt"],
            [background, card],
            PRIMARY_MODEL,
            {"seed": seed},
        )
        if store is None or not store.has(reference_id):
            blocked.append(f"{shot['scenario']} (needs {slug})")
            return
        add(
            "shot",
            shot["scenario"],
            shot["prompt"],
            [card, store.path_for(reference_id)],
            PRIMARY_MODEL,
        )

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
        add_shot(shots["S1"])
        return Plan(jobs, blocked)

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
        add_shot(shots["S8"])
        return Plan(jobs, blocked)

    for reference in scenes["references"]:
        add(
            "reference",
            reference["slug"],
            reference["prompt"],
            [background, card],
            PRIMARY_MODEL,
        )
    for shot in scenes["shots"]:
        add_shot(shot)
    return Plan(jobs, blocked)


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
    actual = 0.0
    for job in report["missing"]:
        client = OpenRouterImageClient(model=job.model)
        urls = [_data_url(path) for path in job.inputs]
        try:
            data_url = await client.generate(job.prompt, urls, **job.params)
            store.save_data_url(job.image_id, data_url)
            generated.append(job)
            actual += client.last_cost_usd or job.price
        except Exception as e:  # noqa: BLE001 - reported, not swallowed
            failed.append((job, str(e)))

    report["ran"] = True
    report["generated"] = [(j.kind, j.name, j.image_id) for j in generated]
    report["failed"] = [(j.kind, j.name, err) for j, err in failed]
    # What it really cost, as OpenRouter billed it -- not the estimate.
    report["spent_usd"] = round(actual, 3)
    return report


def _data_url(path: Path) -> str:
    import base64
    import mimetypes

    mime = mimetypes.guess_type(str(path))[0] or "image/jpeg"
    encoded = base64.b64encode(Path(path).read_bytes()).decode()
    return f"data:{mime};base64,{encoded}"


def run_sync(jobs, store, dry_run=True) -> Dict:
    return asyncio.run(run(jobs, store, dry_run=dry_run))
