import React, { useCallback, useEffect, useState } from 'react';

import QRCode from "react-qr-code";

import { sendAPIRequest } from './utils';

export default function NewItems() {
    const [data, setData] = useState(null);

    const getAmmo = useCallback(() => {
        const item_data = {
            num: 123
        };

        const callback = (d) => {
            console.log("New item:")
            console.log(d)
            setData(d)
        };

        sendAPIRequest(
            "admin_make_new_item",
            { "item_type": "ammo" },
            'POST',
            callback,
            item_data
        );
    }, [setData]);

    useEffect(getAmmo, []);

    return <>
        {
            data ?
                <QRCode value={data} />
                : null
        }

        <button onClick={getAmmo}>New</button>

    </>
}