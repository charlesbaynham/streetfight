import React, { useEffect, useState } from 'react';
import { sendAPIRequest } from './utils';

import styles from './Scoreboard.module.css'


function Scoreboard() {
    const [tableHeader, setTableHeaders] = useState(null);
    const [tableContents, setTableContents] = useState(null);

    useEffect(() => {
        sendAPIRequest("get_scoreboard")
            .then(async response => {
                if (!response.ok)
                    return
                const data = await response.json()

                setTableHeaders(data.headers);
                setTableContents(data.table);
            });
    }, [setTableHeaders, setTableContents])

    return ((tableHeader !== null & tableContents !== null) ?
        <table className={styles.scoretable}>
            <tr>
                {tableHeader.map((e, i) => <th key={i}>{e}</th>)}
            </tr>
            {tableContents.map((row, i_row) =>
                <tr key={i_row}>
                    {row.map((e, i) => <td key={i}>{e}</td>)}
                </tr>
            )}
        </table>
        : null);
}

export default Scoreboard;
