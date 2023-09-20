import React from 'react';

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
  <img
    alt="You Died"
    src={dead_image}
    className={
      screenfillStyles.screenFill
      + " " +
      styles.deadImage
    }
  />
);
