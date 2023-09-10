import React from 'react';

import { SCREEN_FILL_STYLES } from './utils';

import crosshair from './crosshair.png';
import dead_image from './you_are_dead.png';


export const CrosshairImage = () => (
  <img
    src={crosshair}
    style={Object.assign({}, SCREEN_FILL_STYLES, { objectFit: "contain" })}
  />
);


export const DeadImage = () => (
  <img
    src={dead_image}
    style={Object.assign({}, SCREEN_FILL_STYLES, { objectFit: "contain" })}
  />
);

export const QRImage = () => (
  <img
    src={qr_guide}
    style={
      {
        position: "absolute",
        height: "50vh",
        width: "50vw",
        left: "25vw",
        top: "25vh"
      }
    }
  />
);

export default null;
