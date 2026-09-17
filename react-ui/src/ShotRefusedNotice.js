// What the server said when it turned a shot down, put in front of the player.
//
// Deliberately not a dialogue: the player is holding the phone up at somebody
// and the answer is nearly always "wait a moment", so it sits above the fire
// button, says the reason, and goes away on its own. It can be tapped away
// early, and a fresh refusal replaces the one on screen rather than queueing
// behind it - only the newest tap matters.

import { useEffect, useState } from "react";

import prose from "./prose";
import styles from "./ShotRefusedNotice.module.css";
import {
  clearShotRefusal,
  getShotRefusal,
  subscribeShotRefusal,
} from "./shotRefusalStore";

export const VISIBLE_FOR_MS = 4000;

export default function ShotRefusedNotice() {
  const [refusal, setRefusal] = useState(getShotRefusal);

  useEffect(() => subscribeShotRefusal(setRefusal), []);

  // Keyed on the refusal's id, not on the message: two identical refusals are
  // two taps the player made, and the second has to restart the countdown.
  const refusalId = refusal ? refusal.id : null;
  useEffect(() => {
    if (refusalId === null) return;
    const timer = setTimeout(clearShotRefusal, VISIBLE_FOR_MS);
    return () => clearTimeout(timer);
  }, [refusalId]);

  if (!refusal) return null;

  return (
    <button
      type="button"
      className={styles.notice}
      onClick={clearShotRefusal}
      aria-label={prose.fireButton.dismissRefusal}
    >
      {refusal.message
        ? prose.fireButton.shotRefused(refusal.message)
        : prose.fireButton.shotRefusedUnknown}
    </button>
  );
}
