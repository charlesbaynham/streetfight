// The server's reason for turning a shot down, on its way to the player.
//
// `MyWebcam` posts the photograph and is nowhere near the screen furniture, so
// the refusal is published here and picked up by `ShotRefusedNotice` in user
// mode - the same shape as `shotHistoryStore`, which `MyWebcam` already talks
// to. A callback threaded down through `WebcamView` would work too, but the
// admin's reference-photo page mounts the same camera and has no business
// showing a player's fire-cooldown message.
//
// Before this, `MyWebcam` read the response body and threw the status away, so
// a 403 looked exactly like a shot that worked (docs/r9_walkthrough/A4.md).

let refusal = null;
const subscribers = new Set();

function notify() {
  subscribers.forEach((callback) => callback(refusal));
}

export function subscribeShotRefusal(callback) {
  subscribers.add(callback);
  return () => subscribers.delete(callback);
}

export function getShotRefusal() {
  return refusal;
}

// `id` is what makes a second identical refusal a new one to look at: the
// player taps too early twice and both taps have to be answered, even though
// the message is the same.
let nextId = 0;

export function reportShotRefusal(message) {
  refusal = { id: ++nextId, message };
  notify();
}

export function clearShotRefusal() {
  if (refusal === null) return;
  refusal = null;
  notify();
}
