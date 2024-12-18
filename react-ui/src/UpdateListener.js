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

    lastTimestamp = getTimestamp();

    function restartStream() {
      cleanup();
      setBumpCounter(bumpCounter + 1);
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

    // Cleanup: close the SSE connection and deregister the timers
    function cleanup() {
      eventSource.close();
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

    // Retry after a timeout if the stream fails
    eventSource.onerror = (_) => {
      console.log("SSE stream closed - retrying");
      retry_timeout_handle = setTimeout(() => {
        setBumpCounter(bumpCounter + 1);
      }, TIMEOUT_ON_ERROR);
    };

    // Register a watcher to restart the connection if we haven't heard anything in x seconds
    keepalive_interval_handle = setInterval(
      restartIfTimeout,
      TIMEOUT_CHECK_INTERVAL,
    );

    return cleanup;
  }, [bumpCounter, setBumpCounter, endpoint]);

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
