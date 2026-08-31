import {
  getGunImgFromUser,
  headingFromOrientationEvent,
  isLocationBypassActive,
  isOrientationPermissionGranted,
  makeAPIURL,
  requestOrientationPermission,
  sendAPIRequest,
  setAPIErrorHandler,
  setLocationBypass,
  watchCompassHeading,
} from "./utils";
import { installFetchMock, getLastAPICall } from "./testUtils";

// Import the same image files utils.js resolves getGunImgFromUser to, so we
// can compare against the real values rather than guessing at CRA's file
// mock output.
import gun_11 from "./images/art/gun_11.png";
import gun_06 from "./images/art/gun_06.svg";
import gun_16 from "./images/art/gun_default.png";
import gun_26 from "./images/art/gun_26.png";
import gun_36 from "./images/art/gun_36.png";

describe("makeAPIURL", () => {
  test("prefixes the endpoint with /api/", () => {
    const url = makeAPIURL("user_shots");
    expect(url.pathname).toBe("/api/user_shots");
  });

  test("appends query params", () => {
    const url = makeAPIURL("collect_item", { shot_id: "abc", n: 3 });
    expect(url.searchParams.get("shot_id")).toBe("abc");
    expect(url.searchParams.get("n")).toBe("3");
  });

  test("URL-encodes query param values", () => {
    const url = makeAPIURL("foo", { key: "a&b=c d" });
    // Decoded round-trip must recover the original value...
    expect(url.searchParams.get("key")).toBe("a&b=c d");
    // ...and the special characters must not appear literally in the URL.
    expect(url.toString()).not.toContain("a&b=c d");
    expect(url.toString()).toContain("a%26b%3Dc");
  });
});

describe("getGunImgFromUser", () => {
  test.each([
    [{ shot_damage: 0, shot_timeout: 6 }, gun_06],
    [{ shot_damage: 1, shot_timeout: 6 }, gun_16],
    [{ shot_damage: 2, shot_timeout: 6 }, gun_26],
    [{ shot_damage: 3, shot_timeout: 6 }, gun_36],
    [{ shot_damage: 1, shot_timeout: 1 }, gun_11],
  ])("returns the right image for %j", (user, expected) => {
    expect(getGunImgFromUser(user)).toBe(expected);
  });

  test("all five recognised combinations map to distinct images", () => {
    const images = [gun_06, gun_16, gun_26, gun_36, gun_11];
    expect(new Set(images).size).toBe(images.length);
  });

  test("returns null for an unrecognised damage/timeout combination", () => {
    expect(getGunImgFromUser({ shot_damage: 2, shot_timeout: 1 })).toBeNull();
  });
});

describe("sendAPIRequest", () => {
  afterEach(() => {
    setAPIErrorHandler(null);
  });

  test("GET requests carry no body", async () => {
    installFetchMock({ user_shots: [] });
    await sendAPIRequest("user_shots");
    expect(global.fetch).toHaveBeenCalledTimes(1);
    const [, options] = global.fetch.mock.calls[0];
    expect(options.method).toBe("GET");
    expect(options.body).toBeUndefined();
  });

  test("POST requests with a post_object send it as JSON", async () => {
    installFetchMock({ collect_item: { ok_field: true } });
    await sendAPIRequest("collect_item", {}, "POST", null, { data: "xyz" });

    const call = getLastAPICall("collect_item");
    expect(call.method).toBe("POST");
    expect(call.body).toEqual({ data: "xyz" });

    const [, options] = global.fetch.mock.calls[0];
    expect(options.headers["Content-Type"]).toBe("application/json");
    expect(JSON.parse(options.body)).toEqual({ data: "xyz" });
  });

  test("on success, the callback receives the parsed JSON body and the promise resolves with the raw response", async () => {
    installFetchMock({ user_shots: { hello: "world" } });
    const callback = jest.fn();

    const response = await sendAPIRequest("user_shots", null, "GET", callback);

    expect(callback).toHaveBeenCalledWith({ hello: "world" });
    expect(response.ok).toBe(true);
    expect(response.status).toBe(200);
  });

  test("on a non-2xx response, the callback is not called", async () => {
    installFetchMock({ user_shots: { status: 403, body: { error: "nope" } } });
    const callback = jest.fn();

    await sendAPIRequest("user_shots", null, "GET", callback);

    expect(callback).not.toHaveBeenCalled();
  });

  test("the error handler receives {endpoint, status, text} on a failed response", async () => {
    installFetchMock({
      user_shots: { status: 500, body: { error: "boom" } },
    });
    const handler = jest.fn();
    setAPIErrorHandler(handler);

    await sendAPIRequest("user_shots");

    expect(handler).toHaveBeenCalledTimes(1);
    const call = handler.mock.calls[0][0];
    expect(call.endpoint).toBe("user_shots");
    expect(call.status).toBe(500);
    expect(JSON.parse(call.text)).toEqual({ error: "boom" });
  });

  test("the error handler receives status: 'network' when fetch rejects, and the promise still rejects", async () => {
    global.fetch = jest.fn(() => Promise.reject(new Error("offline")));
    const handler = jest.fn();
    setAPIErrorHandler(handler);

    await expect(sendAPIRequest("user_shots")).rejects.toThrow("offline");

    expect(handler).toHaveBeenCalledWith(
      expect.objectContaining({ endpoint: "user_shots", status: "network" }),
    );
  });

  test("the caller can still read the response body after a failure (response.clone())", async () => {
    installFetchMock({
      user_shots: { status: 404, body: { error: "missing" } },
    });
    setAPIErrorHandler(jest.fn()); // failed responses are only cloned when a handler is registered

    const response = await sendAPIRequest("user_shots");

    expect(response.ok).toBe(false);
    await expect(response.json()).resolves.toEqual({ error: "missing" });
  });

  test("a failure with no error handler registered does not throw", async () => {
    installFetchMock({ user_shots: { status: 500, body: {} } });

    await expect(sendAPIRequest("user_shots")).resolves.toBeDefined();
  });
});

// ---------------------------------------------------------------------------
// The compass, recorded with every shot (docs/roadmap.md R5b). Everything here
// has to degrade to "no heading" rather than to an error: a phone that cannot
// answer must still be able to fire.
// ---------------------------------------------------------------------------

function orientationEvent(name, fields) {
  const event = new Event(name);
  Object.assign(event, fields);
  return event;
}

describe("headingFromOrientationEvent", () => {
  test("takes iOS's compass heading as-is", () => {
    expect(
      headingFromOrientationEvent({ webkitCompassHeading: 137.5, alpha: 12 }),
    ).toBeCloseTo(137.5, 6);
  });

  test("turns an absolute alpha (anticlockwise) into a clockwise heading", () => {
    // Alpha counts anticlockwise from north, so 90 degrees of alpha is west.
    expect(
      headingFromOrientationEvent({ absolute: true, alpha: 90 }),
    ).toBeCloseTo(270, 6);
    expect(
      headingFromOrientationEvent({ absolute: true, alpha: 0 }),
    ).toBeCloseTo(0, 6);
    expect(
      headingFromOrientationEvent({ absolute: true, alpha: 359 }),
    ).toBeCloseTo(1, 6);
  });

  test("ignores a non-absolute alpha, which is measured from nowhere in particular", () => {
    expect(headingFromOrientationEvent({ alpha: 90 })).toBeNull();
    expect(
      headingFromOrientationEvent({ absolute: false, alpha: 90 }),
    ).toBeNull();
  });

  test.each([
    ["no event at all", null],
    ["an event with nothing on it", {}],
    ["a null alpha", { absolute: true, alpha: null }],
    ["a NaN alpha", { absolute: true, alpha: NaN }],
  ])("reports no heading for %s", (_label, event) => {
    expect(headingFromOrientationEvent(event)).toBeNull();
  });
});

describe("watchCompassHeading", () => {
  test("reports headings while watching, and stops when told to", () => {
    const onHeading = jest.fn();
    const stop = watchCompassHeading(onHeading);

    window.dispatchEvent(
      orientationEvent("deviceorientation", { webkitCompassHeading: 90 }),
    );
    expect(onHeading).toHaveBeenCalledWith(90);

    stop();
    window.dispatchEvent(
      orientationEvent("deviceorientation", { webkitCompassHeading: 180 }),
    );
    expect(onHeading).toHaveBeenCalledTimes(1);
  });

  test("stays quiet for events that carry no usable heading", () => {
    const onHeading = jest.fn();
    const stop = watchCompassHeading(onHeading);

    window.dispatchEvent(orientationEvent("deviceorientation", { alpha: 90 }));

    expect(onHeading).not.toHaveBeenCalled();
    stop();
  });
});

describe("isOrientationPermissionGranted", () => {
  // jsdom has no DeviceOrientationEvent; every real browser does, and only
  // iOS puts a requestPermission() on it.
  beforeEach(() => {
    window.DeviceOrientationEvent = function DeviceOrientationEvent() {};
  });

  afterEach(() => {
    delete window.DeviceOrientationEvent;
    window.localStorage.clear();
  });

  test("is granted where nobody asks (everything except iOS)", async () => {
    await expect(isOrientationPermissionGranted()).resolves.toBe(true);
  });

  test("is not granted on a device with no orientation events at all", async () => {
    delete window.DeviceOrientationEvent;
    await expect(isOrientationPermissionGranted()).resolves.toBe(false);
    await expect(requestOrientationPermission()).resolves.toBe(false);
  });

  test("remembers an iOS grant, since there is no way to query it back", async () => {
    window.DeviceOrientationEvent.requestPermission = jest
      .fn()
      .mockResolvedValue("granted");

    await expect(isOrientationPermissionGranted()).resolves.toBe(false);
    await expect(requestOrientationPermission()).resolves.toBe(true);
    await expect(isOrientationPermissionGranted()).resolves.toBe(true);
  });

  test("a refusal is remembered as a refusal", async () => {
    window.DeviceOrientationEvent.requestPermission = jest
      .fn()
      .mockResolvedValue("denied");

    await expect(requestOrientationPermission()).resolves.toBe(false);
    await expect(isOrientationPermissionGranted()).resolves.toBe(false);
  });

  test("a request that throws is a refusal, not an explosion", async () => {
    window.DeviceOrientationEvent.requestPermission = jest
      .fn()
      .mockRejectedValue(new Error("must be called from a user gesture"));

    await expect(requestOrientationPermission()).resolves.toBe(false);
  });
});

describe("location bypass", () => {
  afterEach(() => {
    window.localStorage.clear();
  });

  test("is not active until set, and is remembered once it is", () => {
    expect(isLocationBypassActive()).toBe(false);
    setLocationBypass();
    expect(isLocationBypassActive()).toBe(true);
  });
});
