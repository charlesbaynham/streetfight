import { Tooltip } from "react-tooltip";

import dotSrc from "./images/art/helmet.png";
import styles from "./MapView.module.css";

import { motion } from "framer-motion";
import { useState } from "react";

// Something at a position on the map. Three kinds, picked by what it is given:
// a `color` draws the plain coloured disc every player and teammate is drawn
// as; a `src` draws that image instead (the courier's aeroplane, M4.2); and
// neither draws the player's own helmet, which is the one that pulses.
//
// `className` overrides the image's own sizing, since the helmet and the
// courier are not the same size on the map.
export default function Dot({
  x,
  y,
  color = null,
  src = null,
  alpha = 1,
  tooltip = null,
  className = null,
  testId = null,
}) {
  const randomNumber = useState(Math.floor(Math.random() * 100))[0];
  const tooltipID = "tooltip-" + randomNumber;

  if (color === null) {
    // The own-position helmet pulses to pick itself out of the crowd; an
    // image passed in is drawn as it is, because the courier is already the
    // only thing on the map that looks like that and a second animation
    // beside the drop circle's ping is just noise.
    const isSelf = src === null;
    const style = { left: x, bottom: y, opacity: alpha };

    return isSelf ? (
      <motion.img
        animate={{
          scale: [1, 1.2, 1],
          x: ["-50%", "-50%"], // I'm out of energy to care about this hack
          y: ["+50%", "+50%"],
        }}
        transition={{ duration: 2.5, repeat: Infinity }}
        className={className || styles.mapDotSelf}
        src={dotSrc}
        alt=""
        style={style}
        data-testid={testId}
      />
    ) : (
      <>
        {tooltip ? <Tooltip id={tooltipID} /> : null}
        <img
          data-tooltip-id={tooltipID}
          data-tooltip-content={tooltip}
          className={className || styles.mapDotSelf}
          src={src}
          alt={tooltip || ""}
          style={style}
          data-testid={testId}
        />
      </>
    );
  }

  return (
    <>
      {tooltip ? <Tooltip id={tooltipID} /> : null}
      <div
        data-tooltip-id={tooltipID}
        data-tooltip-content={tooltip}
        className={className || styles.mapDotGeneric}
        style={{
          left: x,
          bottom: y,
          backgroundColor: color,
          opacity: alpha,
        }}
        data-testid={testId}
      />
    </>
  );
}
