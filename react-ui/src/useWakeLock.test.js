import React from "react";
import { render } from "@testing-library/react";

import useWakeLock from "./useWakeLock";
import { actAndFlush } from "./testUtils";

function Harness() {
  useWakeLock();
  return null;
}

function makeSentinel() {
  return { release: jest.fn(() => Promise.resolve()) };
}

function stubWakeLock(request) {
  Object.defineProperty(window.navigator, "wakeLock", {
    configurable: true,
    value: { request },
  });
}

function setVisibility(state) {
  Object.defineProperty(document, "visibilityState", {
    configurable: true,
    value: state,
  });
}

afterEach(() => {
  delete window.navigator.wakeLock;
});

test("requests a screen wake lock on mount", async () => {
  const sentinel = makeSentinel();
  const request = jest.fn(() => Promise.resolve(sentinel));
  stubWakeLock(request);

  await actAndFlush(() => render(<Harness />));

  expect(request).toHaveBeenCalledWith("screen");
  expect(request).toHaveBeenCalledTimes(1);
});

test("re-acquires the lock when the page becomes visible again", async () => {
  const sentinels = [makeSentinel(), makeSentinel()];
  let callCount = 0;
  const request = jest.fn(() => Promise.resolve(sentinels[callCount++]));
  stubWakeLock(request);

  await actAndFlush(() => render(<Harness />));
  expect(request).toHaveBeenCalledTimes(1);

  // The lock is auto-released by the browser when the page is hidden - going
  // hidden should not itself trigger a re-request.
  setVisibility("hidden");
  await actAndFlush(() =>
    document.dispatchEvent(new Event("visibilitychange")),
  );
  expect(request).toHaveBeenCalledTimes(1);

  setVisibility("visible");
  await actAndFlush(() =>
    document.dispatchEvent(new Event("visibilitychange")),
  );
  expect(request).toHaveBeenCalledTimes(2);
});

test("releases the sentinel on unmount", async () => {
  const sentinel = makeSentinel();
  const request = jest.fn(() => Promise.resolve(sentinel));
  stubWakeLock(request);

  const { unmount } = await actAndFlush(() => render(<Harness />));

  unmount();

  expect(sentinel.release).toHaveBeenCalledTimes(1);
});

test("does nothing when the Wake Lock API is unavailable", async () => {
  delete window.navigator.wakeLock;

  await expect(actAndFlush(() => render(<Harness />))).resolves.not.toThrow();
});
