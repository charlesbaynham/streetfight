// A full-screen, must-dismiss overlay telling the player they've just been
// shot. Today a hit just silently drops a hit point; this makes it
// unmissable - the moment it matters is the only one a player who isn't
// staring at the screen (most of the game) would otherwise never see.

import React, { useEffect, useReducer, useState } from "react";

import { motion, useReducedMotion } from "framer-motion";
import useSound from "use-sound";

import { openShotHistory } from "./ShotHistory";
import {
  acknowledgeHit,
  getShotImage,
  getShots,
  subscribeShots,
  unacknowledgedHits,
} from "./shotHistoryStore";
import Modernizr from "./modernizr";
import hitSound from "./hit_received.wav";

import styles from "./ShotReceivedOverlay.module.css";

function outcomeText(user) {
  if (!user) return "";
  if (user.state === "knocked out") return "You are knocked out";
  if (user.state === "dead") return "You are dead";
  const points = user.hit_points;
  return `${points} hit point${points === 1 ? "" : "s"} left`;
}

export default function ShotReceivedOverlay({ user }) {
  const [shotList, setShotList] = useState(getShots());
  const [image, setImage] = useState(null);
  // acknowledgeHit doesn't change the store's shots array (it only touches
  // localStorage), so notify() re-delivers the very same reference and a
  // plain setShotList(shots) would bail out of re-rendering (see the
  // sibling-badge bug noted in ShotHistory.test.js). Bumping this on every
  // dismissal forces a re-render so unacknowledgedHits is re-read fresh.
  const [, forceRecompute] = useReducer((n) => n + 1, 0);

  useEffect(() => subscribeShots(setShotList), []);

  const shot = unacknowledgedHits(shotList)[0] || null;
  const shotId = shot ? shot.id : null;

  useEffect(() => {
    if (!shotId) {
      setImage(null);
      return undefined;
    }
    let cancelled = false;
    getShotImage(shotId).then((img) => {
      if (!cancelled) setImage(img);
    });
    return () => {
      cancelled = true;
    };
  }, [shotId]);

  const [playHit] = useSound(hitSound);

  // Once per shot shown: keyed on the shot's own id, not on shotList or
  // visibility, so a re-render that leaves the same shot on screen (a
  // sibling shot's status changing, say) doesn't ding and buzz again.
  useEffect(() => {
    if (!shotId) return;
    playHit();
    if (Modernizr.vibrate) navigator.vibrate([200, 100, 200, 100, 400]);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [shotId]);

  const prefersReducedMotion = useReducedMotion();

  if (!shot) return null;

  const dismiss = () => {
    acknowledgeHit(shotList, shot.id);
    forceRecompute();
  };

  return (
    <motion.div
      className={styles.overlay}
      initial={{ opacity: 0, scale: prefersReducedMotion ? 1 : 0.92 }}
      animate={{ opacity: 1, scale: 1 }}
      transition={{ duration: prefersReducedMotion ? 0 : 0.3 }}
    >
      <h1 className={styles.headline}>You have been shot</h1>
      {shot.shooter_name ? (
        <p className={styles.shooter}>by {shot.shooter_name}</p>
      ) : null}
      {image ? (
        <img className={styles.image} src={image} alt="The shot that hit you" />
      ) : (
        <div className={styles.imagePlaceholder} />
      )}
      <p className={styles.outcome}>{outcomeText(user)}</p>
      <button className={styles.okButton} onClick={dismiss}>
        OK
      </button>
      <button
        className={styles.appealButton}
        onClick={() => {
          dismiss();
          openShotHistory(shot.id);
        }}
      >
        Appeal this shot
      </button>
    </motion.div>
  );
}
