import { Tooltip } from 'react-tooltip'


import dotSrc from "./images/art/helmet.png";
import styles from "./MapView.module.css";

import { motion } from "framer-motion";

export default function Dot({ x, y, color = null, alpha=1 }) {
  return color === null ? (
    <motion.img
      data-tooltip-id="my-tooltip"
      data-tooltip-content="Hello to you too!"
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
    <div
      className={styles.mapDotGeneric}
      style={{
        left: x,
        bottom: y,
        backgroundColor: color,
        opacity: alpha,
      }}
    />
  );
}
