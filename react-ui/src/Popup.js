import React from "react";

import { motion, AnimatePresence } from "framer-motion";

import styles from "./Popup.module.css";
import buttonImg from "./images/exit-button.svg";

const variants = {
  open: { opacity: 1 },
  closed: { opacity: 0 },
};

function Popup({ children, visible, setVisible }) {
  const out = (
    <div className={styles.fullscreenContainer}>
      <motion.div
        className={styles.outerContainer}
        initial="closed"
        animate={visible ? "open" : "closed"}
        transition={{ duration: 0.5 }}
        variants={variants}
        exit="closed"
      >
        <button
          className={styles.exitButton}
          onClick={() => {
            setVisible(false);
          }}
        >
          <img src={buttonImg} alt="" />
        </button>
        <div className={styles.innerContainer}>{children}</div>
      </motion.div>
    </div>
  );

  return <AnimatePresence>{visible ? out : null}</AnimatePresence>;
}

export default Popup;
