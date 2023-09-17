/**
 * User state updater
 *
 * This is a renderless react component which polls the user state for updates
 * at a regular interval. If it gets any updates from the server, it triggers an update
 * via the passed callback.
 */

import { useCallback, useEffect, useState } from 'react'
import { makeAPIURL } from './utils'

let listeners = new Map();


function registerListener(type, callback) {
    if (!listeners.has(type)) {
        listeners.set(type, new Map())
    }

    const handle = Math.random();
    listeners.get(type).set(handle, callback);

    return handle;
}

function deregisterListener(type, handle) {
    listeners.get(type).delete(handle);
}

function processMessage(message) {
    if (message.handler != "update_prompt")
        return

    const update_target = message.data

    if (listeners.has(update_target)) {
        const targetted_listeners = listeners.get(update_target);

        targetted_listeners.forEach((handle, callback) => {
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
            processMessage(event.data);
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


export default function HashUpdater({ known_hash, callback, api_call }) {
    const [updateBumper, setUpdateBumper] = useState(0);

    const errorCheckRate = 1000
    const successCheckRate = 500

    const checkAndBump = useCallback(() => {
        const successHandler = r => {

            setTimeout(() => {
                setUpdateBumper(updateBumper + 1);
            }, (r.ok ? successCheckRate : errorCheckRate))

            if (!r.ok) {
                // Unknown error: log it to console
                console.log("Fetch state failed with error " + r.status);
                console.log(r);
                return;
            }

            // Otherwise, process the json and update the state if required
            return r.json().then(new_hash => {
                if (new_hash !== known_hash) {
                    callback(new_hash)
                }
            })
        }

        const failureHandler = r => {
            setTimeout(() => {
                setUpdateBumper(updateBumper + 1);
            }, errorCheckRate)

            console.log(`Remounted updater after error after failure`)
        }

        const url = makeAPIURL(api_call, { known_hash: known_hash })

        fetch(url).then(successHandler, failureHandler)
    }, [known_hash, callback, updateBumper, setUpdateBumper, api_call]);

    useEffect(checkAndBump, [updateBumper, checkAndBump]);

    return null;
}
