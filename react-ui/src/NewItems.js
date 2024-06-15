import React, { useCallback, useEffect, useState } from "react";

import QRCode from "react-qr-code";

import { sendAPIRequest } from "./utils";

const ITEM_PARAMS = {
  ammo: ["num"],
  armour: ["num"],
  medpack: [],
  weapon: ["shot_damage", "shot_timeout"],
};

function ItemDisplay({ item }) {
  const item_type = item["itype"];
  const item_data = item["item_data"];
  const encoded_item = item["encoded_item"];
  const encoded_url = item["encoded_url"];

  return (
    <>
      <QRCode value={encoded_url} />
      <br />
      Type: {item_type}
      <br />
      <>item_data: {JSON.stringify(item_data)}</>
      <br />
      Code: {encoded_item}
      <br />
      <a href={encoded_url}>Link</a>
    </>
  );
}

export default function NewItems() {
  const [item, setItem] = useState(null);

  const [selectedItemType, setSelectedItemType] = useState("ammo");
  const [selectedItemData, setSelectedItemData] = useState({});
  const [collected_only_once, set_collected_only_once] = useState(true);
  const [collected_as_team, set_collected_as_team] = useState(false);

  const updateItemQR = useCallback(() => {
    const postData = {};

    for (const data_name of ITEM_PARAMS[selectedItemType]) {
      const key = selectedItemType + data_name;
      if (!(key in selectedItemData)) {
        setItem(null);
        return;
      }
      postData[data_name] = selectedItemData[key];
    }

    const callback = (d) => {
      setItem(d);
    };

    sendAPIRequest(
      "admin_make_new_item",
      {
        item_type: selectedItemType,
        collected_only_once: collected_only_once,
        collected_as_team: collected_as_team,
      },
      "POST",
      callback,
      postData,
    );
  }, [
    setItem,
    selectedItemType,
    selectedItemData,
    collected_only_once,
    collected_as_team,
  ]);

  useEffect(updateItemQR, [updateItemQR]);

  return (
    <>
      <b>Type:</b>
      <br />

      <select
        value={selectedItemType}
        onChange={(e) => {
          setSelectedItemType(e.target.value);
        }}
      >
        {Object.entries(ITEM_PARAMS).map((entry, idx) => (
          <option key={idx} value={entry[0]}>
            {entry[0]}
          </option>
        ))}
      </select>

      <br />
      <b>Properties:</b>
      <br />

      {ITEM_PARAMS[selectedItemType].map((data_name) => {
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
                setSelectedItemData(new_data);
              }}
            />
          </>
        );
      })}

      <br />
      <label for="collected_only_once">collected_only_once</label>
      <input
        id="collected_only_once"
        type="checkbox"
        checked={collected_only_once}
        onClick={(_) => {
          set_collected_only_once(!collected_only_once);
        }}
      />

      <br />
      <label for="collected_as_team">collected_as_team</label>
      <input
        id="collected_as_team"
        type="checkbox"
        checked={collected_as_team}
        onClick={(_) => {
          set_collected_as_team(!collected_as_team);
        }}
      />

      <br />

      <button onClick={updateItemQR}>Re-generate</button>

      <br />

      {item ? <ItemDisplay item={item} /> : null}
    </>
  );
}
