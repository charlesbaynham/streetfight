import React, { useEffect, useState } from "react";

import { CountdownTimer } from "./GuideImages";
import prose from "./prose";

import styles from "./NextEventStrip.module.css";

// The wire values of Game.next_event_kind (backend/next_event.py).
export const KIND_CIRCLE = "circle";
export const KIND_DROP = "drop";

// What the game says is happening next, and how long is left: the three
// next_event_* fields off the player's own /user_info (backend/next_event.py),
// so the "user" SSE event every phone already listens to keeps it current and
// nothing here polls.
//
// Nothing is rendered at all when nothing is cued, which is most of the night:
// this sits above the bullet count and the map, and an empty strip would push
// them down the screen for no reason.
export default function NextEventStrip({ user }) {
  const deadline =
    user && typeof user.next_event_at === "number"
      ? user.next_event_at * 1000
      : null;
  const kind = user ? user.next_event_kind : null;

  // Has the countdown run out? One timeout rather than a second ticker beside
  // CountdownTimer's: this flips once and then waits for the server to clear
  // the cue, which arrives as an ordinary "user" update.
  const [elapsed, setElapsed] = useState(
    () => deadline !== null && deadline <= Date.now(),
  );

  useEffect(() => {
    if (deadline === null) return undefined;
    const remaining = deadline - Date.now();
    if (remaining <= 0) {
      setElapsed(true);
      return undefined;
    }
    setElapsed(false);
    const handle = setTimeout(() => setElapsed(true), remaining);
    return () => clearTimeout(handle);
  }, [deadline]);

  if (deadline === null) return null;

  const isDrop = kind === KIND_DROP;
  const isCircle = kind === KIND_CIRCLE;
  // A kind this bundle does not know about is not guessed at: an old tab open
  // through a deploy shows nothing rather than the wrong thing.
  if (!isDrop && !isCircle) return null;

  const label = isDrop
    ? prose.nextEvent.dropLabel
    : prose.nextEvent.circleLabel;
  const passed = isDrop ? prose.nextEvent.dropNow : prose.nextEvent.circleNow;

  return (
    <div
      className={
        styles.strip + " " + (isDrop ? styles.stripDrop : styles.stripCircle)
      }
      data-testid="next-event-strip"
    >
      {elapsed ? (
        <span className={styles.label}>{passed}</span>
      ) : (
        <>
          <span className={styles.label}>{label}</span>{" "}
          <span className={styles.clock}>
            <CountdownTimer deadline={deadline} />
          </span>
        </>
      )}
      {user.next_event_note ? (
        <span className={styles.note}>
          {" "}
          {prose.nextEvent.note(user.next_event_note)}
        </span>
      ) : null}
    </div>
  );
}
