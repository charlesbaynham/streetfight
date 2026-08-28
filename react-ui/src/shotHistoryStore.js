// Shared client-side store for the user's own shot history: both the shots
// they fired and the shots ruled to have hit them (roadmap R8), merged into
// one newest-first list and tagged with which side of the shot they were on.
//
// One fetch feeds every component that cares (the HUD entry's badge, the
// history popup, the status bubble), and localStorage remembers which shot
// statuses the user has already looked at so "unseen" survives reloads.

import { sendAPIRequest } from "./utils";

let shots = null;
const subscribers = new Set();

const SEEN_STORAGE_KEY = "seenShotStatuses";

function notify() {
  subscribers.forEach((callback) => callback(shots));
}

// Subscribe to shot list changes; returns a deregistration function. The
// callback also fires on markShotsSeen, since "unseen" counts depend on both
// the list and the seen map.
export function subscribeShots(callback) {
  subscribers.add(callback);
  return () => subscribers.delete(callback);
}

export function getShots() {
  return shots;
}

// One list of shots, each entry tagged with the direction it points in, or
// null if that half could not be fetched
function fetchShotList(endpoint, direction) {
  return sendAPIRequest(endpoint).then(async (response) => {
    if (!response.ok) return null;
    const list = await response.json();
    return list.map((shot) => ({ ...shot, direction }));
  });
}

// Both halves in parallel, merged newest-first. Ids are unique across the two
// (they are the same Shot table), so seen-tracking and lookups by id work on
// the merged list exactly as they did on the fired one. A half that fails
// contributes nothing rather than blanking the other one; only a total
// failure leaves the stored list alone.
export function refreshShots() {
  return Promise.all([
    fetchShotList("user_shots", "fired"),
    fetchShotList("user_shots_received", "received"),
  ]).then((lists) => {
    const fetched = lists.filter((list) => list !== null);
    if (fetched.length === 0) return;
    shots = fetched
      .flat()
      .sort(
        (a, b) =>
          new Date(b.time_created).getTime() -
          new Date(a.time_created).getTime(),
      );
    notify();
  });
}

// A shot's user-visible status as a comparable string: when this changes, the
// user has something new to look at
function shotStatusFingerprint(shot) {
  return [
    shot.id,
    shot.checked,
    shot.result,
    shot.ai_review_state === "done" ? shot.ai_suggestion : null,
    shot.ai_target_name,
    // An appeal being lodged or ruled on is news to both parties
    shot.appeal_state,
  ].join("|");
}

function loadSeenMap() {
  try {
    return JSON.parse(localStorage.getItem(SEEN_STORAGE_KEY)) || {};
  } catch (e) {
    return {};
  }
}

function isShotStatusSeen(shot) {
  return loadSeenMap()[shot.id] === shotStatusFingerprint(shot);
}

export function countUnseenShots(shotList) {
  if (!shotList) return 0;
  return shotList.filter((shot) => !isShotStatusSeen(shot)).length;
}

// Record every current status as seen (the user has the history open)
export function markShotsSeen(shotList) {
  if (!shotList || shotList.length === 0) return;
  const seen = {};
  shotList.forEach((shot) => {
    seen[shot.id] = shotStatusFingerprint(shot);
  });
  localStorage.setItem(SEEN_STORAGE_KEY, JSON.stringify(seen));
  notify();
}

// Shot images are immutable, so fetch each at most once per page load
const imagePromises = new Map();

export function getShotImage(shotId) {
  if (!imagePromises.has(shotId)) {
    imagePromises.set(
      shotId,
      sendAPIRequest("user_shot_image", { shot_id: shotId }).then((response) =>
        response.ok ? response.json().then((data) => data.image_base64) : null,
      ),
    );
  }
  return imagePromises.get(shotId);
}
