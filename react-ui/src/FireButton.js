import { motion } from "framer-motion";
import useSound from "use-sound";

import bang from "./bang.mp3";
import styles from "./FireButton.module.css";
import { useCallback, useState } from "react";
import Modernizr from "./modernizr";

import fireButtonImg from "./images/firebutton.svg";
import fireButtonImgNoAmmo from "./images/firebutton_no_ammo.svg";
import fireButtonImgCooldown from "./images/firebutton_cooldown.svg";

export default function FireButton({ user, onClick }) {
  const isInTeam = user ? user.team_id !== null : false;
  const hasBullets = user ? user.num_bullets > 0 : false;
  const hasWeapon = user ? user.shot_damage > 0 : false;
  const userCanShoot = isInTeam && hasBullets && hasWeapon;

  const shotTimeout = user.shot_timeout;

  const [playBang] = useSound(bang);
  const [animationState, setAnimationState] = useState("hidden");
  const [onCooldown, setOnCooldown] = useState(false);

  const fireTimeout = user.shot_timeout; // second

  const circleVariants = {
    hidden: {
      pathLength: 0,
      transition: {
        duration: 0.3,
      },
    },
    visible: {
      pathLength: 1,
      transition: {
        duration: fireTimeout,
        ease: "linear",
      },
    },
  };

  const fire = useCallback(
    (e) => {
      console.log("Firing!");

      setOnCooldown(true);
      playBang();
      if (Modernizr.vibrate) navigator.vibrate(200);

      setTimeout(() => {
        setAnimationState("visible");
      }, 100);

      setTimeout(() => {
        onClick(e);
      }, 0);

      setTimeout(() => {
        setAnimationState("hidden");
        setOnCooldown(false);
      }, 1000 * shotTimeout);
    },
    [setAnimationState, setOnCooldown, playBang, onClick, shotTimeout],
  );

  return (
    <>
      <button
        className={styles.fireButton}
        disabled={!userCanShoot | onCooldown}
        onClick={fire}
      >
        <img
          src={
            userCanShoot
              ? onCooldown
                ? fireButtonImgCooldown
                : fireButtonImg
              : fireButtonImgNoAmmo
          }
          alt="Fire button"
        />
        <svg className={styles.fireButtonCircle}>
          <motion.circle
            cx="50%"
            cy="50%"
            r="49%"
            stroke="white"
            strokeWidth="4"
            fill="transparent"
            variants={circleVariants}
            animate={animationState}
          />
        </svg>
      </button>
    </>
  );
}
