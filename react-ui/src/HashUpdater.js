/**
 * User state updater
 *
 * This is a renderless react component which polls the user state for updates
 * at a regular interval. If it gets any updates from the server, it triggers an update
 * via the passed callback.
 */

import { useCallback, useEffect, useState } from 'react'
import { makeAPIURL } from './utils'


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
    }, [known_hash, callback, updateBumper, setUpdateBumper]);

    useEffect(checkAndBump, [updateBumper, checkAndBump]);

    return null;
}
