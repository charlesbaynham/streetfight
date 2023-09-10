import React from 'react';

import { SCREEN_FILL_STYLES } from './utils';


const dead_image = '/images/you_are_dead.svg';
const crosshair_url = '/images/crosshair.svg';

export const CrosshairImage = () => (
  <img
    src={crosshair_url}
    style={Object.assign({}, SCREEN_FILL_STYLES, { objectFit: "contain" })}
  />
);


export const DeadImage = () => (
  <img
    src={dead_image}
    style={Object.assign({}, SCREEN_FILL_STYLES, { objectFit: "contain" })}
  />
);

export default null;
