import React, { useCallback, useEffect, useState } from 'react';

import QRCode from "react-qr-code";

import { sendAPIRequest } from './utils';

function ItemDisplay({ data }) {
    return <QRCode value={data} />
}

export default function NewItems() {
    const [itemData, setItemData] = useState(null);

    const [selectedItemType, setSelectedItemType] = useState("ammo");
    const [selectedItemNum, setSelectedItemNum] = useState(1);

    const numDisabled = selectedItemType === "medpack";

    const updateItemQR = useCallback(() => {
        const item_data = numDisabled ? {} : {
            num: selectedItemNum
        };

        const callback = (d) => {
            console.log(`New ${selectedItemType}/${selectedItemNum}:`)
            console.log(d)
            setItemData(d)
        };

        sendAPIRequest(
            "admin_make_new_item",
            { "item_type": selectedItemType },
            'POST',
            callback,
            item_data
        );
    }, [setItemData, selectedItemNum, selectedItemType, numDisabled]);

    useEffect(updateItemQR, [updateItemQR]);

    return <>

        <>
            <span>Type:</span>

            <select
                value={selectedItemType}
                onChange={(e) => { setSelectedItemType(e.target.value) }}
            >
                <option value="ammo">Ammo</option>
                <option value="medpack">Medpack</option>
                <option value="armour">Armour</option>
            </select>

            <span>Num:</span>
            <input
                type="number"
                value={selectedItemNum}
                disabled={numDisabled}
                onChange={(e) => { setSelectedItemNum(e.target.value) }}
            />

            <button onClick={updateItemQR}>Re-generate</button>

        </>
        <br />

        {
            itemData ?
                <ItemDisplay data={itemData} />
                : null
        }



    </>
}