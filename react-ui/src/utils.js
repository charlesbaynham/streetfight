import gun_11 from "./images/art/gun_11.png";
import gun_06 from "./images/art/gun_06.svg";
import gun_16 from "./images/art/gun_default.png";
import gun_26 from "./images/art/gun_26.png";
import gun_36 from "./images/art/gun_36.png";

// This is a workaround for Safari's lack of proper support for the Permissions
// API. I'll assume that permission is not granted until I've seen a successful
// geolocation request, then set this variable to true.
var geolocation_granted = false;
var webcam_granted = false;

export function makeAPIURL(endpoint, query_params = null) {
  const url = new URL(`/api/${endpoint}`, window.location.origin);

  if (query_params) {
    Object.keys(query_params).forEach((key) =>
      url.searchParams.append(key, query_params[key]),
    );
  }

  return url;
}

// If set, every failed API request (non-2xx response or network error) is
// reported here as {endpoint, status, text}. The admin pages register a
// handler that displays the failures; player pages leave it unset.
var apiErrorHandler = null;

export function setAPIErrorHandler(handler) {
  apiErrorHandler = handler;
}

export function sendAPIRequest(
  endpoint,
  query_params = null,
  method = "GET",
  callback = null,
  post_object = null,
) {
  const url = makeAPIURL(endpoint, query_params);

  var requestOptions;
  if (post_object !== null) {
    const query = JSON.stringify(post_object);

    requestOptions = {
      method: method,
      headers: { "Content-Type": "application/json" },
      body: query,
    };
  } else {
    requestOptions = {
      method: method,
      headers: { "Content-Type": "application/json" },
    };
  }

  // Callbacks are only called on success
  // To handle errors, use the returned promise which gives the raw response
  return fetch(url, requestOptions).then(
    async (response) => {
      if (!response.ok && apiErrorHandler) {
        let text = "";
        try {
          // Clone: the body can only be read once, and the caller may want it
          text = await response.clone().text();
        } catch (e) {}
        apiErrorHandler({ endpoint, status: response.status, text });
      }
      if (callback) {
        if (!response.ok) {
          console.log(`Error in api call to ${url}:`);
          console.dir(response);
        } else {
          callback(await response.json());
        }
      }
      return response;
    },
    (error) => {
      if (apiErrorHandler)
        apiErrorHandler({ endpoint, status: "network", text: String(error) });
      throw error;
    },
  );
}

export function getGunImgFromUser(user) {
  let image = null;

  if (user.shot_damage === 0 && user.shot_timeout === 6) image = gun_06;
  else if (user.shot_damage === 1 && user.shot_timeout === 6) image = gun_16;
  else if (user.shot_damage === 2 && user.shot_timeout === 6) image = gun_26;
  else if (user.shot_damage === 3 && user.shot_timeout === 6) image = gun_36;
  else if (user.shot_damage === 1 && user.shot_timeout === 1) image = gun_11;

  return image;
}

export async function isLocationPermissionGranted() {
  const result = await navigator.permissions.query({ name: "geolocation" });
  const from_permissions_api = result.state === "granted";

  // Allow override using flag so I can support sh*ty Safari
  return geolocation_granted || from_permissions_api;
}

export async function isCameraPermissionGranted() {
  const result = await navigator.permissions.query({ name: "camera" });
  return webcam_granted || result.state === "granted";
}

function getPosition() {
  return new Promise((resolve, reject) => {
    console.log("Requesting geolocation");
    return navigator.geolocation.getCurrentPosition(resolve, reject);
  });
}

export async function requestGeolocationPermission() {
  try {
    await getPosition();
    console.log("Geolocation permission granted");
    geolocation_granted = true;
    return true;
  } catch (err) {
    console.log("Geolocation permission denied", err);
    geolocation_granted = false;
    return false;
  }
}

// Some iPhones never show the location prompt at all - getCurrentPosition
// just hangs, so requestGeolocationPermission above neither resolves nor
// rejects and the player is stuck at the onboarding gate with no way through.
// Tapping the location button several times in a row lets them declare the
// bypass themselves. It's remembered in localStorage (rather than a plain
// variable, the same reasoning as ORIENTATION_GRANTED_KEY below) because the
// player may reload the page after tapping through.
const LOCATION_BYPASS_KEY = "streetfight_location_bypass";

export function isLocationBypassActive() {
  try {
    return window.localStorage.getItem(LOCATION_BYPASS_KEY) === "true";
  } catch {
    return false;
  }
}

export function setLocationBypass() {
  try {
    window.localStorage.setItem(LOCATION_BYPASS_KEY, "true");
  } catch {
    // Best effort - worst case they just have to tap through again later.
  }
}

// The device compass, used to record which way a shot was fired
// (docs/roadmap.md R5b). Everything here is best-effort: a phone with no
// compass, or a player who says no, simply has no heading recorded, and
// nothing in the game is allowed to depend on having one.

// iOS is the only platform that asks, and it gives no way to query the answer
// afterwards - so remember it, the same trick as geolocation_granted above.
// localStorage rather than a variable because the grant outlives the page.
const ORIENTATION_GRANTED_KEY = "streetfight_orientation_granted";

function orientationPermissionIsAsked() {
  return (
    typeof window !== "undefined" &&
    typeof window.DeviceOrientationEvent !== "undefined" &&
    typeof window.DeviceOrientationEvent.requestPermission === "function"
  );
}

export async function isOrientationPermissionGranted() {
  if (typeof window === "undefined" || !window.DeviceOrientationEvent)
    return false;

  // Nobody but iOS gates the orientation events, so there is nothing to grant.
  if (!orientationPermissionIsAsked()) return true;

  try {
    return window.localStorage.getItem(ORIENTATION_GRANTED_KEY) === "true";
  } catch (err) {
    return false;
  }
}

// Must be called from a user gesture on iOS, exactly like the camera.
export async function requestOrientationPermission() {
  if (typeof window === "undefined" || !window.DeviceOrientationEvent)
    return false;

  if (!orientationPermissionIsAsked()) return true;

  try {
    const result = await window.DeviceOrientationEvent.requestPermission();
    const granted = result === "granted";
    try {
      window.localStorage.setItem(ORIENTATION_GRANTED_KEY, String(granted));
    } catch (err) {}
    return granted;
  } catch (err) {
    console.log("Orientation permission request failed", err);
    return false;
  }
}

// The compass heading a DeviceOrientationEvent is reporting, in degrees
// clockwise from north, or null if it isn't reporting one.
//
// Two platforms, two answers: iOS puts a true compass heading on
// `webkitCompassHeading`, while everyone else gives `alpha`, which is measured
// anticlockwise from north and only means anything when the reading is
// absolute - plain `deviceorientation` on Android counts from wherever the
// device happened to start.
export function headingFromOrientationEvent(event) {
  if (!event) return null;

  const webkitHeading = event.webkitCompassHeading;
  if (typeof webkitHeading === "number" && !Number.isNaN(webkitHeading)) {
    return ((webkitHeading % 360) + 360) % 360;
  }

  if (event.absolute !== true) return null;
  if (typeof event.alpha !== "number" || Number.isNaN(event.alpha)) return null;

  return (((360 - event.alpha) % 360) + 360) % 360;
}

// Watch the compass, calling back with the heading whenever it reports one.
// Returns a function that stops the watch. A device that has no compass, or
// has not been given permission, simply never calls back.
export function watchCompassHeading(onHeading) {
  if (typeof window === "undefined" || !window.addEventListener)
    return () => {};

  // `deviceorientationabsolute` is the one that means anything on Android;
  // iOS doesn't have it, and reports its heading on the plain event.
  const eventName =
    "ondeviceorientationabsolute" in window
      ? "deviceorientationabsolute"
      : "deviceorientation";

  const handler = (event) => {
    const heading = headingFromOrientationEvent(event);
    if (heading !== null) onHeading(heading);
  };

  window.addEventListener(eventName, handler, true);
  return () => window.removeEventListener(eventName, handler, true);
}

export function requestWebcamAccess(callbackCompleted = null) {
  navigator.mediaDevices
    .getUserMedia({ video: true })
    .then((stream) => {
      stream.getTracks().forEach(function (track) {
        track.stop();
      });
    })
    .then(() => {
      webcam_granted = true;
      if (callbackCompleted) callbackCompleted();
    });
}
