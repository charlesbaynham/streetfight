import React, { useCallback, useEffect, useState } from 'react';

import QRCode from "react-qr-code";

import { sendAPIRequest } from './utils';


const item_params = {
    "ammo": ["num"],
    "armour": ["num"],
    "medpack": [],
    "weapon": ["damage", "timeout"]
}
// FIXME: use the above to populate admin config interface automatically and
// also to paramatarise API calls

function ItemDisplay({ item }) {
    const item_type = item["itype"];
    const item_data = item["item_data"];
    const encoded_item = item["encoded_item"];
    const encoded_url = item["encoded_url"];

    return <>
        <QRCode value={encoded_url} />
        <br />
        Type: {item_type}
        <br />
        {"num" in item_data ?
            <>Num: {item_data.num}</>
            : null}
        <br />
        Code: {encoded_item}
        <br />
        <a href={encoded_url}>Link</a>
    </>
}

export default function NewItems() {
    const [item, setItem] = useState(null);

    const [selectedItemType, setSelectedItemType] = useState("ammo");
    const [selectedItemNum, setSelectedItemNum] = useState(1);

    const numDisabled = selectedItemType === "medpack";

    const updateItemQR = useCallback(() => {
        const item_data = numDisabled ? {} : {
            num: selectedItemNum
        };

        const callback = (d) => {
            setItem(d)
        };

        sendAPIRequest(
            "admin_make_new_item",
            { "item_type": selectedItemType },
            'POST',
            callback,
            item_data
        );
    }, [setItem, selectedItemNum, selectedItemType, numDisabled]);

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
            item ?
                <ItemDisplay item={item} />
                : null
        }



    </>
}
