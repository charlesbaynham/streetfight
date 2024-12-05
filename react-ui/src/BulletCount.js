import React, { useEffect, useState } from "react";

import TemporaryOverlay from "./TemporaryOverlay";
import CollectItemFromQueryParam from "./CollectItemsFromQueryParams";
import Popup from "./Popup";
import Scoreboard from "./Scoreboard";

import styles from "./BulletCount.module.css";

import medkit from "./images/art/medkit.png";
import bullet from "./images/art/bullet.png";
import armour from "./images/art/helmet.png";
import cross from "./images/cross.svg";
import { getGunImgFromUser } from "./utils";

const make_n_images = (n, image) =>
  Array(n)
    .fill()
    .map((_, i) => <img src={image} alt="" key={i} className={styles.icon} />);

export default function BulletCount({ user }) {
  const [previousUser, setPreviousUser] = useState(null);

  const [showBulletAnim, setShowBulletAnim] = useState(false);
  const [showArmourAnim, setShowArmourAnim] = useState(false);
  const [showMedpackAnim, setShowMedpackAnim] = useState(false);

  const [showGunPickup, setShowGunPickup] = useState(false);

  const anyActive =
    showBulletAnim | showArmourAnim | showMedpackAnim | showGunPickup;

  const [showScores, setShowScores] = useState(false);

  useEffect(() => {
    var timeoutHandle = null;

    if (previousUser) {
      setShowBulletAnim(user.num_bullets > previousUser.num_bullets);
      setShowArmourAnim(
        user.hit_points > previousUser.hit_points && previousUser.hit_points > 0
      );
      setShowMedpackAnim(
        user.hit_points === 1 && previousUser.hit_points === 0
      );

      const collectedGun =
        user.shot_damage !== previousUser.shot_damage ||
        user.shot_timeout !== previousUser.shot_timeout;
      setShowGunPickup(collectedGun);

      timeoutHandle = setTimeout(() => {
        setShowBulletAnim(false);
        setShowArmourAnim(false);
        setShowMedpackAnim(false);
        setShowGunPickup(false);
      }, 3000);
    }

    setPreviousUser(user);

    if (timeoutHandle) {
      return () => {
        clearTimeout(timeoutHandle);
      };
    }
  }, [user, previousUser]);

  return (
    <div id="bullet-count" className={styles.bulletCount}>
      <p>
        Ammo:{" "}
        {user.num_bullets > 0 ? (
          user.num_bullets > 3 ? (
            <>
              {make_n_images(1, bullet)} x{user.num_bullets}
            </>
          ) : (
            make_n_images(user.num_bullets, bullet)
          )
        ) : (
          make_n_images(1, cross)
        )}
      </p>
      <p>
        Armour:{" "}
        {user.hit_points > 1
          ? make_n_images(user.hit_points - 1, armour)
          : make_n_images(1, cross)}
      </p>
      <p>
        <img
          className={styles.weaponImg}
          src={getGunImgFromUser(user)}
          alt=""
        />
      </p>

      <TemporaryOverlay img={bullet} appear={showBulletAnim} />
      <TemporaryOverlay img={armour} appear={showArmourAnim} />
      <TemporaryOverlay img={medkit} appear={showMedpackAnim} />
      <TemporaryOverlay img={getGunImgFromUser(user)} appear={showGunPickup} />

      <CollectItemFromQueryParam enabled={!anyActive} />

      <p>
        <button
          className={styles.showScoresButton}
          onClick={() => {
            setShowScores(true);
          }}
        >
          Show scores &gt;&gt;
        </button>
      </p>

      <Popup visible={showScores} setVisible={setShowScores}>
        <Scoreboard />
      </Popup>
    </div>
  );
}
