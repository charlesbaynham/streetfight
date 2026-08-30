/**
 * User state updater
 *
 * This is a renderless react component which polls the user state for updates
 * at a regular interval. If it gets any updates from the server, it triggers an update
 * via the passed callback.
 */

import { useEffect, useState } from "react";
import { makeAPIURL } from "./utils";

// How long to wait before attempting a reconnect on error
const TIMEOUT_ON_ERROR = 3000;
// How long to go without messages before calling it a timeout.
// Should be greater than the timeout interval in main.py!
const KEEPALIVE_TIMEOUT = 20000;
// How often to check if we have timed out:
const TIMEOUT_CHECK_INTERVAL = 1000;

// A map of listeners to maps of handle to callback. e.g.:
// {
//   "ticker": {564738: ticker_callback_1, 7854398: ticker_callback_2},
//   "user": {345678: user_callback}
// }
var listeners = new Map();

function getTimestamp() {
  return new Date().getTime();
}

// Register a listener for a given type of update. The callback will be called
// when an update arrives from the SSE stream. This function returns a handle:
// call deregisterListener with the same handle to stop listening.
export function registerListener(type, callback) {
  if (!listeners.has(type)) {
    listeners.set(type, new Map());
  }

  const handle = Math.random();
  listeners.get(type).set(handle, callback);

  return handle;
}

// Deregister a listener for a given type of update. See registerListener.
export function deregisterListener(type, handle) {
  listeners.get(type).delete(handle);
}

function processUpdateMessage(message) {
  const update_target = message.data;

  if (listeners.has(update_target)) {
    const targetted_listeners = listeners.get(update_target);

    targetted_listeners.forEach((callback, handle) => {
      callback();
    });
  }
}

var lastTimestamp = 0;

// This UpdateSSEConnection component mounts to an SSE endpoint and listens for
// updates from it, dispatching them to the appropriate listeners. You can
// register listeners wherever you want in the frontend code, but there must be
// one UpdateSSEConnection mounted somewhere otherwise they won't receive
// updates. I think you could also have multiple UpdateSSEConnection components
// if you needed multiple SSE endpoints which you still dispatch events
// appropriately. Untested though.
export function UpdateSSEConnection({ endpoint = "sse_updates" }) {
  const [bumpCounter, setBumpCounter] = useState(0);

  useEffect(() => {
    const eventSource = new EventSource(makeAPIURL(endpoint));
    var retry_timeout_handle = 0;
    var keepalive_interval_handle = 0;
    var keepaliveCount = null;
    // One restart per connection. restartStream tears the stream down before
    // it asks React for a replacement, so a second caller would be tidying up
    // an already-closed socket - and every path into it (a keepalive desync,
    // the watchdog, a retry timer, the network coming back) can fire while
    // another is already in flight.
    var restarted = false;

    lastTimestamp = getTimestamp();

    function restartStream() {
      if (restarted) return;
      restarted = true;
      cleanup();
      // Functional, not `bumpCounter + 1`: the value this effect closed over
      // is a generation old the moment anything else has bumped it, and a
      // state update that lands on the value already there is dropped - which
      // here would mean a stream closed by the line above with nothing left
      // running to reopen it.
      setBumpCounter((counter) => counter + 1);
    }

    function restartIfTimeout() {
      const timeSinceLastEvent = getTimestamp() - lastTimestamp;
      // console.debug(`${timeSinceLastEvent / 1000} since last event`);
      if (timeSinceLastEvent > KEEPALIVE_TIMEOUT) {
        console.log("Keepalive timeout - restarting SSE stream");
        restartStream();
      }
    }

    function processMessage(message) {
      if (message.handler === "update_prompt")
        return processUpdateMessage(message);
      else if (message.handler === "keepalive")
        return processKeepaliveMessage(message);
    }

    function processKeepaliveMessage(message) {
      const newKeepaliveCount = message.data;
      console.log("Keepalive count:", newKeepaliveCount, keepaliveCount);
      if (keepaliveCount === null || newKeepaliveCount === keepaliveCount + 1)
        keepaliveCount = newKeepaliveCount;
      else {
        console.log("Keepalive desync - restarting stream");
        restartStream();
      }
    }

    // A screen nobody touches - the spectator TV above all - has no way back
    // from a wifi drop except a timer, and waiting out the keepalive watchdog
    // is 20s of showing a game that has moved on. The browser knows the
    // moment the network is back, so take its word for it.
    function handleOnline() {
      console.log("Network back - restarting SSE stream");
      restartStream();
    }

    // Cleanup: close the SSE connection and deregister the timers
    function cleanup() {
      eventSource.close();
      window.removeEventListener("online", handleOnline);
      if (retry_timeout_handle !== 0) {
        clearTimeout(retry_timeout_handle);
      }
      if (keepalive_interval_handle !== 0) {
        clearInterval(keepalive_interval_handle);
      }
    }

    // When messages arrive, update the latest timestamp and
    // pass them for processing by the listeners
    eventSource.onmessage = (event) => {
      lastTimestamp = getTimestamp();
      const parsed_event = JSON.parse(event.data);
      processMessage(parsed_event);
    };

    // Retry after a timeout if the stream fails. The browser fires this on
    // every failed attempt while it retries its own way back, so a rebuild
    // that is already scheduled is left to run: re-arming the timer on each
    // error would push recovery further away the worse the network is, and
    // overwriting the handle would leave the previous timer uncancellable.
    eventSource.onerror = (_) => {
      if (restarted || retry_timeout_handle !== 0) return;
      console.log("SSE stream closed - retrying");
      retry_timeout_handle = setTimeout(restartStream, TIMEOUT_ON_ERROR);
    };

    window.addEventListener("online", handleOnline);

    // Register a watcher to restart the connection if we haven't heard anything in x seconds
    keepalive_interval_handle = setInterval(
      restartIfTimeout,
      TIMEOUT_CHECK_INTERVAL,
    );

    return cleanup;
  }, [bumpCounter, endpoint]);

  return null;
}

// Component to automatically handle registering / deregistering listeners. You
// could just use registerListener and deregisterListener directly if you
// prefer.
export default function UpdateListener({ update_type, callback }) {
  useEffect(() => {
    const handle = registerListener(update_type, callback);

    return () => {
      deregisterListener(update_type, handle);
    };
  });

  return null;
}
