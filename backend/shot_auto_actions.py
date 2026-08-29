"""Acting on confident AI shot reviews: the head-of-queue drain, and the ladder.

The vision review only annotates a shot; this module is what turns a confident
annotation into the game action the admin would have taken -- mark_shot_missed
for a confident miss, hit_user for a confident, unambiguously identified hit.
Everything else stays in the queue for the admin.

**The stronger model stands in for the admin.** That is what the game's
escalation toggle means: with it on and a model configured, *nothing reaches a
human until the stronger model has looked at it*. Every way the weak reading
can fail to settle a shot -- an unconfident verdict, a reading that fits
nobody, a tie between two candidates, an outcome this code does not recognise,
or simply too little read to name anybody -- routes to
backend.shot_escalation rather than to the queue.

So the readability test (``confident_channel_count`` and
``armbands_confident``, both in backend.shot_vision) no longer decides who gets
a second opinion; it decides only whether the **weak** reading is allowed to
name somebody on its own:

* **every channel read**, or **all but one with the armbands among them** --
  enough for this reading to name a player, if the overall confidence and the
  posterior also clear their thresholds. The armbands are the one garment the
  game hands out, so reading them makes player-ness solid rather than
  inferred, and one erasure is well within the code.
* **anything less** -- with only ``k`` readable positions an MDS code matches
  *some* codeword for any reading, so it vouches for nothing however it is
  scored. Straight to the stronger model.

Either way an unsettled shot ends up in the same place, which is the point:
the ladder sorts on whether the reading *settles* the shot, not on how legible
the photograph happened to be. A stored escalation, once one exists, is
consulted before the weak reading is retried -- its verdict outranks the
reading that prompted it, including one an admin fired by hand.

The admin therefore sees a shot only when the stronger model **handed it
back**: a verdict of "unsure" or one below its own thresholds. Two other
things land there too, and both are the absence of a second opinion rather
than the result of one -- an escalation that errored, and no stronger model to
ask, because none is configured or the game's escalation toggle is off. That
last is the kill switch: turn escalation off and every uncertainty goes back
to being the admin's, exactly as it was before any of this existed.

**Resolve everything** (roadmap R8) relaxes the *accuracy* half of that, and
only that half. With the game's toggle on, a rung that would hand the head to
the admin because nothing here is sure enough resolves it as best the evidence
allows instead: ``_decide`` stops meaning "stop the drain" and starts meaning
"resolve it as best you can, the players will complain if it is wrong". It is
appeals that make that safe -- an automatic error stops being silent and final
and becomes loud and recoverable. Three things are never forced, because
forcing them would produce a verdict nobody can appeal or nobody deserves: a
head with no completed review, a ranking the reading itself contradicts, and a
hit that ranks nobody at all (nobody to notify means nobody to complain).

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
from .shot_vision import HIT_BYSTANDER
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

        # Re-read per iteration rather than once per drain: the admin flips
        # this mid-game, and it is one cheap query beside the others here.
        resolve_everything = AdminInterface().is_ai_resolve_everything_enabled(game_id)

        decision = _decide(head, game_id, resolve_everything)
        if decision is None:
            # An ambiguous head blocks everything behind it: that is the
            # required ordering, not a missed opportunity.
            return

        action, target_id = decision
        if action == _ESCALATE:
            from . import shot_escalation

            started = None
            if AdminInterface().is_ai_escalation_enabled(game_id):
                logger.info("Escalating shot %s to the stronger model", head.id)
                started = shot_escalation.enqueue_escalation(head.id)

            if started is not None or not resolve_everything:
                # With an escalation in flight the head blocks the queue behind
                # it; with the escalation toggle off, or with no escalation
                # client configured, nothing started at all and the head simply
                # waits for the admin -- the same safety valve, reachable from
                # the admin panel as well as from the environment.
                return

            # ...unless we have been told to resolve everything, in which case
            # a second opinion that is never coming must not be the reason
            # nobody gets a verdict to appeal.
            decision = _forced_fallback(head, game_id)
            if decision is None:
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


def _stored_review(head) -> Optional[dict]:
    """The head's completed reading, or None if there isn't a usable one."""
    if head.ai_review_state != AI_REVIEW_STATE_DONE or not head.ai_review:
        return None
    try:
        review = json.loads(head.ai_review)
    except ValueError:
        return None
    return review if isinstance(review, dict) else None


def _decide(
    head, game_id: UUID, resolve_everything: bool = False
) -> Optional[Tuple[str, Optional[UUID]]]:
    """What to do with the queue head: (action, target_id), or None to stop.

    The ladder, in order (see the module docstring for why each rung is where
    it is):

    1. no completed review, or an unparseable one -> the admin's, in both
       modes: there is nothing here to resolve it *from*;
    2. a miss, confidently -> resolve it. Legacy reviews stored without a
       confidence field parse as 0.0 and can never fire -- unless
       ``resolve_everything``, which drops the threshold rather than the
       reading;
    3. a ``hit_bystander`` stored before roadmap #11 retired that mapping ->
       the admin's, or the bystander call itself when forced (it takes nothing
       off anybody). Any other unrecognised outcome is the admin's either way;
    4. a hit with the whole outfit read (or all but one, armbands included) ->
       the auto-eligible rung, gated on confidence and the posterior;
    5. any other hit -> the escalation rung, which is about what the *stronger*
       model has said so far, not what this one thinks.
    """
    review = _stored_review(head)
    if review is None:
        return None

    # A stronger opinion, once one exists, outranks the weak reading that
    # prompted it -- including an escalation the admin fired by hand on a shot
    # this reading would have resolved on its own.
    if head.ai_escalation_state is not None:
        return _decide_escalated(head, game_id, resolve_everything)

    try:
        confidence = float(review.get("confidence"))
    except (TypeError, ValueError):
        confidence = 0.0

    outcome = review.get("outcome")
    if outcome == MISS:
        if confidence >= CONFIDENT:
            return (_MISS, None)
        return _decide_escalated(head, game_id, resolve_everything)
    if outcome != HIT_PLAYER:
        return _decide_escalated(head, game_id, resolve_everything)

    readable = confident_channel_count(review)
    if readable == DEFAULT_SCHEME.channels.n or (
        readable == DEFAULT_SCHEME.channels.n - 1 and armbands_confident(review)
    ):
        return _decide_auto_hit(head, game_id, review, confidence, resolve_everything)

    return _decide_escalated(head, game_id, resolve_everything)


def _target_from_ranking(
    head, users, ranked, resolve_everything: bool
) -> Optional[Tuple[str, Optional[UUID]]]:
    """Turn a ranking of the candidates into a hit, or None.

    Unforced this is the conservatism the slot-decode gate had, expressed
    against the posterior instead of the code: act only on a confident, untied
    ranking that nothing in the reading contradicts.

    Forced, an unconfident or tied ranking is acted on anyway -- naming the most
    likely candidate is what gives the two people who were there a verdict to
    appeal. Two things are never forced, because they leave nothing worth
    appealing: a ranking the reading itself *contradicts*, which would name
    somebody the evidence argues against, and no ranking at all, which names
    nobody to notify and so nobody who can complain.
    """
    if ranked is None or ranked.inconsistent:
        return None
    if not resolve_everything and (not ranked.confident or ranked.ambiguous):
        return None

    target = next((u for u in users if u.id == ranked.best), None)
    if target is None or target.id == head.user_id:
        return None

    return (_HIT, target.id)


def _decide_auto_hit(
    head, game_id: UUID, review: dict, confidence: float, resolve_everything: bool
) -> Optional[Tuple[str, Optional[UUID]]]:
    """The auto-eligible rung: enough of the outfit was read that this reading
    can name somebody on its own.

    It still has to: the reply has to be confident overall, and the reading has
    to pick out one non-shooter candidate confidently and without a tie -- see
    backend.shot_identification.rank_candidates, which scores the reading
    against what each candidate is *actually wearing* rather than decoding it
    against the code. ``resolve_everything`` drops both of those bars; see
    :func:`_target_from_ranking` for the two it never drops.

    A candidate who is already knocked out is acted on like any other: the shot
    genuinely hit them, it simply takes nothing off them. Withholding it would
    leave the shot behind a kill blocking the queue for an admin to rubber-stamp.
    """
    from .admin_interface import AdminInterface

    if confidence >= CONFIDENT:
        users = AdminInterface().get_users_for_game(game_id)
        ranked = rank_candidates(head, users, review)
        decision = _target_from_ranking(head, users, ranked, False)
        if decision is not None:
            return decision

    return _decide_escalated(head, game_id, resolve_everything)


def _forced_fallback(head, game_id: UUID) -> Optional[Tuple[str, Optional[UUID]]]:
    """The weak reading's best guess, for a head "resolve everything" must not
    leave sitting there.

    Reached when the stronger model was never going to answer -- escalation off
    or unconfigured -- or answered "unsure". The ranking's own gates come off;
    the two that mean there is nothing to say stay on.
    """
    from .admin_interface import AdminInterface

    review = _stored_review(head)
    if review is None:
        return None

    # Whatever the weak reading's own bottom line was: the ranking is only the
    # right answer when it said somebody was hit.
    outcome = review.get("outcome")
    if outcome == MISS:
        return (_MISS, None)
    if outcome == HIT_BYSTANDER:
        return (_BYSTANDER, None)
    if outcome != HIT_PLAYER:
        return None

    users = AdminInterface().get_users_for_game(game_id)
    ranked = rank_candidates(head, users, review)

    return _target_from_ranking(head, users, ranked, True)


def _forced_escalated_verdict(payload) -> Optional[Tuple[str, Optional[UUID]]]:
    """What a stored escalation says once its thresholds are off.

    backend.shot_escalation.decide_from_escalation refuses a verdict it is not
    confident enough in, because naming the wrong player takes somebody's life.
    Forced, it is named anyway: a verdict is the thing a player can appeal, and
    an unappealed silence is not. "unsure" -- and anything malformed -- still
    says nothing, and the caller falls back to the weak reading instead.
    """
    from . import shot_escalation

    if not isinstance(payload, dict):
        return None

    verdict = payload.get("verdict")
    if verdict == shot_escalation.VERDICT_MISS:
        return (shot_escalation.ACTION_MISS, None)
    if verdict == shot_escalation.VERDICT_BYSTANDER:
        return (shot_escalation.ACTION_BYSTANDER, None)
    if verdict != shot_escalation.VERDICT_PLAYER:
        return None

    try:
        return (shot_escalation.ACTION_HIT, UUID(str(payload.get("target_user_id"))))
    except (TypeError, ValueError):
        return None


def _decide_escalated(
    head, game_id: UUID, resolve_everything: bool
) -> Optional[Tuple[str, Optional[UUID]]]:
    """The escalation rung: too little was read for this reading to name
    anybody, so what happens next depends on the stronger model.

    Never escalated -> escalate now, in both modes: a second opinion that is
    actually coming beats a forced guess. Pending -> wait, blocking the queue
    behind it exactly as an ambiguous head does. Errored -> the admin's (a
    re-run of the weak review clears it, see
    AdminInterface.store_shot_ai_review); neither of those is ever forced, one
    being a verdict still coming and the other a verdict that never came.
    Done -> whatever backend.shot_escalation makes of the verdict,
    re-validated here against the roster because the escalation may have
    finished minutes ago. That re-validation asks only whether the named player
    is still somebody this shot could have hit, not whether they are still
    alive: somebody knocked out in the meantime was still hit, for no damage.
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
    if decision is None and resolve_everything:
        decision = _forced_escalated_verdict(payload)
        if decision is None:
            # "unsure", or a reply that never matched the contract: the
            # stronger model has nothing to add, so the weak reading's ranking
            # is the best there is.
            return _forced_fallback(head, game_id)
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
