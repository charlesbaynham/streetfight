import React from "react";
import { render, act } from "@testing-library/react";

import useWakeLock from "./useWakeLock";
import { actAndFlush } from "./testUtils";

function Harness() {
  const awake = useWakeLock();
  return <span data-testid="state">{String(awake)}</span>;
}

// A stand-in for the browser's WakeLockSentinel, including the two ways it
// tells you the lock has gone: the "release" event, and the `released` flag
// changing under you with no event at all (what iOS does).
function makeSentinel() {
  const listeners = [];
  const sentinel = {
    released: false,
    release: jest.fn(() => {
      sentinel.released = true;
      return Promise.resolve();
    }),
    addEventListener: (type, fn) => {
      if (type === "release") listeners.push(fn);
    },
    removeEventListener: () => {},
    fireRelease: () => {
      sentinel.released = true;
      listeners.forEach((fn) => fn());
    },
  };
  return sentinel;
}

function stubWakeLock(request) {
  Object.defineProperty(window.navigator, "wakeLock", {
    configurable: true,
    value: { request },
  });
}

// Hands out a fresh sentinel per call, and records them for the test.
function stubGrantingWakeLock() {
  const sentinels = [];
  const request = jest.fn(() => {
    const sentinel = makeSentinel();
    sentinels.push(sentinel);
    return Promise.resolve(sentinel);
  });
  stubWakeLock(request);
  return { request, sentinels };
}

function setVisibility(state) {
  Object.defineProperty(document, "visibilityState", {
    configurable: true,
    value: state,
  });
}

afterEach(() => {
  delete window.navigator.wakeLock;
  setVisibility("visible");
});

test("requests a screen wake lock on mount", async () => {
  const { request } = stubGrantingWakeLock();

  const { getByTestId } = await actAndFlush(() => render(<Harness />));

  expect(request).toHaveBeenCalledWith("screen");
  expect(request).toHaveBeenCalledTimes(1);
  expect(getByTestId("state")).toHaveTextContent("true");
});

test("re-acquires the lock when the page becomes visible again", async () => {
  const { request } = stubGrantingWakeLock();

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

// The case the spectator iPad actually hits: nothing about the page changed,
// but the browser took the lock back and said so.
test("re-acquires when the browser releases the lock on its own", async () => {
  const { request, sentinels } = stubGrantingWakeLock();

  const { getByTestId } = await actAndFlush(() => render(<Harness />));

  await act(async () => {
    sentinels[0].fireRelease();
    for (let i = 0; i < 8; i++) await Promise.resolve();
  });

  expect(request).toHaveBeenCalledTimes(2);
  expect(getByTestId("state")).toHaveTextContent("true");
});

// Entering or leaving full screen is one of the moments iOS drops the lock
// without firing anything at the sentinel.
test.each(["fullscreenchange", "webkitfullscreenchange"])(
  "re-acquires a silently dropped lock on %s",
  async (eventName) => {
    const { request, sentinels } = stubGrantingWakeLock();

    await actAndFlush(() => render(<Harness />));
    sentinels[0].released = true;

    await actAndFlush(() => document.dispatchEvent(new Event(eventName)));

    expect(request).toHaveBeenCalledTimes(2);
  },
);

test("keeps trying after a refused request", async () => {
  jest.useFakeTimers();
  try {
    let grant = false;
    const sentinel = makeSentinel();
    // Refused the first time (a tablet in low power mode, say), granted once
    // it is plugged in. Nobody is watching the screen to retry by hand.
    const request = jest.fn(() =>
      grant ? Promise.resolve(sentinel) : Promise.reject(new Error("denied")),
    );
    stubWakeLock(request);

    let view;
    await act(async () => {
      view = render(<Harness />);
      for (let i = 0; i < 8; i++) await Promise.resolve();
    });
    expect(request).toHaveBeenCalledTimes(1);
    expect(view.getByTestId("state")).toHaveTextContent("false");

    grant = true;
    await act(async () => {
      jest.advanceTimersByTime(60000);
      for (let i = 0; i < 8; i++) await Promise.resolve();
    });

    expect(request.mock.calls.length).toBeGreaterThan(1);
    expect(view.getByTestId("state")).toHaveTextContent("true");
  } finally {
    jest.useRealTimers();
  }
});

test("releases the sentinel on unmount", async () => {
  const { sentinels } = stubGrantingWakeLock();

  const { unmount } = await actAndFlush(() => render(<Harness />));

  unmount();

  expect(sentinels[0].release).toHaveBeenCalledTimes(1);
});

test("reports that the screen is not held when the API is unavailable", async () => {
  delete window.navigator.wakeLock;

  const { getByTestId } = await actAndFlush(() => render(<Harness />));

  expect(getByTestId("state")).toHaveTextContent("false");
});
