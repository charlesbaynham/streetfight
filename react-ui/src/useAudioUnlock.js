import useSound from "use-sound";

import bang from "./bang.wav";

// Make sure the browser's audio is unlocked by the time the game needs it.
//
// Mobile browsers refuse to play anything until the page has had a user
// gesture, and Howler (under use-sound) handles that for us: the first Howl
// constructed installs document-level touchstart/click listeners that unlock
// the audio context on the next tap. The catch is the ordering - those
// listeners are installed by *constructing a sound*, so a page with no sound
// object on it yet gets no unlock from the taps it receives.
//
// That is exactly the shape of user mode. Every other useSound in the app
// lives in a component that is only mounted once the game is running and the
// permissions are granted - FireButton, ShotHistoryController,
// ShotReceivedOverlay - so the taps a player spends on the onboarding screen
// granting camera and location, which are often the only taps they make all
// evening, unlocked nothing. The first sound they were ever going to hear was
// "you have been shot", by which time the phone is in a pocket and there is no
// gesture coming.
//
// So: hold one sound object from the moment user mode mounts, onboarding
// included. It is not for playing - nothing here ever calls it - it is for
// existing, so that Howler's unlock is armed before the first tap rather than
// after it. bang.wav because it is the smallest of them.
//
// Nothing needs to be done about the audio context being suspended later (iOS
// does that whenever the page is backgrounded, which in this game is most of
// the time): Howl.play() calls Howler._autoResume() itself.
export default function useAudioUnlock() {
  useSound(bang);
}
