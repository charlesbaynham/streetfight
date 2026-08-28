import React, { useCallback, useEffect, useState } from "react";
import { sendAPIRequest } from "./utils";
import { AdminPage, adminPost } from "./AdminCommon";
import { getShotFromCache, evictShotFromCache } from "./ShotCache";
import ShotMap from "./ShotMap";
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

// The AI's reading of a shot, shown as tags under the photo. Advisory only -
// the admin still decides every shot with the buttons alongside.
function ShotAiTags({ shot_id }) {
  const [state, setState] = useState(null);
  const [review, setReview] = useState(null);
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

  return (
    <>
      {listener}
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
export function verdictText(shot) {
  if (shot.result === "hit") {
    const target = shot.game.teams
      .flatMap((team) => team.users)
      .find((user) => user.id === shot.target_user_id);
    return `Hit${target ? ` on ${target.name}` : ""}`;
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

// the shot's location context, with their distance from the shooter at the
// moment it was taken. Excludes the shooter themselves.
export function rankShotCandidates(shot_data) {
  const shooting_user_id = shot_data.user_id;
  const context = JSON.parse(shot_data.location_context);

  // Get user location in context array
  const userIndex = context.findIndex(
    (location) => location.user_id === shooting_user_id,
  );
  console.log("User index in context array:", userIndex);

  const shooting_user_data = context[userIndex];
  const shooting_user_latitude = shooting_user_data.latitude;
  const shooting_user_longitude = shooting_user_data.longitude;

  // Remove the user from the context array
  const otherUsersContext = context.filter(
    (location) => location.user_id !== shooting_user_id,
  );
  console.log("Updated context array:", otherUsersContext);

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
      // Calculate distance between two points
      const R = 6371e3; // metres
      const φ1 = (shooting_user_latitude * Math.PI) / 180; // φ, λ in radians
      const φ2 = (latitude * Math.PI) / 180;
      const Δφ = ((latitude - shooting_user_latitude) * Math.PI) / 180;
      const Δλ = ((longitude - shooting_user_longitude) * Math.PI) / 180;

      const a =
        Math.sin(Δφ / 2) * Math.sin(Δφ / 2) +
        Math.cos(φ1) * Math.cos(φ2) * Math.sin(Δλ / 2) * Math.sin(Δλ / 2);
      const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));

      const distance = R * c; // in metres

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

function NearestPlayers({ shot_data }) {
  if (shot_data === null) return;

  const shooting_users = rankShotCandidates(shot_data);

  return (
    <>
      <h3>Candidates:</h3>
      <ul>
        {shooting_users.map((user, idx) => (
          <li key={idx}>
            {user.user} - {user.team} - ({user.distance.toFixed(2)}m)
          </li>
        ))}
      </ul>
    </>
  );
}

function ShotQueuePanel() {
  const [shot, setShot] = useState(null);
  const [shotsInQueue, setShotsInQueue] = useState([]);
  const [currentShotIdx, setCurrentShotIdx] = useState(0);
  // Off by default: the queue's job during a game is only what needs
  // adjudicating. On, it doubles as the history view for reviewing a game.
  const [showChecked, setShowChecked] = useState(false);

  // On update, get the current list of shot IDs in the queue and pre-load them all
  const update = useCallback(() => {
    sendAPIRequest("admin_get_shots_info", {
      include_checked: showChecked,
    }).then(async (response) => {
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
  }, [currentShotIdx, showChecked]);

  // If current shot ID changes, load the shot from the cache into the state
  useEffect(() => {
    getShotFromCache(shotsInQueue[currentShotIdx]).then((shot) => {
      console.log("Setting shot", shot);
      setShot(shot);
    });
  }, [currentShotIdx, shotsInQueue]);

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
            type="checkbox"
            checked={showChecked}
            onChange={(event) => setShowChecked(event.target.checked)}
          />
          Show adjudicated shots
        </label>
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
              <NearestPlayers shot_data={shot} />
              {shot.checked ? null : (
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
              )}
            </Col>
          </Row>
          {shot.checked ? null : (
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
          )}
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
