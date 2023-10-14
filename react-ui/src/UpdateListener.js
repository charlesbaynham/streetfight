/**
 * User state updater
 *
 * This is a renderless react component which polls the user state for updates
 * at a regular interval. If it gets any updates from the server, it triggers an update
 * via the passed callback.
 */

import { useEffect, useState } from 'react'
import { makeAPIURL } from './utils';

const TIMEOUT_ON_ERROR = 3000
const KEEPALIVE_TIMEOUT = 20000
const TIMEOUT_CHECK_INTERVAL = 1000

var listeners = new Map();


function getTimestamp() {
    return new Date().getTime();
}

export function registerListener(type, callback) {
    if (!listeners.has(type)) {
        listeners.set(type, new Map())
    }

    const handle = Math.random();
    listeners.get(type).set(handle, callback);

    return handle;
}

export function deregisterListener(type, handle) {
    listeners.get(type).delete(handle);
}

function processMessage(message) {
    if (message.handler !== "update_prompt")
        return

    const update_target = message.data

    if (listeners.has(update_target)) {
        const targetted_listeners = listeners.get(update_target);

        targetted_listeners.forEach((callback, handle) => {
            callback();
        })
    }
}

var lastTimestamp = 0;

export function UpdateSSEConnection({ endpoint = "sse_updates" }) {
    const [bumpCounter, setBumpCounter] = useState(0);

    function restartIfTimeout(cleanup) {
        const timeSinceLastEvent = (getTimestamp() - lastTimestamp);
        // console.debug(`${timeSinceLastEvent / 1000} since last event`);
        if (timeSinceLastEvent > KEEPALIVE_TIMEOUT) {
            console.log("Keepalive timeout - restarting SSE stream");
            cleanup();
            setBumpCounter(bumpCounter + 1)
        }
    }

    useEffect(() => {
        const eventSource = new EventSource(makeAPIURL(endpoint));
        var retry_timeout_handle = 0;
        var keepalive_interval_handle = 0;

        lastTimestamp = getTimestamp();

        eventSource.onmessage = (event) => {
            lastTimestamp = getTimestamp();
            // console.debug("Message received:", event)
            processMessage(JSON.parse(event.data));
        };

        eventSource.onerror = (_) => {
            console.log("SSE stream closed - retrying");
            retry_timeout_handle = setTimeout(() => { setBumpCounter(bumpCounter + 1) }, TIMEOUT_ON_ERROR)
        };

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

        // Register a watcher to restart the connection if we haven't heard anything in x seconds
        keepalive_interval_handle = setInterval(() => { restartIfTimeout(cleanup) }, TIMEOUT_CHECK_INTERVAL)

        return cleanup;
    }, [bumpCounter, setBumpCounter, endpoint]);

    return null;
}


export default function UpdateListener({ update_type, callback }) {

    useEffect(() => {
        const handle = registerListener(update_type, callback);

        return () => {
            deregisterListener(update_type, handle);
        }
    })

    return null;
}
