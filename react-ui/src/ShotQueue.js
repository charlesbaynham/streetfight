
import React, { useCallback, useEffect, useState } from 'react';
import { sendAPIRequest } from './utils';



export default function ShotQueue() {

    const [shot, setShot] = useState(null);
    const [numShots, setNumShots] = useState("");

    const update = useCallback(
        () => {
            sendAPIRequest("admin_get_shots", { limit: 1 })
                .then(response => {
                    setNumShots(response.numInQueue);
                    if (response.shots.length > 0) {
                        const newShot = response.shots[0];
                        // console.log("New shot:");
                        // console.dir(newShot);
                        setShot(newShot);
                    } else {
                        setShot(null);
                    }
                });
        },
        []
    );

    const killUser = useCallback(
        (user_id) => {
            sendAPIRequest("admin_kill_user", { user_id: user_id }, "POST")
                .then(_ => {
                    console.log(`Killed user ${user_id}`)
                });
        },
        []
    );

    const dismissShot = useCallback(
        () => {
            sendAPIRequest("admin_mark_shot_checked", { shot_id: shot.id }, "POST")
                .then(_ => {
                    console.log(`Dismissed`)
                    update()
                });
        },
        [shot]
    );

    useEffect(update, [])

    const list_of_user_lis = shot ? shot.game.teams.map((team, idx_team) => {
        return team.users.map((user, idx_user) => (
            <li key={idx_user ** 2 + idx_team ** 3}>
                {user.name}
                <button onClick={() => {
                    killUser(user.id);
                    dismissShot();
                }}>Kill</button>
            </li>
        ));
    }) : [];

    console.log(list_of_user_lis);

    return (
        <>
            <h1>Next unchecked shot ({numShots} in queue):</h1>

            {shot ? <>
                <em>By {shot.user.name}</em>
                <img src={shot.image_base64} />
                {
                    shot.game.teams.map((team, idx_team) => (
                        <>
                            <h3>{team.name}</h3>
                            <ul>
                                {
                                    team.users.map((user, idx_user) => (
                                        <li key={idx_user ** 2 + idx_team ** 3}>
                                            {user.name}
                                            <button onClick={() => {
                                                killUser(user.id);
                                                dismissShot();
                                            }}>Kill</button>
                                        </li>
                                    ))
                                }
                            </ul>
                        </>
                    ))
                }
                <button onClick={() => { dismissShot() }}>Missed</button>
            </> : null
            }

        </>
    );
}
