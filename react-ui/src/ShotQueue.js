import React, { useCallback, useEffect, useState } from "react";
import { sendAPIRequest } from "./utils";
import { AdminPage, adminPost } from "./AdminCommon";
import { getShotFromCache, evictShotFromCache } from "./ShotCache";
import ShotMap, { haversineMetres } from "./ShotMap";
import UpdateListener from "./UpdateListener";
import { Row, Col } from "react-bootstrap";

import styles from "./ShotQueue.module.css";

const OUTCOME_LABELS = {
  hit_player: ["HIT", styles.outcomeHit],
  hit_bystander: ["Bystander - not a hit", styles.outcomeBystander],
  miss: ["Miss", styles.outcomeMiss],
};

const ESCALATION_VERDICT_LABELS = {
  miss: ["Miss", styles.outcomeMiss],
  bystander: ["Bystander - not a hit", styles.outcomeBystander],
  unsure: ["Needs your call", styles.outcomeUnsure],
};

// What each party meant by their reason for appealing (backend/model.py's
// APPEAL_REASONS). The same enum value reads differently depending on who
// said it: "wrong_target" from the shooter is "it hit somebody else", from
// the target it is "that wasn't me".
const APPEAL_REASON_LABELS = {
  shooter: {
    actually_hit: "it actually hit",
    wrong_target: "it hit someone else",
  },
  target: {
    missed: "it missed me",
    wrong_target: "that wasn't me",
    not_a_player: "that's not a player",
    already_out: "I was already out",
  },
};

const APPEAL_STATE_LABELS = {
  open: "Contested - awaiting your ruling",
  upheld: "Appeal upheld",
  rejected: "Appeal rejected",
};

// The AI's reading of a shot, shown as tags under the photo. Advisory only -
// the admin still decides every shot with the buttons alongside.
function ShotAiTags({ shot_id }) {
  const [state, setState] = useState(null);
  const [review, setReview] = useState(null);
  const [identification, setIdentification] = useState(null);
  const [escalationState, setEscalationState] = useState(null);
  const [escalation, setEscalation] = useState(null);

  const update = useCallback(() => {
    if (!shot_id) return;
    // Deliberately not read through ShotCache: that caches by shot id
    // permanently, so a review arriving after the image was cached would
    // never show up.
    sendAPIRequest("admin_get_shot_ai_review", { shot_id: shot_id }).then(
      async (response) => {
        if (!response.ok) return;
        const body = await response.json();
        setState(body.state);
        setReview(body.review);
        setIdentification(body.identification);
        setEscalationState(body.escalation_state);
        setEscalation(body.escalation);
      },
    );
  }, [shot_id]);

  useEffect(update, [update]);

  // A review lands seconds after the shot it describes, so refetch when the
  // backend says the queue changed - the shot id alone will not have.
  const listener = <UpdateListener update_type="shots" callback={update} />;

  if (!state) return listener;

  if (state === "pending") {
    return (
      <>
        {listener}
        <p className={styles.aiReason}>Reviewing...</p>
      </>
    );
  }

  if (state === "error") {
    return (
      <>
        {listener}
        <div className={styles.tagRow}>
          {/* "CharlesBot" is the display name for what the API calls ai_review (#1). */}
          <span className={`${styles.tag} ${styles.outcomeError}`}>
            CharlesBot review failed: {review ? review.error : "unknown error"}
          </span>
        </div>
      </>
    );
  }

  if (!review) return listener;

  const verdict = charlesBotVerdict({
    review,
    identification,
    escalation,
    escalationState,
  });

  return (
    <>
      {listener}
      {verdict ? <p className={styles.botVerdict}>{verdict}</p> : null}
      <div className={styles.tagRow}>
        {outcomeTag(review)}
        {zoomTag(review)}
        <ChannelTags channels={review.channels} />
      </div>
      <p className={styles.aiReason}>
        {review.outcome_reason}
        {review.reasoning ? ` - ${review.reasoning}` : null}
      </p>
      <ShotEscalation state={escalationState} escalation={escalation} />
    </>
  );
}

// One sentence saying what the machine makes of this shot, in the words the
// admin would use themselves - the tags below it are the working, this is the
// answer. Null when there is nothing to say.
//
// The ladder is ordered by what actually knows most: an escalation was asked
// for precisely because the cheap reading was not good enough, so it wins;
// then a confident identification, which can name somebody; then the two-way
// call the admin has to break; then a hit with no name attached.
export function charlesBotVerdict({
  review,
  identification,
  escalation,
  escalationState,
}) {
  const NO_NAME = "CharlesBot thinks: hit on a player, but can't tell who";

  if (
    escalationState === "done" &&
    escalation &&
    escalation.verdict === "player"
  )
    return escalation.target_name
      ? `CharlesBot thinks: hit on ${escalation.target_name}`
      : NO_NAME;

  if (!review) return null;

  if (review.outcome === "hit_player") {
    const ranked = (identification && identification.ranked) || [];
    const clean =
      identification &&
      identification.confident &&
      !identification.ambiguous &&
      !identification.inconsistent;

    if (clean && ranked.length)
      return `CharlesBot thinks: hit on ${ranked[0].name}`;
    if (ranked.length >= 2)
      return (
        `CharlesBot thinks: hit - probably ${ranked[0].name} ` +
        `(${ranked[0].probability.toFixed(1)}) or ${ranked[1].name} ` +
        `(${ranked[1].probability.toFixed(1)})`
      );
    return NO_NAME;
  }

  if (review.outcome === "hit_bystander")
    return "CharlesBot thinks: that's a bystander, not a hit";
  if (review.outcome === "miss") return "CharlesBot thinks: miss";
  return null;
}

// The strong model's verdict, when a shot was hard enough for the cheap
// model's reading to get escalated. Distinct from the weak review above -
// this is what the human is actually deciding against for an "unsure" shot.
function ShotEscalation({ state, escalation }) {
  if (!state) return null;

  if (state === "pending") {
    return (
      <p className={styles.aiReason}>
        Escalated to the stronger model - reviewing...
      </p>
    );
  }

  if (state === "error") {
    return (
      <div className={styles.tagRow}>
        <span className={`${styles.tag} ${styles.outcomeError}`}>
          Escalation failed: {escalation?.error || "unknown error"}
        </span>
      </div>
    );
  }

  if (state !== "done" || !escalation) return null;

  const candidates = Array.isArray(escalation.candidates)
    ? escalation.candidates
    : [];

  return (
    <div className={styles.escalationBlock}>
      <p className={styles.escalationLabel}>Stronger model</p>
      <div className={styles.tagRow}>{escalationVerdictTag(escalation)}</div>
      {escalation.reasoning ? (
        <p className={styles.aiReason}>{escalation.reasoning}</p>
      ) : null}
      {candidates.length ? (
        <ol className={styles.escalationCandidates}>
          {candidates.map((candidate, idx) => (
            <li key={candidate.user_id || idx}>
              {candidate.name} - {Math.round(100 * candidate.probability)}%
              {candidate.reference_photo_shown
                ? " (reference photo shown)"
                : null}
            </li>
          ))}
        </ol>
      ) : null}
    </div>
  );
}

// The strong model's verdict, as one tag - shared so it can be reused
// wherever an escalation result needs showing (e.g. the replay workbench).
export function escalationVerdictTag(escalation) {
  if (escalation.verdict === "player") {
    const label = escalation.target_name
      ? `HIT on ${escalation.target_name}`
      : "HIT";
    return (
      <span className={`${styles.tag} ${styles.outcomeHit}`}>
        {label}
        {typeof escalation.confidence === "number"
          ? ` (${Math.round(100 * escalation.confidence)}%)`
          : null}
      </span>
    );
  }

  const [label, verdictStyle] = ESCALATION_VERDICT_LABELS[
    escalation.verdict
  ] || [escalation.verdict, styles.outcomeMiss];

  return (
    <span className={`${styles.tag} ${verdictStyle}`}>
      {label}
      {escalation.verdict !== "unsure" &&
      typeof escalation.confidence === "number"
        ? ` (${Math.round(100 * escalation.confidence)}%)`
        : null}
    </span>
  );
}

// What the model made of the photograph overall, as one tag. Shared so a
// reading looks the same in the queue, the replay workbench and the
// reference-photo kit check.
export function outcomeTag(review) {
  const [label, outcomeStyle] = OUTCOME_LABELS[review.outcome] || [
    review.outcome,
    styles.outcomeMiss,
  ];

  return <span className={`${styles.tag} ${outcomeStyle}`}>{label}</span>;
}

// The model's per-channel colour reading, as tags. `warnBelow` (unset in the
// queue, where the admin decides every shot anyway) marks any channel it read
// less confidently than that and shows the number, so "the trousers read as
// black at 0.4" is visible rather than hidden behind a confident-looking tag.
export function ChannelTags({ channels, warnBelow = null }) {
  return (
    <>
      {Object.entries(channels || {}).map(([name, channel]) => (
        <span
          key={name}
          className={`${styles.tag} ${channel.colour ? "" : styles.tagUnknown} ${
            isMarginal(channel, warnBelow) ? styles.tagMarginal : ""
          }`}
        >
          {channel.hex ? (
            <span
              className={styles.swatch}
              style={{ background: channel.hex }}
            />
          ) : null}
          {name}: {channel.colour || "unknown"}
          {isMarginal(channel, warnBelow)
            ? ` (${Math.round(100 * channel.confidence)}%)`
            : null}
        </span>
      ))}
    </>
  );
}

// A channel the model read, but not confidently enough to trust at the door.
export function isMarginal(channel, warnBelow) {
  return (
    warnBelow !== null &&
    !!channel.colour &&
    typeof channel.confidence === "number" &&
    channel.confidence < warnBelow
  );
}

// The zoom tag: how many times the zoom was spent (0, 1 or 2). Older stored
// reviews only ever recorded a zoom_used bool, so fall back to that rather
// than showing a wrong count.
export function zoomTag(review) {
  if (review.zoom_count) {
    return (
      <span className={`${styles.tag} ${styles.tagZoom}`}>
        Zoomed in ×{review.zoom_count}
      </span>
    );
  }
  if (review.zoom_used) {
    return <span className={`${styles.tag} ${styles.tagZoom}`}>Zoomed in</span>;
  }
  return null;
}

// What an adjudicated shot was marked as, for the history view.
// `targetName`, when the caller already knows it, saves walking the game model
// - the spectator feed carries the name but deliberately not the whole game.
export function verdictText(shot, targetName = null) {
  if (shot.result === "hit") {
    const target =
      targetName ||
      (shot.game
        ? (
            shot.game.teams
              .flatMap((team) => team.users)
              .find((user) => user.id === shot.target_user_id) || {}
          ).name
        : null);
    return `Hit${target ? ` on ${target}` : ""}`;
  }
  return (
    {
      miss: "Miss",
      bystander: "Bystander",
      refunded: "Refunded",
    }[shot.result] || shot.result
  );
}

// The admin's free-text annotation of a shot: why the verdict is what it is.
// No game logic reads these notes - they exist so the reasoning survives for
// the offline replay harness (scripts/replay_shot_reviews.py). Fetched and
// saved through their own endpoints rather than the shot model, because
// ShotCache caches shot models permanently.
function ShotNotes({ shot_id }) {
  const [notes, setNotes] = useState(null);
  const [dirty, setDirty] = useState(false);

  useEffect(() => {
    setNotes(null);
    setDirty(false);
    sendAPIRequest("admin_get_shot_notes", { shot_id }).then(
      async (response) => {
        if (!response.ok) return;
        const body = await response.json();
        setNotes(body.notes);
      },
    );
  }, [shot_id]);

  const save = useCallback(() => {
    adminPost("admin_set_shot_notes", { shot_id, notes }).then((response) => {
      if (response.ok) setDirty(false);
    });
  }, [shot_id, notes]);

  if (notes === null) return null;

  return (
    <div className={styles.notesBox}>
      <textarea
        aria-label="Admin notes"
        value={notes}
        placeholder="Why is this a hit/miss? (for the record, not the game)"
        onChange={(event) => {
          setNotes(event.target.value);
          setDirty(true);
        }}
      />
      <button onClick={save} disabled={!dirty}>
        {dirty ? "Save notes" : "Notes saved"}
      </button>
    </div>
  );
}

// Who is contesting this shot and on what grounds (roadmap R8). Fetched
// through its own endpoint for the same reason ShotAiTags is: the appeal
// changes after the shot model was cached, so a cached model would show a
// state that had since moved on. Renders nothing for a shot nobody appealed,
// and tells the panel what it found so the adjudication buttons can come back
// for an open appeal.
function AppealDetails({ shot_id, onAppealState }) {
  const [appeal, setAppeal] = useState(null);

  const update = useCallback(() => {
    if (!shot_id) return;
    sendAPIRequest("admin_get_shot_appeal", { shot_id: shot_id }).then(
      async (response) => {
        if (!response.ok) return;
        const body = await response.json();
        setAppeal(body);
        onAppealState(body.appeal_state);
      },
    );
  }, [shot_id, onAppealState]);

  useEffect(update, [update]);

  // An appeal can be lodged (or settled) while the admin is looking at the
  // shot, and both fire a "shots" update.
  const listener = <UpdateListener update_type="shots" callback={update} />;

  if (!appeal || !appeal.appeal_state) return listener;

  const open = appeal.appeal_state === "open";
  const appellants = [
    ["shooter", appeal.shooter_name, appeal.shooter_appeal_reason],
    ["target", appeal.target_name, appeal.target_appeal_reason],
  ].filter(([, , reason]) => reason);

  return (
    <>
      {listener}
      <div className={open ? styles.appealOpen : styles.appealSettled}>
        <p className={styles.appealLabel}>
          {APPEAL_STATE_LABELS[appeal.appeal_state] || appeal.appeal_state}
        </p>
        <ul className={styles.appealReasons}>
          {appellants.map(([party, name, reason]) => (
            <li key={party}>
              {name || "unnamed"} ({party}): "
              {(APPEAL_REASON_LABELS[party] || {})[reason] || reason}"
            </li>
          ))}
        </ul>
        <p className={styles.appealFacts}>
          Standing verdict: {appeal.result || "unadjudicated"}
          {appeal.appealed_at
            ? ` - appealed at ${new Date(
                appeal.appealed_at * 1000,
              ).toLocaleTimeString()}`
            : null}
        </p>
      </div>
    </>
  );
}

// the shot's location context, with their distance from the shooter at the
// moment it was taken. Excludes the shooter themselves.
export function rankShotCandidates(shot_data) {
  const shooting_user_id = shot_data.user_id;
  const context = JSON.parse(shot_data.location_context);

  // Get user location in context array
  const userIndex = context.findIndex(
    (location) => location.user_id === shooting_user_id,
  );

  const shooting_user_data = context[userIndex];
  const shooting_user_latitude = shooting_user_data.latitude;
  const shooting_user_longitude = shooting_user_data.longitude;

  // Remove the user from the context array
  const otherUsersContext = context.filter(
    (location) => location.user_id !== shooting_user_id,
  );

  // For each remaining player, calculate the distance from them to the shooting player
  const shooting_users = otherUsersContext.map(
    ({
      user_id,
      team_id,
      user,
      team,
      latitude,
      longitude,
      state,
      timestamp,
    }) => {
      const distance = haversineMetres(
        shooting_user_latitude,
        shooting_user_longitude,
        latitude,
        longitude,
      );

      return {
        distance,
        user_id,
        team_id,
        user,
        team,
        latitude,
        longitude,
        state,
        timestamp,
      };
    },
  );

  // Sort shooting_users by distance
  shooting_users.sort((a, b) => (a.distance > b.distance ? 1 : -1));

  return shooting_users;
}

// How far each player was from the shooter, by user id. A shot whose location
// context is missing or malformed still has an identification worth showing,
// so a bad fix costs the metres column and nothing else.
function metresByUser(shot) {
  const metres = {};
  try {
    rankShotCandidates(shot).forEach((candidate) => {
      metres[candidate.user_id] = candidate.distance;
    });
  } catch (e) {
    // no usable location context
  }
  return metres;
}

// Who this shot's reading actually looks like: the decoder's ranking over the
// living players (backend/shot_identification.py), with the GPS distance that
// went into it alongside. Replaces the old nearest-first list, which ranked on
// proximity alone and so put the shooter's own teammate at the top.
//
// Fetched here rather than passed down from ShotAiTags: the ranking is scored
// against the current outfits every time it is asked for, so it arrives (and
// changes) with the review rather than with the shot.
function RankedCandidates({ shot, canAdjudicate, onHit }) {
  const [state, setState] = useState(null);
  const [identification, setIdentification] = useState(null);
  // Two steps on purpose: a stray tap on a name must not decide the shot, so
  // picking a candidate only highlights them and the ruling is a separate,
  // deliberate press below the list.
  const [selected, setSelected] = useState(null);

  const shot_id = shot ? shot.id : null;

  // Whoever was picked was picked about the shot on screen a moment ago.
  useEffect(() => setSelected(null), [shot_id]);

  const update = useCallback(() => {
    if (!shot_id) return;
    sendAPIRequest("admin_get_shot_ai_review", { shot_id: shot_id }).then(
      async (response) => {
        if (!response.ok) return;
        const body = await response.json();
        setState(body.state);
        setIdentification(body.identification);
      },
    );
  }, [shot_id]);

  useEffect(update, [update]);

  const listener = <UpdateListener update_type="shots" callback={update} />;

  if (state !== "done" || !identification) return listener;

  const metres = metresByUser(shot);
  const unreadable = identification.readable_channels === 0;
  const ranked = unreadable ? [] : (identification.ranked || []).slice(0, 6);
  // An adjudicated shot still shows its ranking - it is why the verdict is
  // what it is - but there is nothing left to rule on, so it is a list to read
  // rather than a set of buttons.
  const selectable = !!canAdjudicate;
  const chosen = ranked.find((candidate) => candidate.user_id === selected);

  return (
    <>
      {listener}
      <h3>Candidates:</h3>
      {unreadable ? (
        <p className={styles.candidateFlag}>
          Nothing readable in this photo - a ranking would be a guess
        </p>
      ) : null}
      {identification.ambiguous ? (
        <p className={styles.candidateFlag}>
          Two candidates are too close to call
        </p>
      ) : null}
      {identification.inconsistent ? (
        <p className={styles.candidateFlag}>The reading fits nobody cleanly</p>
      ) : null}
      {ranked.length ? <OutfitKey outfit={ranked[0].outfit} /> : null}
      <ul className={styles.candidateList}>
        {ranked.map((candidate) => {
          const picked = candidate.user_id === selected;
          const Row = selectable ? "button" : "div";
          const rowProps = selectable
            ? {
                type: "button",
                "aria-pressed": picked,
                onClick: () => setSelected(picked ? null : candidate.user_id),
              }
            : {};
          return (
            <li key={candidate.user_id}>
              <Row
                className={`${styles.candidateRow} ${
                  selectable ? styles.candidatePickable : ""
                } ${picked ? styles.candidatePicked : ""}`}
                {...rowProps}
              >
                <span className={styles.candidateName}>
                  {candidate.name || candidate.user_id}
                </span>
                <span className={styles.candidateTeam}>
                  {candidate.team_name || "no team"}
                </span>
                <span className={styles.candidateFacts}>
                  {candidateFacts(candidate, metres[candidate.user_id])}
                </span>
                <CandidateOutfit outfit={candidate.outfit} />
              </Row>
            </li>
          );
        })}
      </ul>
      {selectable && ranked.length ? (
        <button
          className={styles.hitCandidate}
          disabled={!chosen}
          onClick={() => onHit(chosen.user_id)}
        >
          {chosen
            ? `Hit ${chosen.name || chosen.user_id}`
            : "Hit candidate - tap one above first"}
        </button>
      ) : null}
    </>
  );
}

// Which garment each swatch below is, said once for the whole list rather than
// on every row. The outfits come in the scheme's channel order, which is the
// order the review's own tags are in, so the admin reads a candidate's colours
// straight down against what CharlesBot called; repeating "tshirt:" six times
// would say nothing the column position doesn't. The tints need no key -
// green against red says which garments fit and which don't on sight.
function OutfitKey({ outfit }) {
  const names = Object.keys(outfit || {});
  if (!names.length) return null;
  return <p className={styles.outfitKey}>{names.join(" - ")}</p>;
}

// What one candidate is actually wearing, as swatches and colour names in
// channel order. The same {colour, hex} shape a review's channels have, so
// this reads as a row against the tags under the photograph, with each garment
// tinted by whether the reading agrees with it (backend's `agrees`: null where
// there is nothing to compare, which is exactly what the code distance skips).
function CandidateOutfit({ outfit }) {
  if (!outfit) return null;
  return (
    <span className={styles.candidateOutfit}>
      {Object.entries(outfit).map(([name, garment]) => (
        <span
          key={name}
          className={`${styles.garment} ${agreementStyle(garment.agrees)}`}
          title={`${name}: ${garment.colour || "not in palette"} - ${agreementWords(
            garment.agrees,
          )}`}
        >
          <span
            className={`${styles.swatch} ${garment.hex ? "" : styles.swatchUnknown}`}
            style={garment.hex ? { background: garment.hex } : undefined}
          />
          {garment.colour || "?"}
        </span>
      ))}
    </span>
  );
}

// Green and red are answers, grey is the absence of one - the house rule that
// colour means certainty (see CLAUDE.md's admin exemplar), which is why an
// unread garment is not amber: nobody is unsure, nobody looked.
function agreementStyle(agrees) {
  if (agrees === true) return styles.garmentAgrees;
  if (agrees === false) return styles.garmentDisagrees;
  return styles.garmentUnread;
}

function agreementWords(agrees) {
  if (agrees === true) return "agrees with the reading";
  if (agrees === false) return "contradicts the reading";
  return "not read in this photo";
}

// The numbers behind one candidate's place in the ranking. An em dash for the
// distance rather than a zero: no fix at all is not the same as standing on
// top of the shooter.
function candidateFacts(candidate, distance) {
  const facts = [`p=${candidate.probability.toFixed(2)}`];
  if (candidate.code_distance !== null && candidate.code_distance !== undefined)
    facts.push(`code distance ${candidate.code_distance}`);
  facts.push(typeof distance === "number" ? `${Math.round(distance)} m` : "—");
  return facts.join(" - ");
}

// The shot on screen, with the queue - not the cache - the authority on
// whether it has been ruled on.
//
// ShotCache keeps a shot's model for ever, which is right for the photograph
// and wrong for `checked`: that flips when an admin rules, when CharlesBot's
// auto-actions resolve the head of the queue with nobody watching, and - the
// way it actually bit - when the database is rebuilt underneath the same shot
// id. The test world and the demo game mint their ids from a seed, so wiping
// and replaying hands the same ids back as brand new, unadjudicated shots
// while the browser still holds last run's adjudicated copy. `canAdjudicate`
// then hid every ruling control on a shot the queue was actively asking
// about: the admin could see the photograph and had no way to call it.
//
// So when the id came from the unadjudicated queue, the shot is unruled by
// construction, and a cached copy that disagrees is stale: throw it away and
// ask again. Once, deliberately - if the server really does say checked, that
// is the truth and the controls stay away.
async function loadQueuedShot(shot_id, mustBeUnadjudicated) {
  const shot = await getShotFromCache(shot_id);
  if (!shot || !mustBeUnadjudicated || !shot.checked) return shot;
  console.log("Cached shot says adjudicated, queue says pending", shot_id);
  await evictShotFromCache(shot_id);
  return getShotFromCache(shot_id);
}

function ShotQueuePanel() {
  const [shot, setShot] = useState(null);
  const [shotsInQueue, setShotsInQueue] = useState([]);
  const [currentShotIdx, setCurrentShotIdx] = useState(0);
  // Off by default: the queue's job during a game is only what needs
  // adjudicating. On, it doubles as the history view for reviewing a game.
  const [showChecked, setShowChecked] = useState(false);
  // The contested list is a different queue, not a filter on this one: those
  // shots are all adjudicated already, and are an argument to settle rather
  // than a backlog to drain (roadmap R8).
  const [contested, setContested] = useState(false);
  const [appealState, setAppealState] = useState(null);

  // On update, get the current list of shot IDs in the queue and pre-load them all
  const update = useCallback(() => {
    sendAPIRequest(
      contested ? "admin_get_contested_shots_info" : "admin_get_shots_info",
      contested ? null : { include_checked: showChecked },
    ).then(async (response) => {
      if (!response.ok) return;
      const shot_ids = await response.json();

      setShotsInQueue(shot_ids);

      const shownIdx = Math.min(currentShotIdx, shot_ids.length - 1);
      if (shownIdx !== currentShotIdx) {
        setCurrentShotIdx(shownIdx);
      }

      // The shot on screen first, alone: pre-loading the whole queue alongside
      // it means competing for the connection, and the admin cannot judge a
      // shot they cannot see yet.
      if (shot_ids[shownIdx]) {
        await getShotFromCache(shot_ids[shownIdx]);
      }

      // Load the rest in background
      await Promise.all(
        shot_ids.map((id) => {
          console.log("Pre-loading shot", id);
          return getShotFromCache(id);
        }),
      );
    });
  }, [currentShotIdx, showChecked, contested]);

  // If current shot ID changes, load the shot from the cache into the state
  useEffect(() => {
    // Whatever AppealDetails knew was about the shot we are leaving
    setAppealState(null);
    loadQueuedShot(
      shotsInQueue[currentShotIdx],
      !showChecked && !contested,
    ).then((shot) => {
      console.log("Setting shot", shot);
      setShot(shot);
    });
  }, [currentShotIdx, shotsInQueue, showChecked, contested]);

  const hitUser = useCallback(
    (shot_id, target_user_id) => {
      adminPost("admin_shot_hit_user", {
        shot_id: shot_id,
        target_user_id: target_user_id,
      })
        .then((_) => evictShotFromCache(shot_id))
        .then((_) => update());
    },
    [update],
  );

  const markShotMissed = useCallback(() => {
    adminPost("admin_mark_shot_missed", { shot_id: shot.id })
      .then((_) => evictShotFromCache(shot.id))
      .then((_) => update());
  }, [shot, update]);

  const markShotBystander = useCallback(() => {
    adminPost("admin_mark_shot_bystander", { shot_id: shot.id })
      .then((_) => evictShotFromCache(shot.id))
      .then((_) => update());
  }, [shot, update]);

  // The escalated second opinion, asked for by hand: it runs whatever the
  // game's toggles say, so the reasons it can refuse are things the admin has
  // to fix (no model configured, no review to escalate from) rather than
  // background noise for the error log.
  const escalateShot = useCallback(async () => {
    const response = await adminPost("admin_escalate_shot", {
      shot_id: shot.id,
    });
    if (response.ok) return;
    const body = await response.json().catch(() => null);
    window.alert(body?.detail || "Could not escalate this shot");
  }, [shot]);

  const refundShot = useCallback(() => {
    adminPost("admin_refund_shot", { shot_id: shot.id })
      .then((_) => evictShotFromCache(shot.id))
      .then((_) => update());
  }, [shot, update]);

  useEffect(update, [update]);

  const nextShot = useCallback(() => {
    if (currentShotIdx < shotsInQueue.length - 1) {
      setCurrentShotIdx(currentShotIdx + 1);
    }
  }, [currentShotIdx, shotsInQueue]);

  const previousShot = useCallback(() => {
    if (currentShotIdx > 0) {
      setCurrentShotIdx(currentShotIdx - 1);
    }
  }, [currentShotIdx]);

  // An adjudicated shot is normally final, but an open appeal re-opens it for
  // exactly one re-ruling - which is what the contested queue is for.
  const canAdjudicate = shot && (!shot.checked || appealState === "open");

  return (
    <>
      {/* The queue changes under us: new shots arrive, and AI reviews land
          seconds after the shot they describe. */}
      <UpdateListener update_type="shots" callback={update} />
      <Row>
        <Col>
          <h1>
            Shot {currentShotIdx + 1} of {shotsInQueue.length}:
          </h1>
        </Col>
      </Row>
      <Row>
        <button
          onClick={() => {
            nextShot();
          }}
        >
          Next
        </button>
        <button
          onClick={() => {
            previousShot();
          }}
        >
          Previous
        </button>
        <label className={styles.showCheckedToggle}>
          <input
            type="radio"
            name="queue-mode"
            checked={!contested}
            onChange={() => setContested(false)}
          />
          Queue
        </label>
        <label className={styles.showCheckedToggle}>
          <input
            type="radio"
            name="queue-mode"
            checked={contested}
            onChange={() => setContested(true)}
          />
          Contested
        </label>
        {contested ? null : (
          <label className={styles.showCheckedToggle}>
            <input
              type="checkbox"
              checked={showChecked}
              onChange={(event) => setShowChecked(event.target.checked)}
            />
            Show adjudicated shots
          </label>
        )}
      </Row>

      {shot ? (
        <>
          <Row>
            <Col>
              <em>By {shot.user.name}</em>
              <img
                className={styles.shotImg}
                alt="The next shot in the queue"
                src={shot.image_base64}
              />
              {shot.checked ? (
                <p className={styles.verdict}>
                  Adjudicated: {verdictText(shot)}
                </p>
              ) : null}
              <AppealDetails shot_id={shot.id} onAppealState={setAppealState} />
              <ShotAiTags shot_id={shot.id} />
              <ShotNotes shot_id={shot.id} />
              <button
                onClick={() =>
                  adminPost("admin_review_shot", { shot_id: shot.id })
                }
              >
                Re-run CharlesBot review
              </button>
              <button onClick={() => escalateShot()}>
                Run escalated review
              </button>
            </Col>
            <Col>
              <h3>Where it was fired from:</h3>
              <ShotMap shot={shot} />
              <RankedCandidates
                shot={shot}
                canAdjudicate={canAdjudicate}
                onHit={(target_user_id) => hitUser(shot.id, target_user_id)}
              />
              {canAdjudicate ? (
                <>
                  {shot.game.teams.map((team, idx_team) => (
                    <div key={idx_team}>
                      <h3>{team.name}</h3>
                      <ul>
                        {team.users.map((target_user, idx_target_user) => (
                          <li key={idx_target_user ** 2 + idx_team ** 3}>
                            {target_user.name}
                            <button
                              onClick={() => {
                                hitUser(shot.id, target_user.id);
                              }}
                            >
                              Hit
                            </button>
                          </li>
                        ))}
                      </ul>
                    </div>
                  ))}
                </>
              ) : null}
            </Col>
          </Row>
          {canAdjudicate ? (
            <Row>
              <button
                onClick={() => {
                  markShotMissed();
                }}
              >
                Missed
              </button>
              <button
                onClick={() => {
                  markShotBystander();
                }}
              >
                Bystander
              </button>
              <button
                onClick={() => {
                  refundShot();
                }}
              >
                Refund
              </button>
            </Row>
          ) : null}
        </>
      ) : null}
    </>
  );
}

export default function ShotQueue() {
  return (
    <AdminPage>
      <ShotQueuePanel />
    </AdminPage>
  );
}
