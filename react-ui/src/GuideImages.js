import React, { useCallback, useEffect, useState } from 'react';

import { motion } from 'framer-motion';

import screenfillStyles from './ScreenFillStyles.module.css';
import styles from './GuideImages.module.css';


import dead_image from './images/you_are_dead.svg';
import crosshair_url from './images/crosshair.svg';

export const CrosshairImage = () => (
  <img
    alt=""
    src={crosshair_url}
    className={screenfillStyles.screenFill}
  />
);


export const DeadImage = () => (
  <motion.img
    alt="You Died"
    src={dead_image}
    className={
      screenfillStyles.screenFill
    }
    animate={{
      width: ["20vw", "50vw"],
      opacity: [0, 1, 1]
    }}
    transition={{
      duration: 5,
    }}
  />
);

function getTimeRemaining(timestamp) {
  const now = new Date().getTime();
  const timeRemaining = Math.max(0, timestamp - now); // Ensure time doesn't go negative

  const minutes = Math.floor((timeRemaining / (1000 * 60)) % 60);
  const seconds = Math.floor((timeRemaining / 1000) % 60);

  const formattedMinutes = minutes.toString().padStart(2, '0');
  const formattedSeconds = seconds.toString().padStart(2, '0');

  return `${formattedMinutes}:${formattedSeconds}`;
}

function CountdownTimer({ deadline }) {
  const [output, setOutput] = useState("");

  const update = useCallback(() => {
    setOutput(getTimeRemaining(deadline))
  }, [setOutput, deadline])

  useEffect(() => {
    const timer_id = setInterval(update, 1000)
    return () => { clearInterval(timer_id) }
  }, [update])

  return output
}

export const KnockedOutView = ({ user }) => (
  <div
    className={
      screenfillStyles.screenFill + " " + styles.centeringDiv
    }
  >
    <motion.div
      animate={{
        scale: [0, 1],
        opacity: [0, 1]
      }}
      transition={{
        duration: 1,
      }}>
      <p>You are knocked out</p>
      <p className={styles.textSmaller}>Get a medkit quick! You will die in:</p>
      <p className={styles.textSmaller}>{<CountdownTimer deadline={1000 * user.time_of_death} />}</p>

    </motion.div>
  </div >
);
