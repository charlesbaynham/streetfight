// The user-facing shot history: a "My shots" entry for the HUD (with an
// unseen-changes badge), a fullscreen popup listing every shot with its
// adjudicated outcome, and a bubble in the corner showing the latest shot's
// status.

import React, { useCallback, useEffect, useState } from "react";

import Popup from "./Popup";
import UpdateListener from "./UpdateListener";
import { sendAPIRequest } from "./utils";
import {
  countUnseenShots,
  getShotImage,
  getShots,
  markShotsSeen,
  refreshShots,
  subscribeShots,
} from "./shotHistoryStore";

import styles from "./ShotHistory.module.css";
import scoreboardStyles from "./Scoreboard.module.css";

import checkImg from "./images/check-solid.svg";
import crossImg from "./images/cross.svg";
import crosshairImg from "./images/crosshair.svg";
import returnImg from "./images/return.svg";

const OPEN_EVENT = "streetfight:open-shot-history";

// Ask the mounted ShotHistoryController to open the popup, optionally straight
// onto one shot's detail view. A window event rather than lifted state so the
// HUD entry, the bubble and the controller don't all need a common ancestor.
export function openShotHistory(shotId = null) {
  window.dispatchEvent(new CustomEvent(OPEN_EVENT, { detail: { shotId } }));
}

// Each status gets its own colour (via the --status-colour custom property set
// by these classes) as well as its own icon, so the bubble reads at a glance
const STATE_CLASSES = {
  unreviewed: styles.stateUnreviewed,
  escalated: styles.stateEscalated,
  hit: styles.stateHit,
  miss: styles.stateMiss,
  bystander: styles.stateBystander,
  refunded: styles.stateRefunded,
  invalidated: styles.stateInvalidated,
  hitYou: styles.stateHitYou,
  appealOpen: styles.stateAppealOpen,
  appealUpheld: styles.stateAppealUpheld,
  appealRejected: styles.stateAppealRejected,
};

// The reasons each side of a shot may give for appealing it (roadmap R8).
// A subset of the backend's APPEAL_REASONS: the shooter has no case to make
// about having been hit, and the target none about their own shot landing.
export const APPEAL_REASONS = {
  fired: [
    ["actually_hit", "It actually hit"],
    ["wrong_target", "It hit someone else"],
  ],
  received: [
    ["missed", "It missed me"],
    ["wrong_target", "That wasn't me"],
    ["not_a_player", "That's not a player"],
    ["already_out", "I was already out"],
  ],
};

export const APPEALS_PER_GAME = 3;

// An appeal's own status, which supersedes the verdict it contests: while it
// is open there is no settled answer, so it is amber; once the referee has
// ruled, green and red say which way (colour means certainty).
const APPEAL_STATUS = {
  open: { state: "appealOpen", emoji: "⚖️", label: "Under appeal" },
  upheld: { state: "appealUpheld", emoji: "⚖️", label: "Appeal upheld" },
  rejected: { state: "appealRejected", emoji: "⚖️", label: "Appeal rejected" },
};

// A shot somebody else fired at this player: what it did to them, and who did
// it. The ticker has already named the shooter, so this names them too.
function receivedStatus(shot) {
  const by = shot.shooter_name ? ` - shot by ${shot.shooter_name}` : "";
  if (shot.result === "hit")
    return { state: "hitYou", emoji: "💥", label: `Hit you!${by}` };
  return {
    state: "unreviewed",
    emoji: "⏳",
    label: `Shot at you${by}`,
  };
}

// What to show for a shot's current status. Shots checked before the result
// column existed have result=null: infer from whether a target was recorded.
export function shotStatus(shot) {
  const appeal = APPEAL_STATUS[shot.appeal_state];
  // The appeal's own state supersedes the verdict, which stays as the
  // sublabel: "Under appeal" over "Hit you!" is the whole story in two lines.
  if (appeal) return { ...appeal, sublabel: baseStatus(shot).label };
  return baseStatus(shot);
}

function baseStatus(shot) {
  if (shot.direction === "received") return receivedStatus(shot);

  if (shot.checked) {
    const result = shot.result || (shot.target_name ? "hit" : "miss");
    if (result === "hit")
      return {
        state: "hit",
        icon: checkImg,
        label: shot.target_name ? `Hit ${shot.target_name}!` : "Hit!",
      };
    if (result === "refunded")
      return { state: "refunded", icon: returnImg, label: "Ammo refunded" };
    if (result === "invalidated")
      return {
        state: "invalidated",
        icon: returnImg,
        label: "Invalidated",
        sublabel: "You were knocked out before this shot could be checked",
      };
    if (result === "bystander")
      return {
        state: "bystander",
        emoji: "😲",
        label: "You shot a bystander!",
        sublabel: "Not a player - no damage done",
      };
    return { state: "miss", icon: crossImg, label: "Missed" };
  }

  // "CharlesBot" is the display name for what the API calls ai_review (#1).
  // It has looked but the call is still the referee's: distinct icon and
  // colour from a shot nobody has looked at yet
  if (shot.ai_review_state === "done" && shot.ai_suggestion) {
    // Naming the target only when the backend was sure enough to name one:
    // the shooter reads a name as who they shot.
    let label = `CharlesBot thinks: ${shot.ai_suggestion}`;
    if (shot.ai_suggestion === "hit")
      label = shot.ai_target_name
        ? `CharlesBot thinks: hit on ${shot.ai_target_name}`
        : "CharlesBot thinks: hit - can't tell who";
    return {
      state: "escalated",
      emoji: "🤖",
      label,
      sublabel: "Escalated to referee",
    };
  }

  return { state: "unreviewed", emoji: "⏳", label: "Not reviewed yet" };
}

function statusClasses(status, ...extra) {
  return [STATE_CLASSES[status.state], ...extra].filter(Boolean).join(" ");
}

// A coloured disc with the status glyph on it. The image sits in a wrapper
// rather than being the disc itself: the filter that knocks the SVGs out to
// white would otherwise whiten the disc's background too.
function StatusIcon({ status, className }) {
  return (
    <span className={statusClasses(status, styles.statusIcon, className)}>
      {status.icon ? (
        <img
          className={styles.statusIconImage}
          src={status.icon}
          alt={status.label}
        />
      ) : (
        status.emoji
      )}
    </span>
  );
}

// A shot photo with the same crosshair the player aimed with drawn over its
// centre. The shot always lands dead centre of the frame, so without the
// marker there is nothing in the picture to say what was actually aimed at -
// which matters most when the referee (or the AI) called a miss. `object-fit:
// cover` crops evenly on both sides, so the centre of the photo stays at the
// centre of the thumbnail.
function ShotThumbnail({ shotId, className, wrapperClassName }) {
  const [image, setImage] = useState(null);

  useEffect(() => {
    let cancelled = false;
    getShotImage(shotId).then((img) => {
      if (!cancelled) setImage(img);
    });
    return () => {
      cancelled = true;
    };
  }, [shotId]);

  if (!image) return <div className={className} />;
  return (
    <span
      className={[styles.imageWrapper, wrapperClassName]
        .filter(Boolean)
        .join(" ")}
    >
      <img className={className} src={image} alt="Your shot" />
      <img className={styles.crosshair} src={crosshairImg} alt="" />
    </span>
  );
}

export function formatShotTime(timeCreated) {
  const date = new Date(timeCreated);
  if (isNaN(date)) return "";
  return date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

// The HUD entry: sits under "Show scores >>" and opens the history
export function ShotHistoryButton({ standalone = false }) {
  const [shotList, setShotList] = useState(getShots());

  useEffect(() => subscribeShots(setShotList), []);

  if (!shotList || shotList.length === 0) return null;

  const numUnseen = countUnseenShots(shotList);

  return (
    <p>
      <button
        className={
          scoreboardStyles.showScoresButton +
          (standalone ? " " + scoreboardStyles.standalone : "")
        }
        onClick={() => openShotHistory()}
      >
        My shots &gt;&gt;
        {numUnseen > 0 ? (
          <span className={styles.badge}>{numUnseen}</span>
        ) : null}
      </button>
    </p>
  );
}

function ShotRow({ shot, onClick }) {
  const status = shotStatus(shot);

  return (
    <button
      className={
        styles.shotRow +
        (shot.direction === "received" ? " " + styles.receivedRow : "")
      }
      onClick={onClick}
    >
      <ShotThumbnail
        shotId={shot.id}
        className={styles.thumbnail}
        wrapperClassName={styles.thumbnailWrapper}
      />
      <div className={styles.rowText}>
        <span>
          <StatusIcon status={status} className={styles.rowIcon} />{" "}
          {status.label}
        </span>
        {status.sublabel ? (
          <span className={styles.rowSublabel}>{status.sublabel}</span>
        ) : null}
        <span className={styles.rowTime}>
          {formatShotTime(shot.time_created)}
        </span>
      </div>
    </button>
  );
}

// Whether to put an Appeal button in front of the player at all. `can_appeal`
// is the backend's own answer (backend/user_interface.appeal_refusal), but it
// goes false when the budget runs out - and a control that vanishes reads as a
// bug, so a player with no appeals left still sees the button, greyed out and
// saying why (roadmap R8).
export function appealButtonState(shot, appealsRemaining) {
  if (shot.can_appeal) return { show: true, disabled: false, label: "Appeal" };

  const outOfAppeals =
    appealsRemaining === 0 &&
    !shot.my_appeal_reason &&
    !shot.appeal_state &&
    (shot.direction === "received"
      ? shot.result === "hit"
      : shot.checked &&
        shot.result &&
        shot.result !== "refunded" &&
        shot.result !== "invalidated");

  if (outOfAppeals)
    return { show: true, disabled: true, label: "No appeals left" };

  return { show: false };
}

function reasonLabel(shot, reason) {
  const options = APPEAL_REASONS[shot.direction] || [];
  const match = options.find(([value]) => value === reason);
  return match ? match[1] : reason;
}

// The confirmation step, in the popup the detail view already lives in: pick a
// reason, then answer for the spend with the count and the refund rule both in
// front of you - the budget is only fair if the player knows the refund rule
// before they weigh using one.
function AppealConfirmation({ shot, appealsRemaining, onDone, onCancel }) {
  const [reason, setReason] = useState(null);
  const [error, setError] = useState(null);

  const confirm = useCallback(() => {
    if (!reason) return;
    sendAPIRequest(
      "appeal_shot",
      { shot_id: shot.id, reason: reason },
      "POST",
    ).then(async (response) => {
      if (response.ok) {
        onDone();
        return;
      }
      const body = await response.json().catch(() => null);
      setError((body && body.detail) || "That appeal could not be lodged");
    });
  }, [shot, reason, onDone]);

  return (
    <div className={styles.appeal}>
      <h3 className={styles.appealTitle}>What was wrong with it?</h3>
      {(APPEAL_REASONS[shot.direction] || []).map(([value, label]) => (
        <label key={value} className={styles.reasonRow}>
          <input
            type="radio"
            name="appeal-reason"
            value={value}
            checked={reason === value}
            onChange={() => setReason(value)}
          />
          {label}
        </label>
      ))}
      <p className={styles.appealQuestion}>
        Are you sure? You have{" "}
        {appealsRemaining === null ? "..." : appealsRemaining} of{" "}
        {APPEALS_PER_GAME} appeals left.
        <br />
        <span className={styles.appealRefund}>
          Successful appeals are refunded.
        </span>
      </p>
      {error ? <p className={styles.appealError}>{error}</p> : null}
      <button
        className={styles.appealButton}
        disabled={!reason}
        onClick={confirm}
      >
        Appeal this shot
      </button>
      <button className={styles.appealCancelButton} onClick={onCancel}>
        Cancel
      </button>
    </div>
  );
}

function ShotDetail({ shot, onBack, appealsRemaining, onAppealed }) {
  const [confirming, setConfirming] = useState(false);
  const status = shotStatus(shot);
  const appealButton = appealButtonState(shot, appealsRemaining);

  // A different shot in the same popup starts from its own detail view
  useEffect(() => setConfirming(false), [shot.id]);

  return (
    <div className={styles.detail}>
      <button className={styles.backButton} onClick={onBack}>
        &lt;&lt; All shots
      </button>
      <p>
        <StatusIcon status={status} className={styles.rowIcon} /> {status.label}
        {status.sublabel ? (
          <>
            <br />
            <span className={styles.rowSublabel}>{status.sublabel}</span>
          </>
        ) : null}
      </p>
      <ShotThumbnail
        shotId={shot.id}
        className={styles.detailImage}
        wrapperClassName={styles.detailImageWrapper}
      />
      <p className={styles.rowTime}>{formatShotTime(shot.time_created)}</p>
      {shot.my_appeal_reason ? (
        <p className={styles.rowSublabel}>
          You appealed: {reasonLabel(shot, shot.my_appeal_reason)}
        </p>
      ) : null}
      {confirming ? (
        <AppealConfirmation
          shot={shot}
          appealsRemaining={appealsRemaining}
          onDone={() => {
            setConfirming(false);
            onAppealed();
          }}
          onCancel={() => setConfirming(false)}
        />
      ) : appealButton.show ? (
        <button
          className={styles.appealButton}
          disabled={appealButton.disabled}
          onClick={() => setConfirming(true)}
        >
          {appealButton.label}
        </button>
      ) : null}
    </div>
  );
}

// The bubble: a thumbnail of the latest shot with its status in the corner.
// Once the user has taken a shot it stays put for the rest of the game,
// tracking that shot's status - it takes up little room, and a status that
// vanishes on its own is easy to miss. Tapping it opens the history on that
// shot.
function ShotNotifierBubble({ shotList }) {
  const latest = shotList && shotList.length > 0 ? shotList[0] : null;

  if (!latest) return null;

  const status = shotStatus(latest);

  return (
    <button
      className={statusClasses(status, styles.bubble)}
      onClick={() => openShotHistory(latest.id)}
    >
      <ShotThumbnail
        shotId={latest.id}
        className={styles.bubbleImage}
        wrapperClassName={styles.bubbleImageWrapper}
      />
      <StatusIcon status={status} className={styles.bubbleIcon} />
    </button>
  );
}

// Mount exactly one of these in the in-game view: it owns the shot list, the
// popup and the status bubble
export function ShotHistoryController() {
  const [shotList, setShotList] = useState(getShots());
  const [visible, setVisible] = useState(false);
  const [selectedShotId, setSelectedShotId] = useState(null);
  // The appeal budget rides the user payload, so it costs one fetch here
  // rather than an endpoint of its own. Null until it has arrived.
  const [appealsRemaining, setAppealsRemaining] = useState(null);

  const refreshAppeals = useCallback(() => {
    sendAPIRequest("user_info", null, "GET", (data) =>
      setAppealsRemaining(data.appeals_remaining),
    );
  }, []);

  const refreshEverything = useCallback(() => {
    refreshShots();
    refreshAppeals();
  }, [refreshAppeals]);

  useEffect(() => subscribeShots(setShotList), []);
  useEffect(refreshEverything, [refreshEverything]);

  useEffect(() => {
    const handler = (event) => {
      setSelectedShotId(event.detail.shotId);
      setVisible(true);
    };
    window.addEventListener(OPEN_EVENT, handler);
    return () => window.removeEventListener(OPEN_EVENT, handler);
  }, []);

  // Whatever is on show while the popup is open counts as seen
  useEffect(() => {
    if (visible && shotList) markShotsSeen(shotList);
  }, [visible, shotList]);

  const setVisibleAndReset = useCallback((newVisible) => {
    setVisible(newVisible);
    if (!newVisible) setSelectedShotId(null);
  }, []);

  const selectedShot =
    shotList && selectedShotId
      ? shotList.find((shot) => shot.id === selectedShotId)
      : null;

  return (
    <>
      {/* Refresh whenever the server nudges this user: new shots, shots fired
          at them, admin adjudications, appeal rulings and AI reviews all
          arrive as "user" updates */}
      <UpdateListener update_type="user" callback={refreshEverything} />
      <ShotNotifierBubble shotList={shotList} />
      <Popup visible={visible} setVisible={setVisibleAndReset}>
        {selectedShot ? (
          <ShotDetail
            shot={selectedShot}
            onBack={() => setSelectedShotId(null)}
            appealsRemaining={appealsRemaining}
            onAppealed={refreshEverything}
          />
        ) : (
          <div className={styles.list}>
            <h2 className={styles.listTitle}>My shots</h2>
            {(shotList || []).map((shot) => (
              <ShotRow
                key={shot.id}
                shot={shot}
                onClick={() => setSelectedShotId(shot.id)}
              />
            ))}
          </div>
        )}
      </Popup>
    </>
  );
}
