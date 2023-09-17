/**
 * User state updater
 *
 * This is a renderless react component which polls the user state for updates
 * at a regular interval. If it gets any updates from the server, it triggers an update
 * via the passed callback.
 */

import { useEffect } from 'react'
import { makeAPIURL } from './utils';


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
            console.debug(`Executing callback ${handle} for handler ${update_target}`);
            callback();
        })
    }
}

export function WebsocketParser() {
    useEffect(() => {
        const eventSource = new EventSource(makeAPIURL("sse_updates"));

        eventSource.onmessage = (event) => {
            console.log("Received SSE:", event.data);
            processMessage(JSON.parse(event.data));
        };

        eventSource.onerror = (error) => {
            console.log("SSE stream closed:", error);
        };

        return () => {
            // Cleanup: close the SSE connection when the component unmounts
            eventSource.close();
        };
    }, []);

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
