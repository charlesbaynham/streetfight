import { motion } from 'framer-motion';
import useSound from 'use-sound';

import bang from './bang.mp3';
import styles from './FireButton.module.css';


const fireButtonImg = '/images/firebutton.svg';
const fireButtonImgNoAmmo = '/images/firebutton_no_ammo.svg';


export default function FireButton({ buttonActive, onClick }) {
  const [playBang] = useSound(bang);

  const circleVariants = {
    hidden: {
      strokeDasharray: "0 1000",
    },
    visible: {
      strokeDasharray: "1000 1000",
      transition: {
        duration: 2,
        ease: "easeInOut",
      },
    },
  };

  return (
    <>
      <button
        className={styles.fireButton}
        disabled={!buttonActive}
        onClick={(e) => {
          playBang();
          navigator.vibrate(200);
          return onClick(e)
        }}
      >
        <img src={buttonActive ? fireButtonImg : fireButtonImgNoAmmo} alt="Fire button" />
      </button>

      <svg width="200" height="200">
        <motion.circle
          cx="100"
          cy="100"
          r="80"
          stroke="blue"
          strokeWidth="4"
          fill="transparent"
          variants={circleVariants}
          initial="hidden"
          animate="visible"
        />
      </svg>
    </>

  );
}
