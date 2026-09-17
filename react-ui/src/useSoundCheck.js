import { useCallback, useState } from "react";
import useSound from "use-sound";

import bang from "./bang.wav";

// The sound check on the onboarding screen: `[tested, test]`, where `test`
// plays a noise and `tested` is whether it has been pressed.
//
// It exists because a phone on silent is silent, and there is nothing the page
// can ask the browser to find that out - no permission, no API, no way to know
// the speaker did anything. The sound is how a player who is not looking at
// their screen learns they have been shot, so "we hope your sound is on" is not
// good enough and a sentence saying so would go unread. A tap that either makes
// a noise or doesn't is the whole test, and the player is the one running it.
//
// It is also the most useful tap in the app: it is a gesture, on a page that
// holds a sound object (see useAudioUnlock), which is exactly what the browser
// wants before it will let anything play later.
export default function useSoundCheck() {
  const [tested, setTested] = useState(false);
  const [play] = useSound(bang);

  const test = useCallback(() => {
    play();
    setTested(true);
  }, [play]);

  return [tested, test];
}
