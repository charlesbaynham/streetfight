import React, { useEffect, useState } from 'react';

import TemporaryOverlay from './TemporaryOverlay';

import medkit from './medkit.svg';
import bullet from './bullet.svg';
import armour from './helmet.svg';


export default function BulletCount({ user }) {
    const [previousUser, setPreviousUser] = useState(null);

    const [showBulletAnim, setShowBulletAnim] = useState(false);
    const [showArmourAnim, setShowArmourAnim] = useState(false);
    const [showMedpackAnim, setShowMedpackAnim] = useState(false);

    useEffect(() => {
        if (previousUser) {
            setShowBulletAnim(user.num_bullets > previousUser.num_bullets);
            setShowArmourAnim(user.hit_points > previousUser.hit_points && previousUser.hit_points > 0);
            setShowMedpackAnim(user.hit_points == 1 && previousUser.hit_points == 0);

            setTimeout(() => {
                setShowBulletAnim(false)
                setShowArmourAnim(false)
                setShowMedpackAnim(false)
            }, 3000)
        }

        setPreviousUser(user);
    }, [user, previousUser]);

    return (
        <div id="bullet-count">
            <p>Bullets: {user.num_bullets}</p>
            <p>HP: {user.hit_points}</p>
            <TemporaryOverlay img={bullet} appear={showBulletAnim} />
            <TemporaryOverlay img={armour} appear={showArmourAnim} />
            <TemporaryOverlay img={medkit} appear={showMedpackAnim} />
        </div>

    );
}
