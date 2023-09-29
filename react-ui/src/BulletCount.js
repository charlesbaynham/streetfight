import React, { useEffect, useState } from 'react';

import TemporaryOverlay from './TemporaryOverlay';
import CollectItemFromQueryParam from './CollectItemsFromQueryParams';

import styles from './BulletCount.module.css';


import medkit from './images/medkit.svg';
import bullet from './images/bullet.svg';
import armour from './images/helmet.svg';
import cross from './images/cross.svg';
import gun_11 from './images/gun_11.svg';
import gun_16 from './images/gun_default.svg';
import gun_26 from './images/gun_26.svg';
import gun_36 from './images/gun_36.svg';
import { getGunFromUser } from './utils';


const GUN_IMGS = {
    "damage1": gun_16,
    "damage2": gun_26,
    "damage3": gun_36,
    "fast1": gun_11,
};

const make_n_images = (n, image) => Array(n).fill().map((_, i) =>
    <img src={image} alt="" key={i} style={{ height: "1.5em", verticalAlign: "middle" }} />
)


export default function BulletCount({ user }) {
    const gun_type = getGunFromUser(user);

    const [previousUser, setPreviousUser] = useState(null);

    const [showBulletAnim, setShowBulletAnim] = useState(false);
    const [showArmourAnim, setShowArmourAnim] = useState(false);
    const [showMedpackAnim, setShowMedpackAnim] = useState(false);

    const [showGunPickup, setShowGunPickup] = useState(false);

    const anyActive = showBulletAnim | showArmourAnim | showMedpackAnim | showGunPickup;

    useEffect(() => {
        var timeoutHandle = null;

        if (previousUser) {
            setShowBulletAnim(user.num_bullets > previousUser.num_bullets);
            setShowArmourAnim(user.hit_points > previousUser.hit_points && previousUser.hit_points > 0);
            setShowMedpackAnim(user.hit_points === 1 && previousUser.hit_points === 0);

            const collectedGun = (user.shot_damage != previousUser.shot_damage) | (user.shot_timeout != previousUser.shot_timeout);
            setShowGunPickup(collectedGun);

            timeoutHandle = setTimeout(() => {
                setShowBulletAnim(false)
                setShowArmourAnim(false)
                setShowMedpackAnim(false)
                setShowGunPickup(false)
            }, 3000)
        }

        setPreviousUser(user);

        if (timeoutHandle) {
            return () => { clearTimeout(timeoutHandle) }
        }
    }, [user, previousUser]);


    return (
        <div id="bullet-count" className={styles.bulletCount}>
            <p>Ammo: {
                user.num_bullets > 0 ?
                    (
                        user.num_bullets > 4 ?
                            <>{make_n_images(1, bullet)} x{user.num_bullets}</> :
                            make_n_images(user.num_bullets, bullet)
                    ) :
                    make_n_images(1, cross)
            }</p>
            <p>Armour: {
                user.hit_points > 1 ?
                    make_n_images(user.hit_points - 1, armour) :
                    make_n_images(1, cross)
            }</p>
            <TemporaryOverlay img={bullet} appear={showBulletAnim} />
            <TemporaryOverlay img={armour} appear={showArmourAnim} />
            <TemporaryOverlay img={medkit} appear={showMedpackAnim} />
            <TemporaryOverlay img={GUN_IMGS[gun_type]} appear={showGunPickup} />

            <CollectItemFromQueryParam enabled={
                !anyActive
            } />
        </div>

    );
}
