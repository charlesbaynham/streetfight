/**
 * User state updater
 *
 * This is a renderless react component which polls the user state for updates
 * at a regular interval. If it gets any updates from the server, it triggers an update
 * via the passed callback.
 */

import { useEffect } from 'react'


var listeners = new Map();


export function registerListener(type, callback) {
    console.log(`Registering listener for ${type}`)
    if (!listeners.has(type)) {
        console.log(`Creating new map for listener ${type}`)
        listeners.set(type, new Map())
    }

    const handle = Math.random();
    listeners.get(type).set(handle, callback);

    return handle;
}

export function deregisterListener(type, handle) {
    console.log(`Deregistering listener for ${type}`)
    listeners.get(type).delete(handle);
}

function processMessage(message) {
    console.log("Potential update received:")
    console.dir(message)
    if (message.handler !== "update_prompt")
        return

    const update_target = message.data

    console.log(`Processing update for ${update_target}`)

    if (listeners.has(update_target)) {
        const targetted_listeners = listeners.get(update_target);

        targetted_listeners.forEach((callback, handle) => {
            console.log(`Executing callback ${handle} for handler ${update_target}`);
            callback();
        })
    }
}

export function WebsocketParser() {
    useEffect(() => {
        // Establish a WebSocket connection
        const newWs = new WebSocket(`wss://${document.location.host}/api/ws_updates`);

        newWs.onopen = () => {
            console.log('WebSocket connected');
        };

        newWs.onmessage = (event) => {
            console.log(event.data);
            processMessage(JSON.parse(event.data));
        };

        newWs.onclose = () => {
            console.log('WebSocket closed');
        };

        // Close the WebSocket when the component unmounts
        return () => {
            if (newWs) {
                newWs.close();
            }
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
