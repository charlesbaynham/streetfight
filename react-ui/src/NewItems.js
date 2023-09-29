import React, { useCallback, useEffect, useState } from 'react';

import QRCode from "react-qr-code";

import { sendAPIRequest } from './utils';


const ITEM_PARAMS = {
    "ammo": ["num"],
    "armour": ["num"],
    "medpack": [],
    "weapon": ["damage", "timeout"]
}

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
    const [selectedItemData, setSelectedItemData] = useState({});

    const updateItemQR = useCallback(() => {
        const postData = {};

        for (const data_name of ITEM_PARAMS[selectedItemType]) {
            const key = selectedItemType + data_name;
            if (!(key in selectedItemData)) {
                setItem(null)
                return
            }
            postData[data_name] = selectedItemData[key];
        }

        const callback = (d) => {
            setItem(d)
        };

        sendAPIRequest(
            "admin_make_new_item",
            { "item_type": selectedItemType },
            'POST',
            callback,
            postData
        );
    }, [setItem, selectedItemType, selectedItemData]);

    useEffect(updateItemQR, [updateItemQR]);


    return <>
        <b>Type:</b>
        <br />

        <select
            value={selectedItemType}
            onChange={(e) => { setSelectedItemType(e.target.value) }}
        >
            {Object.entries(ITEM_PARAMS).map((entry, idx) => (<option key={idx} value={entry[0]}>{entry[0]}</option>))}
        </select>

        <br />
        <b>Properties:</b>
        <br />

        {
            ITEM_PARAMS[selectedItemType].map((data_name) => {
                const key = selectedItemType + data_name;
                return (
                    <>
                        <span>{data_name}:</span>
                        <input
                            type="number"
                            value={key in selectedItemData ? selectedItemData[key] : ""}
                            key={key}
                            onChange={(e) => {
                                // Clone the object to trigger a state update
                                const new_data = { ...selectedItemData };
                                new_data[key] = e.target.value;
                                setSelectedItemData(new_data)
                            }}
                        />
                    </>
                )
            })
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
