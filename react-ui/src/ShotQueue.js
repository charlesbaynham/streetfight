
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

    const hitUser = useCallback(
        (from_user_id, to_user_id) => {
            sendAPIRequest("admin_shot_hit_user", {
                from_user_id: from_user_id,
                to_user_id: to_user_id
            }, "POST")
                .then(_ => {
                    console.log(`Hit user ${to_user_id} by ${from_user_id}`)
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
        [shot, update]
    );

    useEffect(update, [update])

    return (
        <>
            <h1>Next unchecked shot ({numShots} in queue):</h1>

            {shot ? <>
                <em>By {shot.user.name}</em>
                <img alt="The next shot in the queue" src={shot.image_base64} />
                {
                    shot.game.teams.map((team, idx_team) => (
                        <>
                            <h3>{team.name}</h3>
                            <ul>
                                {
                                    team.users.map((target_user, idx_target_user) => (
                                        <li key={idx_target_user ** 2 + idx_team ** 3}>
                                            {target_user.name}
                                            <button onClick={() => {
                                                hitUser(shot.user.id, target_user.id);
                                                dismissShot();
                                            }}>Hit</button>
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
