import { motion } from 'framer-motion';
import useSound from 'use-sound';

import bang from './bang.mp3';
import styles from './FireButton.module.css';
import { useCallback, useState } from 'react';


import fireButtonImg from './images/firebutton.svg';
import fireButtonImgNoAmmo from './images/firebutton_no_ammo.svg';
import fireButtonImgCooldown from './images/firebutton_cooldown.svg';



export default function FireButton({ userState, onClick }) {

  const isInTeam = userState ? userState.team_id !== null : false;
  const hasBullets = userState ? (userState.num_bullets > 0) : false;
  const userHasAmmo = isInTeam && hasBullets;

  const shotTimeout = user.shot_timeout;

  const [playBang] = useSound(bang);
  const [animationState, setAnimationState] = useState("hidden")
  const [onCooldown, setOnCooldown] = useState(false);

  const circleVariants = {
    hidden: {
      strokeDasharray: "0 1000",
    },
    visible: {
      strokeDasharray: "1000 1000",
      transition: {
        duration: fireTimeout,
        ease: "linear",
      },
    },
  };

  const fireTimeout = 10;  // second

  const fire = useCallback((e) => {
    console.log("Firing!")

    setTimeout(() => {
      playBang();
      navigator.vibrate(200);
      setAnimationState("visible")
      setOnCooldown(true);
    }, 0);

    setTimeout(() => {
      setAnimationState("hidden")
      setOnCooldown(false)
    }, 1000 * shotTimeout)

    return onClick(e)
  }, [setAnimationState, setOnCooldown, playBang, onClick]);


  return (
    <>
      <button
        className={styles.fireButton}
        disabled={!userHasAmmo}
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
