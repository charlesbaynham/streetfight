import React, { useEffect, useState } from 'react';
import { useLocation, useNavigate } from "react-router-dom";

import TemporaryOverlay from './TemporaryOverlay';
import { sendAPIRequest } from './utils';

import medkit from './medkit.svg';
import bullet from './bullet.svg';
import armour from './helmet.svg';

// A custom hook that builds on useLocation to parse
// the query string for you.
// See https://v5.reactrouter.com/web/example/query-parameters
function useQuery() {
    const { search } = useLocation();

    return React.useMemo(() => new URLSearchParams(search), [search]);
}


function CollectItemFromQueryParam({ enabled }) {
    const navigate = useNavigate();
    const query = useQuery();

    const data = query.get("d");

    useEffect(() => {
        if (enabled && data !== null) {
            console.log(`Collecting item with d=${data}`)

            function onTimeout() {
                sendAPIRequest("collect_item", {}, "POST", null, {
                    data: data
                })
                    .then((r) => {
                        console.log(r)
                    })
                    .then((_) => {
                        navigate("/")
                    })
            }
            const timeoutId = setTimeout(onTimeout, 200);

            return () => {
                console.log('Cancel collection');
                clearTimeout(timeoutId);
            };
        }
    }, [data, enabled, navigate]);

    return null
}


export default function BulletCount({ user }) {
    const [previousUser, setPreviousUser] = useState(null);

    const [showBulletAnim, setShowBulletAnim] = useState(false);
    const [showArmourAnim, setShowArmourAnim] = useState(false);
    const [showMedpackAnim, setShowMedpackAnim] = useState(false);

    useEffect(() => {
        var timeoutHandle = null;

        if (previousUser) {
            console.log(previousUser)
            setShowBulletAnim(user.num_bullets > previousUser.num_bullets);
            setShowArmourAnim(user.hit_points > previousUser.hit_points && previousUser.hit_points > 0);
            setShowMedpackAnim(user.hit_points === 1 && previousUser.hit_points === 0);

            timeoutHandle = setTimeout(() => {
                setShowBulletAnim(false)
                setShowArmourAnim(false)
                setShowMedpackAnim(false)
            }, 3000)
        }

        setPreviousUser(user);

        if (timeoutHandle) {
            return () => { clearTimeout(timeoutHandle) }
        }
    }, [user, previousUser]);

    return (
        <div id="bullet-count">
            <p>Bullets: {user.num_bullets}</p>
            <p>HP: {user.hit_points}</p>
            <TemporaryOverlay img={bullet} appear={showBulletAnim} />
            <TemporaryOverlay img={armour} appear={showArmourAnim} />
            <TemporaryOverlay img={medkit} appear={showMedpackAnim} />


            <CollectItemFromQueryParam enabled={
                !showBulletAnim && !showArmourAnim && !showMedpackAnim
            } />
        </div>

    );
}
