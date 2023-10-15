import React, { useState } from 'react';
import { makeAPIURL } from './utils';

import styles from './Scoreboard.module.css'

function Scoreboard() {
    return (

        <table className={styles.scoretable}>
            <tr>
                <th>Player</th>
                <th>Team</th>
                <th>Armour</th>
                <th>Damage</th>
            </tr>
            <tr>
                <td>Kirsty</td>
                <td>Team K</td>
                <td>1</td>
                <td>999</td>
            </tr>
            <tr>
                <td>Charles</td>
                <td>Team K</td>
                <td>0</td>
                <td>6</td>
            </tr>
            <tr className={styles.knocked}>
                <td>Harry</td>
                <td>Team G</td>
                <td>0</td>
                <td>6</td>
            </tr>
            <tr className={styles.dead}>
                <td>Gaby</td>
                <td>Team G</td>
                <td>0</td>
                <td>0</td>
            </tr>
        </table>
    );
}

export default Scoreboard;
