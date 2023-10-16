import React, { useCallback, useEffect, useState } from 'react';
import { sendAPIRequest } from './utils';
import UpdateListener from './UpdateListener';

import styles from './Scoreboard.module.css'


function Scoreboard() {
    const [tableContents, setTableContents] = useState(null);

    const update = useCallback(() => {
        sendAPIRequest("get_scoreboard")
            .then(async response => {
                if (!response.ok)
                    return
                const data = await response.json()
                setTableContents(data.table);
            });
    }, [setTableContents]);

    // Update scoreboard on load
    useEffect(update, [update])

    return <>
        {
            (tableContents !== null) ?
                <table className={styles.scoretable}>
                    <tr>
                        <td>Player</td>
                        <td>Team</td>
                        <td>Armour</td>
                        <td>Damage</td>
                    </tr>
                    {tableContents.map((row, i_row) => {
                        // const className = 

                        return <tr key={i_row}>
                            <td>{row.name}</td>
                            <td>{row.team}</td>
                            <td>{Math.max(row.hitpoints - 1, 0)}</td>
                            <td>{row.total_damage}</td>
                        </tr>
                    }
                    )}
                </table>
                : null
        }
        {/* Also update scoreboard when the ticker updates */}
        <UpdateListener update_type="ticker" callback={update} />
    </>;
}

export default Scoreboard;
