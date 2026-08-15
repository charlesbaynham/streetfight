import { sendAPIRequest } from "./utils";

const CACHE_VERSION = 1;
const CURRENT_CACHES = {
  shots: `shot-cache-v${CACHE_VERSION}`,
};

window.addEventListener("activate", (event) => {
  // Delete all caches that aren't named in CURRENT_CACHES.
  // While there is only one cache in this example, the same logic
  // will handle the case where there are multiple versioned caches.
  const expectedCacheNamesSet = new Set(Object.values(CURRENT_CACHES));
  event.waitUntil(
    caches.keys().then((cacheNames) =>
      Promise.all(
        cacheNames.map((cacheName) => {
          if (!expectedCacheNamesSet.has(cacheName)) {
            // If this cache name isn't present in the set of
            // "expected" cache names, then delete it.
            console.log("Deleting out of date cache:", cacheName);
            return caches.delete(cacheName);
          }
          return null;
        }),
      ),
    ),
  );
});

// Shots already being fetched, by id. The queue asks for the same shot from
// several places at once (the pre-load loop and the panel showing it), and a
// shot is megabytes: without this they each miss the still-empty cache and
// start their own download of the same photo.
const inFlight = new Map();

async function fetchAndCache(cache, shot_id) {
  console.log("Shot not in cache, fetching from API");
  const apiResponse = await sendAPIRequest("admin_get_shot", {
    shot_id: shot_id,
  });
  if (!apiResponse.ok) {
    throw new Error(`Error fetching shot: ${apiResponse.statusText}`);
  }

  // Cache the fetched response for future use
  await cache.put(shot_id, apiResponse.clone());

  return apiResponse.json();
}

export async function getShotFromCache(shot_id) {
  console.log("getShotFromCache", shot_id);

  if (!shot_id) {
    return null;
  }

  const cache = await caches.open(CURRENT_CACHES.shots);
  const response = await cache.match(shot_id);
  if (response) {
    console.log("Shot found in cache, returning");
    return response.json();
  }

  const pending = inFlight.get(shot_id);
  if (pending) {
    console.log("Shot already being fetched, joining that request");
    return pending;
  }

  const request = fetchAndCache(cache, shot_id).finally(() => {
    inFlight.delete(shot_id);
  });
  inFlight.set(shot_id, request);
  return request;
}
