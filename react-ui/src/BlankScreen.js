import React, { useEffect, useState } from "react";

import { motion } from "framer-motion";

import styles from "./BlankScreen.module.css";

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function BlankScreen({
  appear,
  color = "white",
  time_to_appear = 0.5,
  time_to_show = 0.5,
  time_to_disappear = 1.5,
}) {
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    async function f() {
      if (appear === true) {
        setVisible(true);
        await sleep(1000 * (time_to_appear + time_to_show));
        setVisible(false);
      }
    }
    f();
  }, [appear, time_to_appear, time_to_show]);

  const default_variants = {
    hidden: {
      opacity: 0,
      transitionEnd: {
        display: "none",
      },
      transition: { duration: time_to_disappear },
    },
    visible: {
      opacity: 1,
      display: "block",
      transition: { duration: time_to_appear },
    },
  };

  return (
    <motion.div
      style={{
        backgroundColor: color,
      }}
      className={styles.overlay}
      initial="hidden"
      animate={visible ? "visible" : "hidden"}
      variants={default_variants}
    />
  );
}

export default BlankScreen;
