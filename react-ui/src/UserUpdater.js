/**
 * User state updater
 *
 * This is a renderless react component which polls the user state for updates
 * at a regular interval. If it gets any updates from the server, it triggers an update
 * via the passed callback.
 */

import { Component } from 'react'
import { makeAPIURL } from './utils'

class UserStateUpdater extends Component {

    constructor() {
        super()

        this.timeoutID = null
        this.cancelled = false
        this.checkAndReschedule = this.checkAndReschedule.bind(this)
    }

    componentDidMount() {
        this.checkAndReschedule()
    }

    componentWillUnmount() {
        this.stopPolling()
    }


    checkAndReschedule() {
        const errorCheckRate = 1000
        const successCheckRate = 500

        const successHandler = r => {
            console.log(`New hash received - cancelled=${this.cancelled}`)

            if (!this.cancelled) {
                this.timeoutID = setTimeout(this.checkAndReschedule, (r.ok ? successCheckRate : errorCheckRate))

                console.log(`New hash received - rescheduling check (${this.timeoutID})`)

                if (!r.ok) {
                    // Unknown error: log it to console
                    console.log("Fetch state failed with error " + r.status);
                    console.log(r);
                    return;
                }

                // Otherwise, process the json and update the state if required
                return r.json().then(new_hash => {
                    if (new_hash !== this.props.known_hash) {
                        this.props.callback(new_hash)
                    }
                })
            }
        }

        const failureHandler = r => {
            if (!this.cancelled) {
                this.timeoutID = setTimeout(this.checkAndReschedule, errorCheckRate)
                console.log(`Remounted updater after error with id ${this.timeoutID} after failure`)
            }
        }

        const url = makeAPIURL("get_hash", { known_hash: this.props.known_hash })

        return fetch(url).then(successHandler, failureHandler)
    }

    stopPolling() {
        console.log(`Unmounting updater with id ${this.timeoutID}`)
        clearTimeout(this.timeoutID)
        this.cancelled = true
    }

    render() {
        return null
    }
}


export default UserStateUpdater;
