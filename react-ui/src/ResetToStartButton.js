import React, { useCallback, useEffect, useState } from "react";

import { adminPost } from "./AdminCommon";

import styles from "./ResetToStartButton.module.css";

// How long an armed button stays armed. Long enough to look at what it now
// says and mean it, short enough that a button left armed on a phone in a
// pocket has disarmed itself by the time it comes out again.
const ARMED_MS = 6000;

// The 16:00 button (M2.1). Two taps, because one tap deletes every shot and
// every scanned item in the game: the first arms it and makes it say what it
// is about to do, the second does it. The friction is the point - do not
// collapse this into one tap or into a window.confirm, which is dismissed
// without being read.
export default function ResetToStartButton({ game }) {
  const [armed, setArmed] = useState(false);
  const [result, setResult] = useState(null);

  // A refusal is the answer to "why did nothing happen?", so it is said
  // beside the button rather than only in the page's error log
  const paused = !game.active;

  useEffect(() => {
    if (!armed) return undefined;
    const timeout = setTimeout(() => setArmed(false), ARMED_MS);
    return () => clearTimeout(timeout);
  }, [armed]);

  const reset = useCallback(() => {
    setResult(null);
    adminPost("admin_reset_to_start_state", { game_id: game.id }).then(
      async (response) => {
        setArmed(false);
        if (response.ok) {
          setResult({ ok: true, text: "Reset. Everyone is at the start." });
          return;
        }
        const body = await response.json().catch(() => null);
        setResult({
          ok: false,
          text: (body && body.detail) || `Request failed (${response.status})`,
        });
      },
    );
  }, [game.id]);

  return (
    <>
      <p>
        <span
          className={
            styles.status +
            " " +
            (paused ? styles.statusGood : styles.statusBad)
          }
        >
          {paused ? "Game is paused" : "Game is running - pause it first"}
        </span>
      </p>

      <button
        className={styles.bigButton + (armed ? " " + styles.armed : "")}
        disabled={!paused}
        onClick={() => (armed ? reset() : setArmed(true))}
      >
        {armed
          ? "Tap again to wipe the sandbox"
          : "Reset everyone to the start state"}
      </button>

      <p>
        Sets everyone in this game - including players who have signed up but
        not yet scanned a team card - to no ammo, starting armour, the basic
        weapon and a full appeal budget, and deletes every shot, every scanned
        item, the ticker, the circles and any cued event. <b>Keeps</b> teams,
        outfits, reference photos, last known locations and team leaders. It
        refuses unless the game is paused.
      </p>

      {result ? (
        <p className={result.ok ? styles.resultGood : styles.resultBad}>
          {result.text}
        </p>
      ) : null}
    </>
  );
}
