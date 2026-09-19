// What the server said when it turned something down, put in front of the
// player: a shot it would not take, or a code it would not collect.
//
// Deliberately not a dialogue: the player is holding the phone up at somebody,
// or at a card on a wall, and the answer is usually short. It sits above the
// fire button, says the reason, and goes away on its own. It can be tapped
// away early, and a fresh refusal replaces the one on screen rather than
// queueing behind it - only the newest thing the player did matters.
//
// The sentence is built by whoever reports the refusal (see refusalStore.js),
// so this component chooses nothing and renders what it is given.

import { useEffect, useState } from "react";

import prose from "./prose";
import styles from "./RefusedNotice.module.css";
import { clearRefusal, getRefusal, subscribeRefusal } from "./refusalStore";

export const VISIBLE_FOR_MS = 4000;

export default function RefusedNotice() {
  const [refusal, setRefusal] = useState(getRefusal);

  useEffect(() => subscribeRefusal(setRefusal), []);

  // Keyed on the refusal's id, not on the message: two identical refusals are
  // two things the player did, and the second has to restart the countdown.
  const refusalId = refusal ? refusal.id : null;
  useEffect(() => {
    if (refusalId === null) return;
    const timer = setTimeout(clearRefusal, VISIBLE_FOR_MS);
    return () => clearTimeout(timer);
  }, [refusalId]);

  if (!refusal) return null;

  return (
    <button
      type="button"
      className={styles.notice}
      onClick={clearRefusal}
      aria-label={prose.refusedNotice.dismiss}
    >
      {refusal.message}
    </button>
  );
}
