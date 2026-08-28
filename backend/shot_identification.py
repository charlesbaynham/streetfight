"""Which player was photographed: the integration layer between a stored vision
review and the pure soft decoder in :mod:`backend.identity.decoder`.

The split of concerns this module sits in the middle of:

* the **vision model** is asked only "what colour is each garment, and how sure
  are you?". It knows nothing about codes, channels or error correction, and it
  is never told who is playing -- see ``backend/shot_vision.py``;
* **this module** turns that reading, plus who is alive and where they were,
  into a ranked posterior over players. All of the error correction happens
  here, deterministically, in code;
* :mod:`backend.shot_auto_actions` decides whether the top of that ranking is
  good enough to act on without an admin.

Why this exists at all (roadmap #5). The path it replaces for identification,
``shot_vision.slot_candidates_from_review``, decodes a reading against the
*code* and then looks for a player holding the resulting slot. That only works
if the player is wearing their exact canonical codeword. Overrides exist
precisely because guests do not (``backend/identity/overrides.py``), and once
players choose their own outfits (roadmap #10) almost nobody will -- so that
path does not merely fail to identify them, it can complete a reading to the
*wrong* codeword and name somebody with confidence. Scoring the reading against
the candidates' **effective words** has no such failure mode, and it is also
strictly more informative: two readable channels discriminate sharply within a
handful of living players even though they vouch for nothing against the code.

The probability model follows the roadmap's #5 section, which is worth reading
before changing anything here. In short::

    P(T = x | image, location)  ∝  P(T = x) · P(image | T = x) · P(location | T = x)

``decode()`` computes the image term itself, so what this module hands it as a
"prior" is everything *except* the image evidence -- the structural prior times
the location likelihood ratio. That is exact, and needs no change to the pure
module.

**Proximity is evidence, not a prior.** Weighting the prior by closeness would
give a teammate standing at the shooter's shoulder the highest prior of anyone,
when they should have nearly the lowest -- people stand near their teammates
*because* they are teammates. It would also count clustering twice and produce
overconfident posteriors, which is the failure mode that matters when a
threshold gates an automatic action.
"""

import json
import logging
import math
import time
from typing import Dict
from typing import List
from typing import Optional
from uuid import UUID

from .identity.config import DEFAULT_THRESHOLDS
from .identity.config import default_scheme
from .identity.decoder import DecodeResult
from .identity.decoder import decode
from .identity.observations import Prior
from .identity.overrides import Word
from .identity.overrides import pairwise_distances
from .identity.scheme import IdentityScheme
from .model import ShotModel
from .model import UserModel
from .shot_vision import reading_from_review

logger = logging.getLogger(__name__)


# -- the location model's constants -----------------------------------------
#
# Every one of these is a guess awaiting data from R2. They are gathered here
# rather than inlined so that fitting them later is an edit to this block.

# sigma_fix: the accuracy of a position fix, in metres. The browser reports
# this as position.coords.accuracy and we throw it away today; R5 captures it,
# after which this is only the fallback for fixes recorded before that landed.
DEFAULT_FIX_ACCURACY_M = 15.0

# D: how fast uncertainty about a player's position grows once their fix is
# stale, in m^2/s. A random walk at strolling pace with a ~30 s correlation
# time gives D ~ 30; 20 is deliberately a little tighter. MapView.js already
# fades other players' dots to their floor over five minutes, which is the same
# instinct applied visually and a reasonable check on the timescale.
DIFFUSION_M2_PER_S = 20.0

# A: the area a player could be in if we knew nothing at all, in m^2. Only ever
# used as a ratio against the fix's own spread, so the exact value matters much
# less than its order of magnitude. 1 km^2 is a large night's play area.
GAME_AREA_M2 = 1_000_000.0

# P(T = x) for a teammate of the shooter. Not zero: hit_user performs no team
# check and friendly fire is possible, just unlikely.
TEAMMATE_PRIOR = 0.05

# The uniform floor mixed into the prior. The posterior is a product, so a zero
# anywhere is unrecoverable - a candidate at zero cannot be rescued by a
# photograph that reads their outfit perfectly.
PRIOR_FLOOR = 0.02

_EARTH_RADIUS_M = 6_371_000.0


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in metres."""
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    d_phi = phi2 - phi1
    d_lambda = math.radians(lon2 - lon1)
    a = (
        math.sin(d_phi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    )
    return 2 * _EARTH_RADIUS_M * math.asin(math.sqrt(a))


def parse_location_context(raw: Optional[str]) -> Dict[UUID, dict]:
    """``{user_id: fix}`` from a shot's stored ``location_context`` JSON.

    Entries without a usable position are dropped rather than defaulted: "we
    don't know where they were" must not become "they were at (0, 0)".
    """
    if not raw:
        return {}
    try:
        entries = json.loads(raw)
    except ValueError:
        logger.warning("Unparseable location_context; ignoring the location term")
        return {}
    if not isinstance(entries, list):
        return {}

    fixes: Dict[UUID, dict] = {}
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        if entry.get("latitude") is None or entry.get("longitude") is None:
            continue
        try:
            user_id = UUID(str(entry["user_id"]))
        except (KeyError, ValueError):
            continue
        fixes[user_id] = entry
    return fixes


def _effective_sigma_m(fix: dict, at_time: float) -> float:
    """How uncertain this player's *current* position is, given the fix's age.

    ``sigma_eff^2 = sigma_fix^2 + 2 D a``. Staleness widens the uncertainty; it
    never removes the candidate.
    """
    accuracy = fix.get("accuracy")
    try:
        sigma_fix = float(accuracy)
    except (TypeError, ValueError):
        sigma_fix = DEFAULT_FIX_ACCURACY_M
    if not math.isfinite(sigma_fix) or sigma_fix <= 0:
        sigma_fix = DEFAULT_FIX_ACCURACY_M

    try:
        age = max(0.0, at_time - float(fix.get("timestamp")))
    except (TypeError, ValueError):
        # No timestamp: treat the fix as maximally stale rather than fresh.
        age = GAME_AREA_M2 / (2 * DIFFUSION_M2_PER_S)

    return math.sqrt(sigma_fix**2 + 2 * DIFFUSION_M2_PER_S * age)


def location_likelihood_ratios(
    shooter_fix: Optional[dict],
    fixes: Dict[UUID, dict],
    candidate_ids: List[UUID],
    at_time: float,
) -> Dict[UUID, float]:
    """``Λ_x`` per candidate: how much more likely their observed fix is if they
    were at the shooter than if they were simply somewhere in the play area.

    ``Λ_x = max(1, (A / S) · exp(-d² / 2σ_eff²))`` where ``S = 2πσ_eff²`` is the
    area the fix's uncertainty spreads over. Two limits make this the right
    shape rather than a proximity score:

    * **a stale fix goes quiet.** As the age grows, ``S`` grows until it exceeds
      ``A``, the exponential flattens, and ``Λ_x → 1`` -- the location term drops
      out of the product and the image evidence decides alone. It is never
      allowed below 1, so no candidate is ever suppressed by *not knowing* where
      they were.
    * **crowds discriminate less.** The ratio rewards a *uniquely* close player.
      When everybody is close, everybody's ratio is similar and normalisation
      washes it out, which a raw proximity weight cannot express.
    """
    if shooter_fix is None:
        return {pid: 1.0 for pid in candidate_ids}

    ratios: Dict[UUID, float] = {}
    for pid in candidate_ids:
        fix = fixes.get(pid)
        if fix is None:
            ratios[pid] = 1.0
            continue
        sigma = _effective_sigma_m(fix, at_time)
        spread_area = 2 * math.pi * sigma**2
        distance = haversine_m(
            float(shooter_fix["latitude"]),
            float(shooter_fix["longitude"]),
            float(fix["latitude"]),
            float(fix["longitude"]),
        )
        ratio = (GAME_AREA_M2 / spread_area) * math.exp(-(distance**2) / (2 * sigma**2))
        ratios[pid] = max(1.0, ratio)
    return ratios


def structural_prior(candidates: List[UserModel], shooter_team_id) -> Dict[UUID, float]:
    """``P(T = x)`` before any evidence: flat, then adjusted for the game rules.

    The only thing known before looking at the photograph is that a teammate is
    an unlikely target -- not an impossible one.
    """
    return {
        user.id: (
            TEAMMATE_PRIOR
            if shooter_team_id is not None and user.team_id == shooter_team_id
            else 1.0
        )
        for user in candidates
    }


def eligible_candidates(
    users: List[UserModel], shooter_id: Optional[UUID]
) -> List[UserModel]:
    """Who could have been photographed: anybody in the game but the shooter.

    A player with no identity slot is excluded -- they have no effective word,
    so there is nothing to score them against.

    **Being knocked out does not remove a candidate.** A dead player is still
    standing there to be photographed, most obviously in the seconds after the
    shot that killed them: the next shot in the queue is often of exactly that
    person, and dropping them makes it match nobody, climb the escalation
    ladder for nothing and land back with the admin. Resolving it as a hit that
    does no damage is both cheaper and true. The prior stays flat for the dead
    -- a down-weight by how long ago they died is plausible, but it is a
    constant to fit from R2's data rather than to invent here.
    """
    return [
        user
        for user in users
        if user.id != shooter_id and user.identity_slot is not None
    ]


def build_prior(
    candidates: List[UserModel],
    shooter: Optional[UserModel],
    fixes: Dict[UUID, dict],
    at_time: float,
) -> Prior:
    """Everything except the image evidence, as the decoder's ``prior``.

    ``prior[x] ∝ P(T = x) · Λ_x``, mixed with a uniform floor. Named a prior
    because that is the decoder's parameter; it is really a pre-image posterior,
    and the call site says so rather than the tested module being renamed to
    suit its caller.
    """
    if not candidates:
        return Prior()

    ids = [user.id for user in candidates]
    structural = structural_prior(candidates, shooter.team_id if shooter else None)
    shooter_fix = fixes.get(shooter.id) if shooter else None
    ratios = location_likelihood_ratios(shooter_fix, fixes, ids, at_time)

    weights = {pid: structural[pid] * ratios[pid] for pid in ids}
    total = sum(weights.values())
    if total <= 0:
        return Prior({pid: 1.0 / len(ids) for pid in ids})

    uniform = 1.0 / len(ids)
    return Prior(
        {
            pid: (1 - PRIOR_FLOOR) * (w / total) + PRIOR_FLOOR * uniform
            for pid, w in weights.items()
        }
    )


def candidate_words(
    candidates: List[UserModel], scheme: IdentityScheme
) -> Dict[UUID, Word]:
    """``{user_id: effective word}`` -- what each candidate is actually wearing."""
    from .identity_admin import effective_words

    return effective_words(candidates, scheme)


def _rank(
    candidates: List[UserModel],
    review: dict,
    scheme: IdentityScheme,
    make_prior,
) -> Optional[DecodeResult]:
    """Score a reading against a candidate set: the shared tail of the ranking
    functions, which differ only in who is eligible and what the prior is.

    ``make_prior`` is handed the candidates that survived having an effective
    word, since a prior over anybody else would never be looked up.
    """
    words = candidate_words(candidates, scheme)
    if not words:
        return None
    candidates = [user for user in candidates if user.id in words]

    # The candidates' own separation, not the code's nominal d: an overridden
    # or freely-chosen outfit is not a codeword, so d no longer bounds how far
    # apart these particular players actually are.
    distances = pairwise_distances(words)
    effective_min_distance = distances[0][2] if distances else None

    return decode(
        reading=reading_from_review(review, scheme),
        candidates=words,
        channels=scheme.channels,
        prior=make_prior(candidates),
        thresholds=DEFAULT_THRESHOLDS,
        code_min_distance=effective_min_distance,
    )


def rank_candidates(
    shot: ShotModel,
    users: List[UserModel],
    review: dict,
    scheme: Optional[IdentityScheme] = None,
    at_time: Optional[float] = None,
) -> Optional[DecodeResult]:
    """Rank the game's players by how well they explain this shot's photograph.

    Returns ``None`` when there is nobody to rank. Every candidate keeps a
    non-zero posterior, so the caller decides what is good enough to act on --
    this function never refuses on its own account.
    """
    scheme = scheme or default_scheme()
    candidates = eligible_candidates(users, shot.user_id)
    if not candidates:
        return None

    at_time = at_time if at_time is not None else time.time()
    fixes = parse_location_context(shot.location_context)
    shooter = next((u for u in users if u.id == shot.user_id), None)

    return _rank(
        candidates,
        review,
        scheme,
        lambda survivors: build_prior(survivors, shooter, fixes, at_time),
    )


def rank_reference_candidates(
    users: List[UserModel],
    review: dict,
    scheme: Optional[IdentityScheme] = None,
) -> Optional[DecodeResult]:
    """Rank the whole game against a reference photo taken at the door.

    The same scoring as :func:`rank_candidates` with the shot-specific terms
    dropped, because at the door none of them apply: there is no shooter to
    exclude or to treat as a teammate, and a reference photo carries no
    ``location_context`` to build a location term from. What is left is every
    player who has picked an outfit, under a flat prior -- ``build_prior`` with
    no shooter and no fixes is exactly that, floor and all.
    """
    scheme = scheme or default_scheme()
    candidates = [user for user in users if user.identity_slot is not None]
    if not candidates:
        return None

    return _rank(
        candidates,
        review,
        scheme,
        lambda survivors: build_prior(survivors, None, {}, time.time()),
    )
