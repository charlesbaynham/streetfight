
import React, { useCallback, useEffect, useState } from 'react';
import { sendAPIRequest } from './utils';



export default function ShotQueue() {

    const [shotInfo, setShotInfo] = useState(null);
    const [shotImg, setShotImg] = useState(null);
    const [numShots, setNumShots] = useState("");

    const update = useCallback(
        () => {
            sendAPIRequest("admin_get_unchecked_shot_info")
                .then(async response => {
                    return await response.json();
                })
                .then(async list_of_shot_info => {
                    if (list_of_shot_info.length == 0)
                        return

                    const this_shot = list_of_shot_info[0];
                    console.log(this_shot)
                    setShotInfo(this_shot)
                    sendAPIRequest("admin_get_shot_image", { shot_id: this_shot.id })
                        .then(r => r.json())
                        .then(img => {
                            console.log(img)
                            setShotImg(img)
                        })

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
            sendAPIRequest("admin_mark_shot_checked", { shot_id: shotInfo.id }, "POST")
                .then(_ => { update() });
        },
        [shotInfo, update]
    );

    useEffect(update, [update])

    return (
        <>
            <h1>Next unchecked shot ({numShots} in queue):</h1>

            {shotInfo ? <>
                <em>By {shotInfo.user.name}</em>
                <img alt="The next shot in the queue" src={shotImg} />
                {
                    shotInfo.game.teams.map((team, idx_team) => (
                        <>
                            <h3>{team.name}</h3>
                            <ul>
                                {
                                    team.users.map((target_user, idx_target_user) => (
                                        <li key={idx_target_user ** 2 + idx_team ** 3}>
                                            {target_user.name}
                                            <button onClick={() => {
                                                hitUser(shotInfo.id, target_user.id);
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
