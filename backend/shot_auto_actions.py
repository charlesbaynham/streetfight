"""Acting on confident AI shot reviews: the head-of-queue drain.

The vision review only annotates a shot; this module is what turns a confident
annotation into the game action the admin would have taken -- mark_shot_missed
for a confident miss or bystander, hit_user for a confident, unambiguously
identified hit. Everything else stays in the queue for the admin.

**Strict queue order.** Only the oldest unchecked shot of a game is ever acted
on. Resolving a shot can invalidate the shots behind it (a knockout refunds the
victim's queued shots), so an ambiguous head blocks the whole queue, and every
resolution -- automatic or admin -- re-reads the head and carries on. The drain
is called after a review completes (backend.ai_shot_review) and after each
admin resolution (backend.main); never from inside hit_user/mark_shot_missed
themselves, which would recurse.
"""

import json
import logging
from typing import Optional
from typing import Tuple
from uuid import UUID

from fastapi import HTTPException

from .identity.config import DEFAULT_THRESHOLDS
from .model import AI_REVIEW_STATE_DONE
from .shot_vision import HIT_BYSTANDER
from .shot_vision import HIT_PLAYER
from .shot_vision import MISS
from .shot_vision import slot_candidates_from_review

logger = logging.getLogger(__name__)

CONFIDENT = DEFAULT_THRESHOLDS.confident_threshold

# The decisions _decide can reach; None means "leave it to the admin".
_MISS = "miss"
_HIT = "hit"


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
        try:
            if action == _HIT:
                logger.info(
                    "Auto-hit: shot %s confidently identifies user %s",
                    head.id,
                    target_id,
                )
                AdminInterface().hit_user(head.id, target_id)
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

    Only a completed review with top-level confidence >= CONFIDENT can act. A
    hit additionally needs the stored channel reads to identify exactly one
    assignable slot (see slot_candidates_from_review), held by exactly one user
    in this game, who is alive and is not the shooter. Legacy reviews stored
    without a confidence field parse as 0.0 and can never fire.
    """
    from .admin_interface import AdminInterface

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
    if confidence < CONFIDENT:
        return None

    outcome = review.get("outcome")
    if outcome in (MISS, HIT_BYSTANDER):
        return (_MISS, None)
    if outcome != HIT_PLAYER:
        return None

    candidates = slot_candidates_from_review(review)
    if len(candidates) != 1:
        return None
    slot = candidates[0]

    holders = [
        user
        for user in AdminInterface().get_users_for_game(game_id)
        if user.identity_slot == slot
    ]
    if len(holders) != 1:
        return None
    target = holders[0]
    if target.hit_points <= 0 or target.id == head.user_id:
        return None

    return (_HIT, target.id)
