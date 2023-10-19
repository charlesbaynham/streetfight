
import React, { useCallback, useEffect, useState } from 'react';
import { sendAPIRequest } from './utils';



export default function ShotQueue() {

    const [shotInfo, setShotInfo] = useState(null);
    const [shotImg, setShotImg] = useState(null);

    const [shotInfoArray, setShotInfoArray] = useState([]);
    const [selectedShotIdx, setSelectedShotIdx] = useState(0);

    const [shotImgCache, setShotImgCache] = useState({})

    const updateInfo = useCallback(
        () => {
            sendAPIRequest("admin_get_unchecked_shot_info")
                .then(r => r.json())
                .then(list_of_shot_info => {
                    setShotInfoArray(list_of_shot_info)
                })
        },
        []
    );

    const loadShot = useCallback(
        () => {
            const this_shot_info = shotInfoArray[selectedShotIdx];
            if (this_shot_info === undefined)
                return
            const this_shot_id = this_shot_info.id;

            setShotInfo(this_shot_info)

            if (this_shot_id in shotImgCache)
                setShotImg(shotImgCache[this_shot_id])
            else {
                sendAPIRequest("admin_get_shot_image", { shot_id: this_shot_info.id })
                    .then(r => r.json())
                    .then(img => {
                        const newImgCache = Object.assign({}, shotImgCache);
                        newImgCache[this_shot_info.id] = img;
                        setShotImgCache(newImgCache);
                        setShotImg(img)
                    })
            }
        }, [shotInfoArray, selectedShotIdx, shotImgCache]
    )

    useEffect(() => {
        if (selectedShotIdx >= shotInfoArray.length)
            setSelectedShotIdx(shotInfoArray.length - 1)
        if (selectedShotIdx < 0)
            setSelectedShotIdx(0)
    }, [selectedShotIdx, shotInfoArray])


    const hitUser = useCallback(
        (shot_id, target_user_id) => {
            sendAPIRequest("admin_shot_hit_user", {
                shot_id: shot_id,
                target_user_id: target_user_id
            }, "POST").then(_ => { updateInfo() })
        },
        [updateInfo]
    );

    const dismissShot = useCallback(
        () => {
            sendAPIRequest("admin_mark_shot_checked", { shot_id: shotInfo.id }, "POST")
                .then(_ => { updateInfo() });
        },
        [shotInfo, updateInfo]
    );

    useEffect(updateInfo, [updateInfo])
    useEffect(loadShot, [loadShot, shotInfoArray])

    return (
        <>
            <h1>Next unchecked shot ({shotInfoArray.length} in queue):</h1>

            <button
                onClick={() => { setSelectedShotIdx(selectedShotIdx - 1) }}
                disabled={selectedShotIdx === 0}
            >
                Previous
            </button>
            <button
                onClick={() => { setSelectedShotIdx(selectedShotIdx + 1) }}
                disabled={selectedShotIdx === shotInfoArray.length - 1}
            >
                Next
            </button>

            {shotInfo ? <>
                <em>By {shotInfo.user.name}</em>
                <img alt="The next shot in the queue" src={shotImg} />
                {
                    shotInfo.game.teams.map((team, idx_team) => (
                        <div key={idx_team}>
                            <h3>{team.name}</h3>
                            <ul>
                                {
                                    team.users.map((target_user, idx_target_user) => (
                                        <li key={idx_target_user}>
                                            {target_user.name}
                                            <button onClick={() => {
                                                hitUser(shotInfo.id, target_user.id);
                                            }}>Hit</button>
                                        </li>
                                    ))
                                }
                            </ul>
                        </div>
                    ))
                }
                <button onClick={() => { dismissShot() }}>Missed</button>
            </> : null
            }

        </>
    );
}
