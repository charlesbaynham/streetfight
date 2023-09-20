import React from 'react';

import { motion } from 'framer-motion';

import screenfillStyles from './ScreenFillStyles.module.css';


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
