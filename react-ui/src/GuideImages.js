import React from 'react';

import screenfillStyles from './ScreenFillStyles.module.css';


const dead_image = '/images/you_are_dead.svg';
const crosshair_url = '/images/crosshair.svg';

export const CrosshairImage = () => (
  <img
    alt=""
    src={crosshair_url}
    className={screenfillStyles.screenFill}
    style={{ objectFit: "contain" }}
  />
);


export const DeadImage = () => (
  <img
    alt=""
    src={dead_image}
    className={screenfillStyles.screenFill}
    style={{ objectFit: "contain" }}
  />
);
