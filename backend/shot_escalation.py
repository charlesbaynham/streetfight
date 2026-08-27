"""The hard shots, put to a stronger model with the reference photos.

Roadmap #11's middle rung. The cheap pass (:mod:`backend.shot_vision`) asks
what colour each garment is; when too little of the outfit was legible for
:mod:`backend.shot_auto_actions` to act on the answer, the shot comes here
rather than straight to the admin. This module asks a *different* question of a
*different* model: which of these people is this -- or did the shot miss, or
hit a non-player, or can you genuinely not tell which player it is.

What the stronger model is given: the photograph and its zoom, the ranked
candidate list with each candidate's prior and outfit, and the reference photos
of the top few candidates, the rest available on request. Asking for one is
another turn in the same multi-turn shape the screening/zoom loop already uses
rather than provider tool-calling, because ``OPENROUTER_ESCALATION_MODEL`` is
meant to be swapped freely.

What it is deliberately **not** given: the cheap pass's conclusions. It draws
its own from the pixels, and inherits nothing but the ranking -- otherwise the
second opinion is only the first one restated, and the failure the ladder
exists to catch is exactly a confident-sounding weak reading.

**The model observes; Python decides**, as in the cheap pass: the reply carries
a verdict and a confidence, and the thresholds below -- not the model -- decide
whether it is acted on. "unsure" is a first-class answer and the only correct
one for "a player, but I cannot tell which"; miss and bystander must never be
used as a dodge for it.

Two constraints shape the plumbing, the same two as
:mod:`backend.ai_shot_review`:

* **Never hold a database session across an ``await``.** Everything the call
  needs is read in one short synchronous pass before the first turn is sent.
* **Never let a failure escape.** An escalation that falls over is stored as an
  ``error`` state and nothing else, which leaves the shot with the admin --
  where every shot went before any of this existed.
"""

import asyncio
import json
import logging
from typing import Dict
from typing import List
from typing import Optional
from typing import Tuple
from uuid import UUID

from . import shot_auto_actions
from . import shot_vision
from .asyncio_triggers import trigger_update_event
from .identity.config import default_scheme
from .image_processing import draw_aim_marker
from .image_processing import prepare_for_vision
from .image_processing import zoom_image
from .model import AI_REVIEW_STATE_DONE
from .model import AI_REVIEW_STATE_ERROR
from .model import AI_REVIEW_STATE_PENDING
from .shot_identification import rank_candidates
from .shot_vision import _assistant_turn
from .shot_vision import _clamped_confidence
from .shot_vision import _previous_answer_turn
from .shot_vision import _transcript_turn
from .vision_client import get_escalation_client

logger = logging.getLogger(__name__)

STATE_PENDING = AI_REVIEW_STATE_PENDING
STATE_DONE = AI_REVIEW_STATE_DONE
STATE_ERROR = AI_REVIEW_STATE_ERROR

# How far down the ranking to go. Every candidate is potentially a reference
# photo in the request and the bill scales with the list, so the tail -- which
# the prior already says is unlikely -- is not worth paying for.
ESCALATION_MAX_CANDIDATES = 5

# How many reference photos ride along up front rather than on request. Enough
# that the usual case (the right player is near the top) needs one round trip,
# few enough that a wrong-but-cheap escalation stays cheap.
UPFRONT_REFERENCE_PHOTOS = 3

# Naming a player is the expensive mistake: a wrong "player X" takes a life off
# somebody who was never shot, while a wrong "unsure" costs an admin thirty
# seconds. So it needs more than the generic confident threshold. A guess
# awaiting R2's data, like every threshold in this pipeline.
ESCALATION_HIT_THRESHOLD = 0.75

# Miss and bystander cost the shooter one bullet and nothing else -- the same
# stakes as the weak model's own auto-actions, so the same threshold. Also a
# guess awaiting R2.
ESCALATION_OUTCOME_THRESHOLD = 0.6

# The four answers, and the only four. "unsure" is the human rung of the
# ladder: a player was hit but which one is undecidable, so an admin decides.
VERDICT_PLAYER = "player"
VERDICT_MISS = "miss"
VERDICT_BYSTANDER = "bystander"
VERDICT_UNSURE = "unsure"
VERDICTS = (VERDICT_PLAYER, VERDICT_MISS, VERDICT_BYSTANDER, VERDICT_UNSURE)

# What :func:`decide_from_escalation` hands back, matching the vocabulary
# backend.shot_auto_actions acts in.
ACTION_HIT = "hit"
ACTION_MISS = "miss"
ACTION_BYSTANDER = "bystander"

# asyncio only holds a weak reference to a running task, so keep our own or an
# escalation can be collected mid-flight.
_tasks = set()


class EscalationError(ValueError):
    """The stronger model's reply did not match the contract."""


def enqueue_escalation(shot_id: UUID, client=None) -> Optional[asyncio.Task]:
    """Schedule an escalation of one shot. None if the feature is not set up.

    Returning None is the safety valve: with no escalation model configured
    (or no event loop) the shot simply waits for the admin, exactly as it did
    before this rung existed.
    """
    client = client or get_escalation_client()
    if client is None:
        logger.info(
            "Not escalating shot %s: no escalation client configured "
            "(set OPENROUTER_API_KEY and OPENROUTER_ESCALATION_MODEL)",
            shot_id,
        )
        return None

    try:
        task = asyncio.create_task(escalate_shot(shot_id, client))
    except RuntimeError:
        # No running loop -- e.g. a synchronous test harness. Nothing to do.
        logger.warning("Not escalating shot %s: no running event loop", shot_id)
        return None

    _tasks.add(task)
    task.add_done_callback(_tasks.discard)
    return task


# ---------------------------------------------------------------------------
# The prompt and its response contract
# ---------------------------------------------------------------------------


def build_escalation_schema() -> dict:
    """The JSON schema the stronger model is asked to fill in.

    Requested, never assumed: the same model-agnostic contract as
    :func:`backend.shot_vision.build_schema`, so a model without native
    structured output can answer it as plain JSON. ``candidate`` and
    ``request_reference_photos`` are optional because three of the four
    verdicts name nobody and most replies ask for nothing.
    """
    return {
        "type": "object",
        "properties": {
            "verdict": {"enum": list(VERDICTS)},
            "candidate": {"type": ["integer", "null"]},
            "confidence": {"type": "number", "minimum": 0, "maximum": 1},
            "reasoning": {"type": "string"},
            "request_reference_photos": {
                "type": "array",
                "items": {"type": "integer"},
            },
        },
        "required": ["verdict", "confidence", "reasoning"],
        "additionalProperties": False,
    }


def _candidate_line(candidate: dict) -> str:
    """One numbered candidate: who they are, how likely, what they are wearing,
    and whether their reference photo is here, askable for, or missing."""
    outfit = ", ".join(
        f"{channel} {colour or shot_vision.UNKNOWN}"
        for channel, colour in (candidate.get("outfit") or {}).items()
    )
    if candidate["reference_photo_shown"]:
        photo = "Reference photo attached below."
    elif candidate["reference_photo_available"]:
        photo = "Reference photo available on request."
    else:
        photo = "No reference photo available."
    return (
        f"  {candidate['number']}. {candidate['name']} -- "
        f"{candidate['probability'] * 100:.1f}% likely. "
        f"Wearing: {outfit or shot_vision.UNKNOWN}. {photo}"
    )


def build_escalation_prompt(candidates: List[dict], has_more_photos: bool) -> str:
    """The instructions sent alongside the photograph.

    A different question from the cheap pass, and it must stay one: nothing of
    the first review's reading, outcome or reasoning appears here. The ranking
    -- the percentages -- is the only thing inherited.
    """
    if candidates:
        candidate_section = (
            "These are the players who could have been shot, most likely "
            "first. The percentage is what was known before anyone looked at "
            "this photograph -- who was near the shooter, and who is on the "
            "shooter's own team -- so treat it as a starting point that the "
            "photograph can and should overrule. A garment given as "
            f'"{shot_vision.UNKNOWN}" is one nobody recorded.\n\n'
            + "\n".join(_candidate_line(candidate) for candidate in candidates)
        )
    else:
        candidate_section = (
            'Nobody in this game is placed and still alive, so "player" is not '
            "a valid verdict here: there is no list to pick from. Decide "
            'between "miss", "bystander" and "unsure" on what the photograph '
            "shows."
        )

    if has_more_photos:
        # Name the numbers that can actually be asked for, rather than an
        # invented example: a model told to ask for candidate 5 out of a list
        # of two has been handed a way to waste the one round it gets.
        askable = [
            candidate["number"]
            for candidate in candidates
            if candidate["reference_photo_available"]
            and not candidate["reference_photo_shown"]
        ]
        request_section = (
            "The reference photos of these candidates are not attached: "
            f"{askable or 'none'}. If seeing one would change your answer, "
            'reply with "request_reference_photos" naming their numbers -- for '
            f'example {{"request_reference_photos": {askable[:2] or [2]}}}. The '
            "photos will be supplied in a follow-up turn and this question "
            "asked again. You get one round of this, so ask for everything you "
            "want at once."
        )
    else:
        request_section = (
            "Every reference photo there is has already been attached; there "
            "are no further photos to ask for."
        )

    return f"""You are looking at a photograph taken during a street game. A player \
has photographed somebody in order to "shoot" them, and it now has to be \
decided what happened.

The photo has a thin red cross drawn across it -- one horizontal line and one \
vertical line, each spanning the whole image. The lines themselves are guides \
only, there to help you find the aim point -- IGNORE anything they merely pass \
over or touch elsewhere in the frame. The single pixel at the centre of the \
cross, where the two lines meet, is the exact spot the shot landed. Only what \
is at that one pixel matters: the shot hit a person only if that centre point \
is on them -- on their clothing, hands or shoes -- and missed if it is on the \
background beside them.

You are shown two views: first the whole frame, then a zoomed-in view \
containing only the middle 12.5% of it at higher resolution, with the same red \
cross redrawn at the same aim point. Use whichever view is clearer, and trust \
the zoomed one when they disagree.

{candidate_section}

{request_section}

Your answer is exactly one of four verdicts:

  "{VERDICT_PLAYER}" -- the shot hit one of the players listed above, and you \
can say which. Put their number in "candidate".
  "{VERDICT_MISS}" -- the shot landed on nobody at all.
  "{VERDICT_BYSTANDER}" -- the shot landed on somebody who is not in the game: \
a passer-by, not one of the players listed above.
  "{VERDICT_UNSURE}" -- the shot hit somebody, but you cannot tell which \
player it is.

The fence between those matters more than producing an answer. Say \
"{VERDICT_MISS}" only when the shot genuinely landed on nobody, and \
"{VERDICT_BYSTANDER}" only when it genuinely hit somebody who is not playing. \
If it hit a player and you cannot tell which, the answer is \
"{VERDICT_UNSURE}" -- never miss or bystander as a way out of a hard call.

The costs are not symmetric. Naming the wrong player takes a life off somebody \
who was never shot; answering "{VERDICT_UNSURE}" costs a human admin about \
thirty seconds looking at this same photograph. When you are torn, answer \
"{VERDICT_UNSURE}".

Give a "confidence" between 0 and 1: how sure you are of the verdict you give. \
Nothing is decided by that number here -- the thresholds are applied \
afterwards, in code -- so an honest 0.5 is worth far more than a hopeful 0.9.

Reply with JSON only, matching this shape:
{{
  "verdict": "{VERDICT_PLAYER}",
  "candidate": 1,
  "confidence": 0.8,
  "reasoning": "one or two sentences on what you can and cannot see"
}}"""


# The second turn: the zoomed view promised by the prompt.
ZOOM_TURN = (
    "Here is the zoomed view: the middle 12.5% of the photograph above, at "
    "higher resolution, with the same red cross redrawn at the same aim point "
    "-- only its centre pixel counts, exactly as in the full frame."
)

# The turn after the requested photos have been supplied. There is only ever
# one round of requests, so this closes the door explicitly rather than leaving
# the model waiting for photos that are not coming.
NO_FURTHER_PHOTOS = (
    "There are no further photos. Answer in full now with the JSON described " "above."
)


def _reference_photo_turn(candidate: dict, image_data_url: str) -> dict:
    return {
        "role": "user",
        "text": (
            f"Reference photo of candidate {candidate['number']} "
            f"({candidate['name']}):"
        ),
        "image_data_url": image_data_url,
    }


def _unavailable_photos_turn(numbers: List[int]) -> dict:
    """The reply asked for photos that do not exist, or asked for nothing and
    answered nothing. Either way, say so once and ask for the verdict."""
    if numbers:
        listed = ", ".join(str(number) for number in numbers)
        text = (
            f"No reference photo is available for candidate(s) {listed}. "
            f"{NO_FURTHER_PHOTOS}"
        )
    else:
        text = NO_FURTHER_PHOTOS
    return {"role": "user", "text": text}


# ---------------------------------------------------------------------------
# Parsing and validation
# ---------------------------------------------------------------------------


def _candidate_number(value, candidate_numbers: List[int]) -> Optional[int]:
    """``value`` as one of the numbers actually on the list, or None.

    Booleans are rejected before ``int()`` gets them: ``True`` is 1 in Python
    and would silently name the top-ranked candidate.
    """
    if isinstance(value, bool):
        return None
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None
    return number if number in candidate_numbers else None


def requested_numbers(raw, candidate_numbers: List[int]) -> List[int]:
    """The listed candidates whose reference photos a reply asked for.

    Anything that is not a number on the list is dropped rather than erroring:
    a model inventing a candidate number is not a broken reply, just one whose
    request cannot be honoured.
    """
    if not isinstance(raw, dict):
        return []
    asked = raw.get("request_reference_photos")
    if not isinstance(asked, list):
        return []
    numbers = []
    for value in asked:
        number = _candidate_number(value, candidate_numbers)
        if number is not None and number not in numbers:
            numbers.append(number)
    return numbers


def is_complete_verdict(raw) -> bool:
    """Whether a reply decided something, rather than only asking for photos."""
    return isinstance(raw, dict) and raw.get("verdict") in VERDICTS


def parse_escalation_reply(raw, candidate_numbers: List[int]) -> dict:
    """Validate a raw reply into ``{verdict, candidate, confidence, reasoning}``.

    A "player" verdict naming somebody who is not on the list degrades to
    "unsure" rather than raising: a model that answers the right question badly
    has told us it could not decide, which is a verdict we have a rung for. An
    unrecognisable verdict is a different matter -- that is a reply to some
    other question, and storing it as a decision would be worse than erroring.
    """
    if not isinstance(raw, dict):
        raise EscalationError(f"expected a JSON object, got {type(raw).__name__}")

    verdict = raw.get("verdict")
    if verdict not in VERDICTS:
        raise EscalationError(
            f"'verdict' must be one of {list(VERDICTS)}; got {verdict!r}"
        )

    reasoning = raw.get("reasoning")
    if not isinstance(reasoning, str):
        reasoning = ""
    # Missing or unparseable becomes 0.0, so nothing unconfident can fire.
    confidence = _clamped_confidence(raw.get("confidence"))

    candidate = None
    if verdict == VERDICT_PLAYER:
        candidate = _candidate_number(raw.get("candidate"), candidate_numbers)
        if candidate is None:
            logger.info(
                "Escalated reply named candidate %r, which is not on the list; "
                "treating it as unsure",
                raw.get("candidate"),
            )
            return {
                "verdict": VERDICT_UNSURE,
                "candidate": None,
                "confidence": confidence,
                "reasoning": (
                    f"{reasoning} [named candidate {raw.get('candidate')!r}, who "
                    "is not on the candidate list, so treated as unsure]"
                ).strip(),
            }

    return {
        "verdict": verdict,
        "candidate": candidate,
        "confidence": confidence,
        "reasoning": reasoning,
    }


def decide_from_escalation(payload: dict) -> Optional[Tuple[str, Optional[UUID]]]:
    """What a stored escalation payload means for the queue, or None for "leave
    it to the admin".

    Pure: this is where "Python owns the thresholds" lives. Naming a player
    needs :data:`ESCALATION_HIT_THRESHOLD` because the mistake takes somebody's
    life; miss and bystander only cost a bullet, so they clear the same bar the
    weak model's own auto-actions do. "unsure" -- and anything malformed -- is
    the admin's.
    """
    if not isinstance(payload, dict):
        return None

    verdict = payload.get("verdict")
    confidence = _clamped_confidence(payload.get("confidence"))

    if verdict == VERDICT_PLAYER:
        if confidence < ESCALATION_HIT_THRESHOLD:
            return None
        try:
            return (ACTION_HIT, UUID(str(payload.get("target_user_id"))))
        except (TypeError, ValueError):
            return None

    if confidence < ESCALATION_OUTCOME_THRESHOLD:
        return None
    if verdict == VERDICT_MISS:
        return (ACTION_MISS, None)
    if verdict == VERDICT_BYSTANDER:
        return (ACTION_BYSTANDER, None)
    return None


# ---------------------------------------------------------------------------
# The call itself
# ---------------------------------------------------------------------------


def _stored_review(shot) -> dict:
    """The cheap pass's stored reading -- the input the ranking is built from.

    Only ever used to *rank* the candidates; none of it reaches the prompt.
    """
    try:
        review = json.loads(shot.ai_review or "")
    except ValueError:
        review = None
    if not isinstance(review, dict):
        raise EscalationError("no stored review to escalate from")
    return review


def _load_context(shot_id: UUID):
    """Everything the call needs, read in one synchronous pass.

    Returns ``(shot, candidates, photos)``. The candidate dicts carry no image
    data -- they are stored in the payload verbatim -- so the reference photos
    come back beside them, keyed by candidate number and still unprepared:
    resizing them is CPU work with no session open, and a photo nobody asks for
    is never resized at all.
    """
    from .admin_interface import AdminInterface
    from .identity_admin import _word_to_appearance
    from .identity_admin import effective_words

    shot = AdminInterface().get_shot_model(shot_id)
    review = _stored_review(shot)
    users = AdminInterface().get_users_for_game(shot.game_id)
    ranked = rank_candidates(shot, users, review)

    scheme = default_scheme()
    names = {user.id: user.name for user in users}
    words = effective_words(users, scheme)

    candidates: List[dict] = []
    photos: Dict[int, str] = {}
    shown = 0
    entries = ranked.ranked[:ESCALATION_MAX_CANDIDATES] if ranked else []
    for number, (user_id, probability) in enumerate(entries, start=1):
        photo = AdminInterface().get_reference_photo(user_id)
        if photo:
            photos[number] = photo
        show = bool(photo) and shown < UPFRONT_REFERENCE_PHOTOS
        shown += 1 if show else 0
        word = words.get(user_id)
        candidates.append(
            {
                "number": number,
                "user_id": str(user_id),
                "name": names.get(user_id),
                "probability": probability,
                # What they are actually wearing, overrides and all -- not the
                # codeword their slot nominally assigns them.
                "outfit": (
                    _word_to_appearance(word, scheme) if word is not None else {}
                ),
                "reference_photo_shown": show,
                "reference_photo_available": bool(photo),
            }
        )

    return shot, candidates, photos


async def _run_escalation(shot_id: UUID, client) -> dict:
    """One escalated call (or two, if photos are asked for), as a payload."""
    shot, candidates, photos = _load_context(shot_id)
    numbers = [candidate["number"] for candidate in candidates]
    by_number = {candidate["number"]: candidate for candidate in candidates}
    has_more_photos = any(
        candidate["reference_photo_available"]
        and not candidate["reference_photo_shown"]
        for candidate in candidates
    )

    turns = [
        {
            "role": "user",
            "text": build_escalation_prompt(candidates, has_more_photos),
            "image_data_url": prepare_for_vision(draw_aim_marker(shot.image_base64)),
        },
        {
            "role": "user",
            "text": ZOOM_TURN,
            "image_data_url": zoom_image(
                shot.image_base64, factor=shot_vision.ZOOM_FACTOR
            ),
        },
    ]
    turns += [
        _reference_photo_turn(
            candidate, prepare_for_vision(photos[candidate["number"]])
        )
        for candidate in candidates
        if candidate["reference_photo_shown"]
    ]

    schema = build_escalation_schema()
    transcript = [_transcript_turn(turn) for turn in turns]
    raw = await client.complete(turns, schema)
    transcript.append(_assistant_turn(raw, client))

    requested = requested_numbers(raw, numbers)
    supplied = [
        number
        for number in requested
        if number in photos and not by_number[number]["reference_photo_shown"]
    ]
    follow_up: List[dict] = []
    if supplied:
        follow_up = [
            _reference_photo_turn(by_number[number], prepare_for_vision(photos[number]))
            for number in supplied
        ]
        follow_up.append({"role": "user", "text": NO_FURTHER_PHOTOS})
    elif not is_complete_verdict(raw):
        # It asked for nothing we can supply and decided nothing, so pressing
        # once for the verdict is the difference between an answer and an
        # errored escalation.
        follow_up = [
            _unavailable_photos_turn(
                [number for number in requested if number not in photos]
            )
        ]

    if follow_up:
        turns = (
            turns
            + [_previous_answer_turn(raw, client.last_reasoning_details)]
            + follow_up
        )
        transcript += [_transcript_turn(turn) for turn in follow_up]
        # Whatever comes back now is the answer: a second request is ignored.
        raw = await client.complete(turns, schema)
        transcript.append(_assistant_turn(raw, client))

    reply = parse_escalation_reply(raw, numbers)
    target = by_number.get(reply["candidate"]) if reply["candidate"] else None
    return {
        "verdict": reply["verdict"],
        "candidate": reply["candidate"],
        "target_user_id": target["user_id"] if target else None,
        "target_name": target["name"] if target else None,
        "confidence": reply["confidence"],
        "reasoning": reply["reasoning"],
        "candidates": candidates,
        "requested_reference_photos": requested,
        "transcript": transcript,
    }


async def escalate_shot(shot_id: UUID, client=None) -> None:
    """Escalate one shot and store the verdict. Never raises."""
    from .admin_interface import AdminInterface

    client = client or get_escalation_client()
    if client is None:
        return

    try:
        game_id, shooter_id = AdminInterface().store_shot_escalation(
            shot_id, STATE_PENDING
        )
        # Unlike a pending weak review, an escalation is slow enough that the
        # admin should see the queue head is waiting on one rather than
        # wondering why nothing is happening.
        trigger_update_event("shots", game_id)
    except Exception:
        logger.exception("Could not start the escalation of shot %s", shot_id)
        return

    state = STATE_DONE
    payload = None
    try:
        payload = await _run_escalation(shot_id, client)
        logger.info(
            "Shot %s escalated: %s (%s, confidence %s)",
            shot_id,
            payload["verdict"],
            payload["target_name"],
            payload["confidence"],
        )
    except asyncio.CancelledError:
        raise
    except Exception as e:
        logger.exception("Escalation of shot %s failed", shot_id)
        state = STATE_ERROR
        payload = str(e) or e.__class__.__name__

    try:
        AdminInterface().store_shot_escalation(shot_id, state, payload)
        # The shooter's shot history shows the escalated bottom line, so nudge
        # them as well as the admin queue.
        trigger_update_event("user", shooter_id)
        trigger_update_event("shots", game_id)
    except Exception:
        logger.exception("Could not store the escalation of shot %s", shot_id)
        return

    # The verdict may have made the queue head resolvable. Guarded so this
    # function keeps its "never raises" contract.
    try:
        shot_auto_actions.process_queue_head(game_id)
    except Exception:
        logger.exception("Auto-action drain after escalating shot %s failed", shot_id)
