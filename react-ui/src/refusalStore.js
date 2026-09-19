// The server's reason for turning something down, on its way to the player.
//
// Two things post from behind the camera and are nowhere near the screen
// furniture: `MyWebcam`, which fires a shot, and `QRParser`, which collects a
// scanned code. Both used to throw the reason away. A refused shot looked
// exactly like one that worked (docs/r9_walkthrough/A4.md); a refused scan was
// a full-screen flash of red that said something was wrong and nothing
// whatever about what - and the game has a dozen distinct reasons to refuse a
// card, from a withdrawn print run to a medpack scanned by somebody who is not
// knocked out. The refusal is published here and picked up by `RefusedNotice`
// in user mode.
//
// A callback threaded down through `WebcamView` would work too, but the
// admin's reference-photo page mounts the same camera and has no business
// showing a player's fire-cooldown message.
//
// Callers publish the finished sentence rather than a bare reason: the frame
// around it differs by what was refused ("Shot not taken", "Not collected"),
// and every word a player reads belongs in prose.js.

let refusal = null;
const subscribers = new Set();

function notify() {
  subscribers.forEach((callback) => callback(refusal));
}

export function subscribeRefusal(callback) {
  subscribers.add(callback);
  return () => subscribers.delete(callback);
}

export function getRefusal() {
  return refusal;
}

// `id` is what makes a second identical refusal a new one to look at: the
// player taps too early twice, or holds the phone at the same dead poster, and
// both have to be answered even though the message is the same.
let nextId = 0;

export function reportRefusal(message) {
  refusal = { id: ++nextId, message };
  notify();
}

export function clearRefusal() {
  if (refusal === null) return;
  refusal = null;
  notify();
}
