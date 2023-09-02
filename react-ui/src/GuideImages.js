import React from 'react';

import { SCREEN_FILL_STYLES } from './utils';

import crosshair from './crosshair.png';
import qr_guide from './qr_guide.png';


export const CrosshairImage = () => (
  <img
    src={crosshair}
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
