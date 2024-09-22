import { Tooltip } from "react-tooltip";

import dotSrc from "./images/art/helmet.png";
import styles from "./MapView.module.css";

import { motion } from "framer-motion";
import { useState } from "react";

export default function Dot({ x, y, color = null, alpha = 1, tooltip = null }) {
  const randomNumber = useState(Math.floor(Math.random() * 100))[0];
  const tooltipID = "tooltip-" + randomNumber;

  return color === null ? (
    <motion.img
      animate={{
        scale: [1, 1.2, 1],
        x: ["-50%", "-50%"], // I'm out of energy to care about this hack
        y: ["+50%", "+50%"],
      }}
      transition={{ duration: 2.5, repeat: Infinity }}
      className={styles.mapDotSelf}
      src={dotSrc}
      alt=""
      style={{
        left: x,
        bottom: y,
        opacity: alpha,
      }}
    />
  ) : (
    <>
      {tooltip ? <Tooltip id={tooltipID} /> : null}
      <div
        data-tooltip-id={tooltipID}
        data-tooltip-content={tooltip}
        className={styles.mapDotGeneric}
        style={{
          left: x,
          bottom: y,
          backgroundColor: color,
          opacity: alpha,
        }}
      />
    </>
  );
}
