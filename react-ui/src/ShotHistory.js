// The user-facing shot history: a "My shots" entry for the HUD (with an
// unseen-changes badge), a fullscreen popup listing every shot with its
// adjudicated outcome, and a bubble in the corner showing the latest shot's
// status.

import React, { useCallback, useEffect, useState } from "react";

import Popup from "./Popup";
import UpdateListener from "./UpdateListener";
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
  refunded: styles.stateRefunded,
};

// What to show for a shot's current status. Shots checked before the result
// column existed have result=null: infer from whether a target was recorded.
export function shotStatus(shot) {
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
    return { state: "miss", icon: crossImg, label: "Missed" };
  }

  // The AI has looked but the call is still the referee's: distinct icon and
  // colour from a shot nobody has looked at yet
  if (shot.ai_review_state === "done" && shot.ai_suggestion)
    return {
      state: "escalated",
      emoji: "🤖",
      label: `AI thinks: ${shot.ai_suggestion}`,
      sublabel: "Escalated to referee",
    };

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
    <button className={styles.shotRow} onClick={onClick}>
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

function ShotDetail({ shot, onBack }) {
  const status = shotStatus(shot);

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

  useEffect(() => subscribeShots(setShotList), []);
  useEffect(() => {
    refreshShots();
  }, []);

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
      {/* Refresh whenever the server nudges this user: new shots, admin
          adjudications and AI reviews all arrive as "user" updates */}
      <UpdateListener update_type="user" callback={refreshShots} />
      <ShotNotifierBubble shotList={shotList} />
      <Popup visible={visible} setVisible={setVisibleAndReset}>
        {selectedShot ? (
          <ShotDetail
            shot={selectedShot}
            onBack={() => setSelectedShotId(null)}
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
