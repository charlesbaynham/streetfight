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
  return fetch(url, requestOptions).then(async (response) => {
    if (callback) {
      if (!response.ok) {
        console.log(`Error in api call to ${url}:`);
        console.dir(response);
        console.dir(response.json());
      } else {
        callback(await response.json());
      }
    }
    return response;
  });
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
