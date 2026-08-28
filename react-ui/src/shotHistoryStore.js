// Shared client-side store for the user's own shot history.
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

export function refreshShots() {
  return sendAPIRequest("user_shots").then(async (response) => {
    if (!response.ok) return;
    shots = await response.json();
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
