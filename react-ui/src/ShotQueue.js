
import React, { useCallback, useEffect, useState } from 'react';



export default function ShotQueue() {

    const [shot, setShot] = useState(null);
    const [numShots, setNumShots] = useState("");

    const update = useCallback(
        () => {
            console.log("Checking for new shot")
            const requestOptions = {
                method: 'GET',
                headers: { 'Content-Type': 'application/json' },
            };
            fetch('/api/admin_get_shots?' + new URLSearchParams({
                limit: 1
            }), requestOptions)
                .then(response => response.json())
                .then(response => {
                    setNumShots(response.numInQueue);
                    if (response.shots.length > 0) {
                        setShot(response.shots[0]);
                    } else {
                        setShot(null);
                    }
                });
        },
        []
    );

    const killUser = useCallback(
        (user_id) => {

            console.log(`Killing user ${user_id}`)

            const requestOptions = {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' }
            };

            const url = '/api/admin_kill_user?' + new URLSearchParams({
                user_id: user_id
            })

            fetch(url, requestOptions)
                .then(response => response.json())
                .then(response => {
                    console.log(response);
                });
        },
        []
    );

    const dismissShot = useCallback(
        () => {
            console.log("Dismissing this shot")

            const requestOptions = {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' }
            };

            const url = '/api/admin_mark_shot_checked?' + new URLSearchParams({
                shot_id: shot.id
            })

            fetch(url, requestOptions)
                .then(response => response.json())
                .then(response => {
                    console.log(response);
                    update()
                });



        },
        [shot]
    );

    useEffect(update, [])

    return (
        <>
            <h1>Next unchecked shot ({numShots} in queue):</h1>

            {shot ? <>
                <em>By {shot.user.id}</em>
                <img src={shot.image_base64} />
                Other users:
                <ul>
                    {
                        shot.game.users.map((user, idx_user) => (
                            <li key={idx_user}>
                                {user.id}
                                <button onClick={() => {
                                    killUser(user.id);
                                    dismissShot();
                                }}>Kill</button>
                            </li>
                        ))
                    }
                    <button onClick={() => { dismissShot() }}>Missed</button>
                </ul>
            </> : null}

        </>
    );
}