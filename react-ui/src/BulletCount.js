import React, { useEffect, useState } from 'react';

import TemporaryOverlay from './TemporaryOverlay';
import CollectItemFromQueryParam from './CollectItemsFromQueryParams';

import styles from './BulletCount.module.css';


import medkit from './images/medkit.svg';
import bullet from './images/bullet.svg';
import armour from './images/helmet.svg';
import cross from './images/cross.svg';
import gun_11 from './images/gun_11.svg';
import gun_26 from './images/gun_26.svg';
import gun_36 from './images/gun_36.svg';
import gun_default from './images/gun_default.svg';


const make_n_images = (n, image) => Array(n).fill().map((_, i) =>
    <img src={image} alt="" key={i} style={{ height: "1.5em", verticalAlign: "middle" }} />
)


export default function BulletCount({ user }) {
    const [previousUser, setPreviousUser] = useState(null);

    const [showBulletAnim, setShowBulletAnim] = useState(false);
    const [showArmourAnim, setShowArmourAnim] = useState(false);
    const [showMedpackAnim, setShowMedpackAnim] = useState(false);

    const [showGun11, setShowGun11] = useState(false);
    const [showGun26, setShowGun26] = useState(false);
    const [showGun36, setShowGun36] = useState(false);

    const anyActive = showBulletAnim | showArmourAnim | showMedpackAnim | showGun11 | showGun26 | showGun36;

    useEffect(() => {
        var timeoutHandle = null;

        if (previousUser) {
            setShowBulletAnim(user.num_bullets > previousUser.num_bullets);
            setShowArmourAnim(user.hit_points > previousUser.hit_points && previousUser.hit_points > 0);
            setShowMedpackAnim(user.hit_points === 1 && previousUser.hit_points === 0);

            const collectedGun = (user.shot_damage != previousUser.shot_damage) | (user.shot_timeout != previousUser.shot_timeout);
            setShowGun11(collectedGun && user.shot_damage === 1 && user.shot_timeout === 1)
            setShowGun26(collectedGun && user.shot_damage === 2 && user.shot_timeout === 6)
            setShowGun36(collectedGun && user.shot_damage === 3 && user.shot_timeout === 6)

            timeoutHandle = setTimeout(() => {
                setShowBulletAnim(false)
                setShowArmourAnim(false)
                setShowMedpackAnim(false)
                setShowGun11(false)
                setShowGun26(false)
                setShowGun36(false)
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

            <TemporaryOverlay img={gun_11} appear={showGun11} />
            <TemporaryOverlay img={gun_26} appear={showGun26} />
            <TemporaryOverlay img={gun_36} appear={showGun36} />

            <CollectItemFromQueryParam enabled={
                !anyActive
            } />
        </div>

    );
}
