import { useEffect, useRef } from "react";
import useSound from "use-sound";

import knockedOutSound from "./knocked_out.wav";

const KNOCKED_OUT = "knocked out";

// The sound of your own power going off, the moment you are knocked out.
//
// Seeded silently, the discipline ShotHistory's useShotOutcomeSounds follows:
// the first state this hook is handed is recorded and not played, so a player
// who reloads the page while knocked out - or leaves the tab and comes back -
// hears nothing. Only a transition into it plays, and only from another state,
// so a "user" update that changes something else does not re-fire it.
//
// It does not vibrate. ShotReceivedOverlay is buzzing its own pattern at this
// same instant and navigator.vibrate replaces whatever is running rather than
// queueing behind it, so a second call here would cut that one short.
//
// Note it plays on "knocked out" alone and not on "dead". A player is always
// knocked out first, for ten minutes; the only way to see the jump straight to
// dead is to have had the page backgrounded through the whole of it, and a
// power-down ten minutes after the fact is worse than silence.
export default function useKnockedOutSound(user) {
  const state = user ? user.state : null;
  const [playKnockedOut] = useSound(knockedOutSound);
  const seen = useRef(null);

  useEffect(() => {
    if (!state) return;

    const previous = seen.current;
    seen.current = state;

    // The first state we have ever seen is the seed, whatever it is
    if (previous === null) return;

    if (state === KNOCKED_OUT && previous !== KNOCKED_OUT) playKnockedOut();
  }, [state, playKnockedOut]);
}
