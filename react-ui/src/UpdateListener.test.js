import { act, render } from "@testing-library/react";
import UpdateListener, {
  UpdateSSEConnection,
  registerListener,
  deregisterListener,
} from "./UpdateListener";
import {
  getEventSources,
  emitUpdate,
  emitKeepalive,
  emitError,
} from "./testUtils";

// Mirrors the (unexported) constants at the top of UpdateListener.js, so the
// timer assertions below have a clear rationale.
const KEEPALIVE_TIMEOUT_MS = 20000;
const TIMEOUT_ON_ERROR_MS = 3000;

// registerListener/deregisterListener manage a single module-scoped map, and
// processUpdateMessage (which dispatches to it) is only reachable through a
// mounted UpdateSSEConnection's message handler - so every test in this file
// mounts one to drive dispatch.

describe("listener registry", () => {
  test("an update of one type only fires callbacks registered for that type", () => {
    render(<UpdateSSEConnection />);
    const userCallback = jest.fn();
    const tickerCallback = jest.fn();
    const userHandle = registerListener("user", userCallback);
    const tickerHandle = registerListener("ticker", tickerCallback);

    act(() => emitUpdate("user"));

    expect(userCallback).toHaveBeenCalledTimes(1);
    expect(tickerCallback).not.toHaveBeenCalled();

    deregisterListener("user", userHandle);
    deregisterListener("ticker", tickerHandle);
  });

  test("multiple listeners registered on the same type all fire", () => {
    render(<UpdateSSEConnection />);
    const callback1 = jest.fn();
    const callback2 = jest.fn();
    const handle1 = registerListener("ticker", callback1);
    const handle2 = registerListener("ticker", callback2);

    act(() => emitUpdate("ticker"));

    expect(callback1).toHaveBeenCalledTimes(1);
    expect(callback2).toHaveBeenCalledTimes(1);

    deregisterListener("ticker", handle1);
    deregisterListener("ticker", handle2);
  });

  test("a deregistered handle stops receiving updates", () => {
    render(<UpdateSSEConnection />);
    const callback = jest.fn();
    const handle = registerListener("admin", callback);

    act(() => emitUpdate("admin"));
    expect(callback).toHaveBeenCalledTimes(1);

    deregisterListener("admin", handle);

    act(() => emitUpdate("admin"));
    expect(callback).toHaveBeenCalledTimes(1); // still just the one call
  });

  test("an update for a type with no listeners is a no-op", () => {
    render(<UpdateSSEConnection />);
    expect(() => act(() => emitUpdate("nobody-listens-here"))).not.toThrow();
  });
});

describe("UpdateListener component", () => {
  test("registers its callback on mount and deregisters on unmount", () => {
    render(<UpdateSSEConnection />);
    const callback = jest.fn();
    const { unmount } = render(
      <UpdateListener update_type="shots" callback={callback} />,
    );

    act(() => emitUpdate("shots"));
    expect(callback).toHaveBeenCalledTimes(1);

    unmount();

    act(() => emitUpdate("shots"));
    expect(callback).toHaveBeenCalledTimes(1); // no further calls post-unmount
  });

  // The effect has no dependency array, so it re-registers on every render
  // (deregistering the old handle first). This confirms that doesn't leave
  // stale listeners firing alongside the current one.
  test("re-rendering with a new callback swaps to it without double-firing", () => {
    render(<UpdateSSEConnection />);
    const callback1 = jest.fn();
    const callback2 = jest.fn();
    const { rerender } = render(
      <UpdateListener update_type="ticker" callback={callback1} />,
    );

    rerender(<UpdateListener update_type="ticker" callback={callback2} />);

    act(() => emitUpdate("ticker"));

    expect(callback1).not.toHaveBeenCalled();
    expect(callback2).toHaveBeenCalledTimes(1);
  });
});

describe("UpdateSSEConnection", () => {
  test("mounting opens an EventSource pointed at /api/sse_updates by default", () => {
    render(<UpdateSSEConnection />);

    const sources = getEventSources();
    expect(sources).toHaveLength(1);
    expect(sources[0].url).toContain("/api/sse_updates");
  });

  test("honours a custom endpoint prop (e.g. AdminCommon's sse_admin_updates)", () => {
    render(<UpdateSSEConnection endpoint="sse_admin_updates" />);

    const sources = getEventSources();
    expect(sources).toHaveLength(1);
    expect(sources[0].url).toContain("/api/sse_admin_updates");
  });

  test("an update_prompt message dispatches to the matching registered listener", () => {
    render(<UpdateSSEConnection />);
    const callback = jest.fn();
    const handle = registerListener("circle", callback);

    act(() => emitUpdate("circle"));

    expect(callback).toHaveBeenCalledTimes(1);
    deregisterListener("circle", handle);
  });

  test("a keepalive count following the previous one does not restart the stream", () => {
    render(<UpdateSSEConnection />);

    act(() => emitKeepalive(1));
    act(() => emitKeepalive(2));
    act(() => emitKeepalive(3));

    const sources = getEventSources();
    expect(sources).toHaveLength(1);
    expect(sources[0].readyState).not.toBe(2); // not closed
  });

  test("the first keepalive received is accepted whatever its value", () => {
    render(<UpdateSSEConnection />);

    // The stream's keepalive counter starts as null, so an arbitrary first
    // value (not 0 or 1) must be accepted rather than treated as a desync.
    act(() => emitKeepalive(42));
    expect(getEventSources()).toHaveLength(1);

    act(() => emitKeepalive(43));
    expect(getEventSources()).toHaveLength(1);
  });

  test("a keepalive count that skips closes the current stream and opens a new one", () => {
    render(<UpdateSSEConnection />);
    const first = getEventSources()[0];

    act(() => emitKeepalive(1));
    act(() => emitKeepalive(5)); // desync: jumped from 1 to 5

    const sources = getEventSources();
    expect(sources).toHaveLength(2);
    expect(first.readyState).toBe(2); // closed
    expect(sources[1]).not.toBe(first);
  });

  describe("timer-driven reconnects", () => {
    beforeEach(() => {
      jest.useFakeTimers();
    });

    afterEach(() => {
      jest.useRealTimers();
    });

    test("no messages for longer than the keepalive timeout restarts the stream", () => {
      render(<UpdateSSEConnection />);
      expect(getEventSources()).toHaveLength(1);

      act(() => {
        jest.advanceTimersByTime(KEEPALIVE_TIMEOUT_MS + 1000);
      });

      const sources = getEventSources();
      expect(sources).toHaveLength(2);
      expect(sources[0].readyState).toBe(2); // closed
    });

    test("any message received resets the timeout, so steady traffic is not restarted", () => {
      render(<UpdateSSEConnection />);

      act(() => {
        jest.advanceTimersByTime(15000);
      });
      act(() => emitKeepalive(1)); // resets the last-message timestamp

      act(() => {
        // 30s have now passed since mount, but only 15s since the message.
        jest.advanceTimersByTime(15000);
      });

      expect(getEventSources()).toHaveLength(1);
    });

    test("onerror schedules a reconnect after the retry timeout rather than immediately", () => {
      render(<UpdateSSEConnection />);
      const first = getEventSources()[0];

      act(() => emitError());

      expect(getEventSources()).toHaveLength(1); // not reconnected yet

      act(() => {
        jest.advanceTimersByTime(TIMEOUT_ON_ERROR_MS - 1);
      });
      expect(getEventSources()).toHaveLength(1);

      act(() => {
        jest.advanceTimersByTime(1);
      });
      const sources = getEventSources();
      expect(sources).toHaveLength(2);
      expect(first.readyState).toBe(2);
    });

    test("a burst of errors schedules one reconnect, not one per error", () => {
      // The browser fires onerror on every failed attempt while it retries
      // its own way back, which on a night with bad wifi is a lot of them.
      // Each one used to arm its own timer over the top of the last handle,
      // so all but one were left uncancellable and recovery was pushed
      // further away the worse the network got.
      render(<UpdateSSEConnection />);

      act(() => emitError());
      act(() => {
        jest.advanceTimersByTime(1000);
      });
      act(() => emitError());
      act(() => {
        jest.advanceTimersByTime(1000);
      });
      act(() => emitError());

      // The first error's timer still governs, so the rebuild happens on
      // schedule rather than being pushed back by the later ones...
      act(() => {
        jest.advanceTimersByTime(TIMEOUT_ON_ERROR_MS - 2000);
      });
      expect(getEventSources()).toHaveLength(2);

      // ...and the later ones left nothing behind to fire afterwards.
      act(() => {
        jest.advanceTimersByTime(TIMEOUT_ON_ERROR_MS);
      });
      expect(getEventSources()).toHaveLength(2);
    });

    test("the keepalive watchdog still fires after an error has been ridden out", () => {
      // The stream that replaces a failed one has to be watched as closely as
      // the first: a screen left running all evening reconnects many times,
      // and one generation forgetting to arm its watchdog is a dashboard that
      // silently stops.
      render(<UpdateSSEConnection />);

      act(() => emitError());
      act(() => {
        jest.advanceTimersByTime(TIMEOUT_ON_ERROR_MS);
      });
      expect(getEventSources()).toHaveLength(2);

      act(() => {
        jest.advanceTimersByTime(KEEPALIVE_TIMEOUT_MS + 1000);
      });
      expect(getEventSources()).toHaveLength(3);

      act(() => {
        jest.advanceTimersByTime(KEEPALIVE_TIMEOUT_MS + 1000);
      });
      expect(getEventSources()).toHaveLength(4);
    });

    test("coming back online reconnects at once rather than waiting out the watchdog", () => {
      // The tablet's wifi dropping is the case this whole file exists for.
      // Waiting the full keepalive timeout after the network is demonstrably
      // back is 20s of a spectator screen showing a stale game.
      render(<UpdateSSEConnection />);
      const first = getEventSources()[0];

      act(() => {
        window.dispatchEvent(new Event("online"));
      });

      const sources = getEventSources();
      expect(sources).toHaveLength(2);
      expect(first.readyState).toBe(2); // closed
    });

    test("unmounting stops listening for the network coming back", () => {
      const { unmount } = render(<UpdateSSEConnection />);
      unmount();

      act(() => {
        window.dispatchEvent(new Event("online"));
      });

      expect(getEventSources()).toHaveLength(1);
    });

    test("unmounting closes the EventSource and clears timers, so no reconnect follows", () => {
      const { unmount } = render(<UpdateSSEConnection />);
      const es = getEventSources()[0];

      act(() => emitError());
      unmount();

      expect(es.readyState).toBe(2); // closed by the effect's cleanup

      act(() => {
        jest.advanceTimersByTime(TIMEOUT_ON_ERROR_MS + KEEPALIVE_TIMEOUT_MS);
      });

      // The pending retry timer (and the keepalive-check interval) were
      // cleared on unmount, so nothing reconnects afterwards.
      expect(getEventSources()).toHaveLength(1);
    });
  });
});
