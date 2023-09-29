import React, { useCallback, useEffect, useState } from 'react';

import QRCode from "react-qr-code";

import { sendAPIRequest } from './utils';


const ITEM_PARAMS = {
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
    const [selectedItemData, setSelectedItemData] = useState([]);


    const updateItemQR = useCallback(() => {
        // const item_data = numDisabled ? {} : {
        //     num: selectedItemNum
        // };

        // const callback = (d) => {
        //     setItem(d)
        // };

        // sendAPIRequest(
        //     "admin_make_new_item",
        //     { "item_type": selectedItemType },
        //     'POST',
        //     callback,
        //     item_data
        // );
    }, [setItem, selectedItemType]);

    useEffect(updateItemQR, [updateItemQR]);


    return <>
        <b>Type:</b>
        <br />

        <select
            value={selectedItemType}
            onChange={(e) => { setSelectedItemData([]); setSelectedItemType(e.target.value) }}
        >
            {Object.entries(ITEM_PARAMS).map((entry, idx) => (<option key={idx} value={entry[0]}>{entry[0]}</option>))}
        </select>

        <br />
        <b>Properties:</b>
        <br />

        {
            ITEM_PARAMS[selectedItemType].map((data_name, idx) => (
                <>
                    <span>{data_name}:</span>
                    <input
                        type="number"
                        value={selectedItemData[idx]}
                        key={idx}
                        onChange={(e) => {
                            const new_data = selectedItemData;
                            new_data[idx] = e.target.value;
                            setSelectedItemData(new_data)
                            console.log(new_data)
                        }}
                    />
                </>
            ))
        }

        <br />

        <button onClick={updateItemQR}>Re-generate</button>

        <br />

        {
            item ?
                <ItemDisplay item={item} />
                : null
        }
    </>
}
