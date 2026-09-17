import { motion } from "framer-motion";
import useSound from "use-sound";

import bang from "./bang.mp3";
import styles from "./FireButton.module.css";
import { useCallback, useEffect, useMemo, useState } from "react";
import Modernizr from "./modernizr";
import prose from "./prose";

import fireButtonImg from "./images/firebutton.svg";
import fireButtonImgNoAmmo from "./images/firebutton_no_ammo.svg";
import fireButtonImgCooldown from "./images/firebutton_cooldown.svg";

export default function FireButton({ user, onClick }) {
  const isInTeam = user ? user.team_id !== null : false;
  const hasBullets = user ? user.num_bullets > 0 : false;
  const hasWeapon = user ? user.shot_damage > 0 : false;
  const userCanShoot = isInTeam && hasBullets && hasWeapon;

  const shotTimeout = user.shot_timeout;
  const nextShotAt =
    user && user.next_shot_at != null ? user.next_shot_at : null;

  const [playBang] = useSound(bang);
  const [animationState, setAnimationState] = useState("hidden");

  // The moment this button becomes usable again, in ms on this device's
  // clock. Zero means now. Seeded from the server's answer rather than from
  // zero, so a phone that reloads mid-cooldown never paints a live button for
  // the frame before the effect below runs.
  const [deadline, setDeadline] = useState(() =>
    nextShotAt === null
      ? 0
      : Math.min(nextShotAt * 1000, Date.now() + shotTimeout * 1000),
  );
  // How long the ring has to sweep, fixed when the deadline is set so that an
  // unrelated re-render cannot restart the animation half way round.
  const [sweepSeconds, setSweepSeconds] = useState(shotTimeout);

  // The server is the authority on the cooldown (it refuses a shot fired
  // inside one), and its answer is what survives a reload - a timer in here
  // does not. It only arrives with the next "user" update, though, so firing
  // sets a deadline locally straight away and the later of the two wins.
  const serverDeadline = useMemo(() => {
    if (nextShotAt === null) return 0;
    const remaining = nextShotAt * 1000 - Date.now();
    if (remaining <= 0) return 0;
    // Clamped to the player's own cooldown: the server's epoch and the
    // phone's may disagree, and a phone whose clock is slow must not be
    // locked out for longer than the weapon it is holding.
    return Date.now() + Math.min(remaining, shotTimeout * 1000);
  }, [nextShotAt, shotTimeout]);

  useEffect(() => {
    if (serverDeadline === 0) return;
    setDeadline((current) => Math.max(current, serverDeadline));
  }, [serverDeadline]);

  // One timer owns the cooldown, whichever of the two set it.
  useEffect(() => {
    const remaining = deadline - Date.now();
    if (remaining <= 0) {
      setAnimationState("hidden");
      return;
    }

    setSweepSeconds(remaining / 1000);
    const startSweep = setTimeout(() => setAnimationState("visible"), 100);
    const finish = setTimeout(() => {
      setAnimationState("hidden");
      setDeadline(0);
    }, remaining);

    return () => {
      clearTimeout(startSweep);
      clearTimeout(finish);
    };
  }, [deadline]);

  const onCooldown = deadline > Date.now();

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
        duration: sweepSeconds,
        ease: "linear",
      },
    },
  };

  const fire = useCallback(
    (e) => {
      console.log("Firing!");

      setDeadline(Date.now() + shotTimeout * 1000);
      playBang();
      if (Modernizr.vibrate) navigator.vibrate(200);

      setTimeout(() => {
        onClick(e);
      }, 0);
    },
    [playBang, onClick, shotTimeout],
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
          alt={prose.fireButton.fireButtonAlt}
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
