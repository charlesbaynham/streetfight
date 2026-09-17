import React, { useCallback, useEffect, useState } from "react";

import { motion } from "framer-motion";

import screenfillStyles from "./ScreenFillStyles.module.css";
import styles from "./GuideImages.module.css";

import dead_image from "./images/you_are_dead.svg";
import crosshair_url from "./images/crosshair.svg";
import prose from "./prose";

export const CrosshairImage = () => (
  <img alt="" src={crosshair_url} className={screenfillStyles.screenFill} />
);

export const DeadImage = () => (
  <motion.img
    alt={prose.guideImages.deadAlt}
    src={dead_image}
    className={screenfillStyles.screenFill}
    animate={{
      width: ["20vw", "50vw"],
      opacity: [0, 1, 1],
    }}
    transition={{
      duration: 5,
    }}
  />
);

function getTimeRemaining(timestamp) {
  const now = new Date().getTime();
  const timeRemaining = Math.max(0, timestamp - now); // Ensure time doesn't go negative

  // Total minutes, not minutes-past-the-hour: a cue an admin sets ninety
  // minutes out must not read 30:00 (the knocked-out clock never gets near an
  // hour, so this changes nothing for it).
  const minutes = Math.floor(timeRemaining / (1000 * 60));
  const seconds = Math.floor((timeRemaining / 1000) % 60);

  const formattedMinutes = minutes.toString().padStart(2, "0");
  const formattedSeconds = seconds.toString().padStart(2, "0");

  return `${formattedMinutes}:${formattedSeconds}`;
}

// mm:ss down to a deadline in epoch milliseconds, ticking every second and
// floored at 00:00. Exported for NextEventStrip.js - one formatter, so the
// knocked-out clock and the "what happens next" strip count the same way.
export function CountdownTimer({ deadline }) {
  const [output, setOutput] = useState(() => getTimeRemaining(deadline));

  const update = useCallback(() => {
    setOutput(getTimeRemaining(deadline));
  }, [setOutput, deadline]);

  useEffect(() => {
    // Render the first value straight away rather than a second late: a strip
    // that appears blank is a strip nobody trusts.
    update();
    const timer_id = setInterval(update, 1000);
    return () => {
      clearInterval(timer_id);
    };
  }, [update]);

  return output;
}

export const KnockedOutView = ({ user }) => (
  <div className={screenfillStyles.screenFill + " " + styles.centeringDiv}>
    <motion.div
      animate={{
        scale: [0, 1],
        opacity: [0, 1],
      }}
      transition={{
        duration: 1,
      }}
    >
      <p>{prose.guideImages.knockedOutTitle}</p>
      <p className={styles.textSmaller}>{prose.guideImages.medkitWarning}</p>
      <p className={styles.textSmaller}>
        {<CountdownTimer deadline={1000 * user.time_of_death} />}
      </p>
    </motion.div>
  </div>
);
