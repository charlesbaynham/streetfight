import React, { useCallback, useState, useRef } from 'react';

import QRCode from "react-qr-code";

import { sendAPIRequest } from './utils';

export default function NewItems() {
    const [data, setData] = useState(null);

    const getItem = useCallback((item_type, item_num) => {
        const item_data = {
            num: item_num
        };

        const callback = (d) => {
            console.log(`New ${item_type}/${item_num}:`)
            console.log(d)
            setData(d)
        };

        sendAPIRequest(
            "admin_make_new_item",
            { "item_type": item_type },
            'POST',
            callback,
            item_data
        );
    }, [setData]);

    const itemTypeRef = useRef();
    const itemNumRef = useRef();

    return <>

        <>
            <span>Type:</span>

            <select ref={itemTypeRef} >
                <option value="ammo">Ammo</option>
                <option value="medkit">Medkit</option>
                <option value="armour">Armour</option>
            </select>

            <span>Num:</span>
            <input ref={itemNumRef} type="number" />

            <button onClick={() => {
                getItem(itemTypeRef.current.value, parseInt(itemNumRef.current.value))
            }
            }
            >Generate</button>

        </>
        <br />

        {
            data ?
                <QRCode value={data} />
                : null
        }



    </>
}