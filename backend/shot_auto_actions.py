"""Acting on confident AI shot reviews: the head-of-queue drain, and the ladder.

The vision review only annotates a shot; this module is what turns a confident
annotation into the game action the admin would have taken -- mark_shot_missed
for a confident miss, hit_user for a confident, unambiguously identified hit.
Everything else stays in the queue for the admin.

**The escalation ladder** (roadmap #11) decides which of those a hit on a
person gets, by how much of the outfit was legible (``confident_channel_count``
and ``armbands_confident``, both in backend.shot_vision):

* **every channel read**, or **all but one with the armbands among them** --
  the auto-eligible rung. The armbands are the one garment the game hands out,
  so reading them makes player-ness solid rather than inferred, and one erasure
  is well within the code. Acted on when the overall confidence and the
  posterior both clear their thresholds; otherwise it is the admin's.
* **anything less** -- three channels without the armbands, or two, or fewer.
  Identification still runs and still ranks the candidates, but nothing here
  acts on it: the shot goes to a stronger model with the reference photos
  (backend.shot_escalation), whose verdict re-enters this same gate. The weak
  model's own confidence is deliberately *not* a gate on that rung -- the weak
  model being unsure is exactly what escalation is for.

An escalated verdict of "unsure" -- and an escalation that errored, and one
never made because no escalation model is configured -- all land in the same
place: the admin queue, where every shot went before any of this existed.

**Strict queue order.** Only the oldest unchecked shot of a game is ever acted
on. Resolving a shot can invalidate the shots behind it (a knockout refunds the
victim's queued shots), so an ambiguous head blocks the whole queue -- and so
does a head waiting on an escalation. Every resolution -- automatic or admin --
re-reads the head and carries on. The drain is called after a review completes
(backend.ai_shot_review), after an escalation completes
(backend.shot_escalation) and after each admin resolution (backend.main); never
from inside hit_user/mark_shot_missed themselves, which would recurse.
"""

import json
import logging
from typing import Optional
from typing import Tuple
from uuid import UUID

from fastapi import HTTPException

from .identity.config import DEFAULT_THRESHOLDS
from .identity.config import default_scheme
from .model import AI_REVIEW_STATE_DONE
from .shot_identification import rank_candidates
from .shot_vision import HIT_PLAYER
from .shot_vision import MISS
from .shot_vision import armbands_confident
from .shot_vision import confident_channel_count

logger = logging.getLogger(__name__)

CONFIDENT = DEFAULT_THRESHOLDS.confident_threshold

# Built once: the scheme is fixed for the life of the process.
DEFAULT_SCHEME = default_scheme()

# The decisions _decide can reach; None means "leave it to the admin".
_MISS = "miss"
_BYSTANDER = "bystander"
_HIT = "hit"
_ESCALATE = "escalate"


def process_queue_head(game_id: UUID) -> None:
    """Auto-resolve the head of a game's shot queue while confident verdicts allow.

    A no-op unless the game's auto-actions toggle is on -- reviews (automatic
    or manual re-runs) always annotate, but only act when the game has opted
    in. Races with an admin resolving the same shot are expected: the
    resolvers 400 on an already-checked shot, and the re-read sees the truth.
    """
    from .admin_interface import AdminInterface

    if not AdminInterface().is_ai_auto_actions_enabled(game_id):
        return

    while True:
        head = AdminInterface().get_queue_head(game_id)
        if head is None:
            return

        decision = _decide(head, game_id)
        if decision is None:
            # An ambiguous head blocks everything behind it: that is the
            # required ordering, not a missed opportunity.
            return

        action, target_id = decision
        if action == _ESCALATE:
            from . import shot_escalation

            logger.info("Escalating shot %s to the stronger model", head.id)
            shot_escalation.enqueue_escalation(head.id)
            # Return either way. With an escalation in flight the head blocks
            # the queue behind it; with no escalation client configured nothing
            # started at all and the head simply waits for the admin -- the
            # pre-existing safety valve, unchanged.
            return

        try:
            if action == _HIT:
                logger.info(
                    "Auto-hit: shot %s confidently identifies user %s",
                    head.id,
                    target_id,
                )
                AdminInterface().hit_user(head.id, target_id)
            elif action == _BYSTANDER:
                logger.info(
                    "Auto-bystander: shot %s confidently hit nobody playing", head.id
                )
                AdminInterface().mark_shot_bystander(head.id)
            else:
                logger.info("Auto-miss: shot %s confidently missed", head.id)
                AdminInterface().mark_shot_missed(head.id)
        except HTTPException as e:
            logger.info(
                "Auto-action on shot %s raced an admin (%s); re-reading the queue",
                head.id,
                e.detail,
            )


def _decide(head, game_id: UUID) -> Optional[Tuple[str, Optional[UUID]]]:
    """What to do with the queue head: (action, target_id), or None to stop.

    The ladder, in order (see the module docstring for why each rung is where
    it is):

    1. no completed review, or an unparseable one -> the admin's;
    2. a miss, confidently -> resolve it. Legacy reviews stored without a
       confidence field parse as 0.0 and can never fire;
    3. any outcome other than a hit on a player -- including a ``hit_bystander``
       stored before roadmap #11 retired that mapping -- > the admin's. Nothing
       auto-bystanders off the weak model any more;
    4. a hit with the whole outfit read (or all but one, armbands included) ->
       the auto-eligible rung, gated on confidence and the posterior;
    5. any other hit -> the escalation rung, which is about what the *stronger*
       model has said so far, not what this one thinks.
    """
    if head.ai_review_state != AI_REVIEW_STATE_DONE or not head.ai_review:
        return None
    try:
        review = json.loads(head.ai_review)
    except ValueError:
        return None
    if not isinstance(review, dict):
        return None

    try:
        confidence = float(review.get("confidence"))
    except (TypeError, ValueError):
        confidence = 0.0

    outcome = review.get("outcome")
    if outcome == MISS:
        return (_MISS, None) if confidence >= CONFIDENT else None
    if outcome != HIT_PLAYER:
        return None

    readable = confident_channel_count(review)
    if readable == DEFAULT_SCHEME.channels.n or (
        readable == DEFAULT_SCHEME.channels.n - 1 and armbands_confident(review)
    ):
        return _decide_auto_hit(head, game_id, review, confidence)

    return _decide_escalated(head, game_id)


def _decide_auto_hit(
    head, game_id: UUID, review: dict, confidence: float
) -> Optional[Tuple[str, Optional[UUID]]]:
    """The auto-eligible rung: enough of the outfit was read that this reading
    can name somebody on its own.

    It still has to: the reply has to be confident overall, and the reading has
    to pick out one non-shooter candidate confidently and without a tie -- see
    backend.shot_identification.rank_candidates, which scores the reading
    against what each candidate is *actually wearing* rather than decoding it
    against the code.

    A candidate who is already knocked out is acted on like any other: the shot
    genuinely hit them, it simply takes nothing off them. Withholding it would
    leave the shot behind a kill blocking the queue for an admin to rubber-stamp.
    """
    from .admin_interface import AdminInterface

    if confidence < CONFIDENT:
        return None

    users = AdminInterface().get_users_for_game(game_id)
    ranked = rank_candidates(head, users, review)
    if ranked is None:
        return None

    # The same conservatism the slot-decode gate had, expressed against the
    # posterior instead of the code: act only on a confident, untied ranking
    # that nothing in the reading contradicts.
    if not ranked.confident or ranked.ambiguous or ranked.inconsistent:
        return None

    target = next((u for u in users if u.id == ranked.best), None)
    if target is None or target.id == head.user_id:
        return None

    return (_HIT, target.id)


def _decide_escalated(head, game_id: UUID) -> Optional[Tuple[str, Optional[UUID]]]:
    """The escalation rung: too little was read for this reading to name
    anybody, so what happens next depends on the stronger model.

    Never escalated -> escalate now. Pending -> wait, blocking the queue behind
    it exactly as an ambiguous head does. Errored -> the admin's (a re-run of
    the weak review clears it, see AdminInterface.store_shot_ai_review). Done ->
    whatever backend.shot_escalation makes of the verdict, re-validated here
    against the roster because the escalation may have finished minutes ago.
    That re-validation asks only whether the named player is still somebody
    this shot could have hit, not whether they are still alive: somebody
    knocked out in the meantime was still hit, for no damage.
    """
    from . import shot_escalation
    from .admin_interface import AdminInterface

    state = head.ai_escalation_state
    if state is None:
        return (_ESCALATE, None)
    if state != AI_REVIEW_STATE_DONE or not head.ai_escalation:
        return None

    try:
        payload = json.loads(head.ai_escalation)
    except ValueError:
        return None

    decision = shot_escalation.decide_from_escalation(payload)
    if decision is None:
        return None

    action, target_id = decision
    if action == shot_escalation.ACTION_MISS:
        return (_MISS, None)
    if action == shot_escalation.ACTION_BYSTANDER:
        return (_BYSTANDER, None)

    users = AdminInterface().get_users_for_game(game_id)
    target = next((u for u in users if u.id == target_id), None)
    if target is None or target.id == head.user_id:
        return None

    return (_HIT, target.id)
