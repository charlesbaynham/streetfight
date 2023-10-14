import { motion } from 'framer-motion';
import useSound from 'use-sound';

import bang from './bang.mp3';
import styles from './FireButton.module.css';
import { useCallback, useState } from 'react';


import fireButtonImg from './images/firebutton.svg';
import fireButtonImgNoAmmo from './images/firebutton_no_ammo.svg';
import fireButtonImgCooldown from './images/firebutton_cooldown.svg';



export default function FireButton({ user, onClick }) {

  const isInTeam = user ? user.team_id !== null : false;
  const hasBullets = user ? (user.num_bullets > 0) : false;
  const userHasAmmo = isInTeam && hasBullets;

  const shotTimeout = user.shot_timeout;

  const [playBang] = useSound(bang);
  const [animationState, setAnimationState] = useState("hidden")
  const [onCooldown, setOnCooldown] = useState(false);

  const fireTimeout = user.shot_timeout;  // second

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

  const fire = useCallback((e) => {
    console.log("Firing!")

    setOnCooldown(true);
    playBang();
    navigator.vibrate(200);

    setTimeout(() => {
      setAnimationState("visible")
    }, 100);

    setTimeout(() => {
      onClick(e)
    }, 0);

    setTimeout(() => {
      setAnimationState("hidden")
      setOnCooldown(false)
    }, 1000 * shotTimeout)
  }, [setAnimationState, setOnCooldown, playBang, onClick]);


  return (
    <>
      <button
        className={styles.fireButton}
        disabled={!userHasAmmo | onCooldown}
        onClick={fire}
      >
        <img src={
          userHasAmmo
            ? (onCooldown ? fireButtonImgCooldown : fireButtonImg)
            : fireButtonImgNoAmmo}
          alt="Fire button" />
        <svg className={styles.fireButtonCircle} >
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
