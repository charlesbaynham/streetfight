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

var listeners = new Map();


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

export function WebsocketParser() {
    const [bumpCounter, setBumpCounter] = useState(0);

    useEffect(() => {
        const eventSource = new EventSource(makeAPIURL("sse_updates"));
        var retry_timeout = 0;

        eventSource.onmessage = (event) => {
            processMessage(JSON.parse(event.data));
        };

        eventSource.onerror = (_) => {
            console.log("SSE stream closed - retrying");
            retry_timeout = setTimeout(() => { setBumpCounter(bumpCounter + 1) }, TIMEOUT_ON_ERROR)
        };

        return () => {
            // Cleanup: close the SSE connection when the component unmounts
            eventSource.close();
            if (retry_timeout !== 0) {
                clearTimeout(retry_timeout);
            }
        };
    }, [bumpCounter, setBumpCounter]);

    return null;
}


export default function HashUpdater({ update_type, callback }) {

    useEffect(() => {
        const handle = registerListener(update_type, callback);

        return () => {
            deregisterListener(update_type, handle);
        }
    })

    return null;
}
