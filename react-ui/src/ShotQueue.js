
import React, { useCallback, useEffect, useState } from 'react';
import { sendAPIRequest } from './utils';



export default function ShotQueue() {

    const [shot, setShot] = useState(null);
    const [numShots, setNumShots] = useState("");

    const update = useCallback(
        () => {
            sendAPIRequest("admin_get_unchecked_shot_info")
                .then(async response => {
                    console.log(await response.json())
                })
            // FIXME: Use get_shot_infos instead of get_shots
            // sendAPIRequest("admin_get_shots", { limit: 1 })
            //     .then(async response => {
            //         if (!response.ok)
            //             return
            //         const data = await response.json()
            //         setNumShots(data.numInQueue);
            //         if (data.shots.length > 0) {
            //             const newShot = data.shots[0];
            //             // console.log("New shot:");
            //             // console.dir(newShot);
            //             setShot(newShot);
            //         } else {
            //             setShot(null);
            //         }
            //     });
        },
        []
    );

    const hitUser = useCallback(
        (shot_id, target_user_id) => {
            sendAPIRequest("admin_shot_hit_user", {
                shot_id: shot_id,
                target_user_id: target_user_id
            }, "POST").then(_ => { update() })
        },
        [update]
    );

    const dismissShot = useCallback(
        () => {
            sendAPIRequest("admin_mark_shot_checked", { shot_id: shot.id }, "POST")
                .then(_ => { update() });
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
                                                hitUser(shot.id, target_user.id);
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
