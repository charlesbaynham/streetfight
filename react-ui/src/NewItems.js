import React, { useCallback, useEffect, useState } from "react";

import QRCode from "react-qr-code";

import { sendAPIRequest } from "./utils";
import { WEAPONS } from "./weapons";

const ITEM_PARAMS = {
  ammo: ["num"],
  armour: ["num"],
  medpack: [],
  weapon: ["shot_damage", "shot_timeout"],
};

// A loot drop for "No weapon" makes no sense - that entry exists only for
// AdminMode's per-player select, to describe a player who currently has
// none.
const WEAPON_LOOT_NAMES = Object.keys(WEAPONS).filter(
  (name) => name !== "No weapon",
);

// The weapon select is controlled by name, but what's actually held in
// selectedItemData is the (damage, timeout) pair updateItemQR posts - so
// look the name back up from those, the same way AdminMode's weaponName
// does for a player's stats.
function selectedWeaponName(selectedItemData) {
  const damage = selectedItemData.weaponshot_damage;
  const timeout = selectedItemData.weaponshot_timeout;
  for (const [name, [d, t]] of Object.entries(WEAPONS)) {
    if (d === damage && t === timeout) return name;
  }
  return null;
}

function ItemDisplay({ item }) {
  const item_type = item["itype"];
  const item_data = item["item_data"];
  const encoded_item = item["encoded_item"];
  const encoded_url = item["encoded_url"];

  return (
    <>
      <a href={encoded_url} target="_blank" rel="noreferrer">
        <QRCode value={encoded_url} />
      </a>
      <p>Type: {item_type}</p>
      <p>item_data: {JSON.stringify(item_data)}</p>
      {/* <p>Code: {encoded_item}</p> */}
      <p>
        <a href={encoded_url}>Link</a>
      </p>
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

      {selectedItemType === "weapon" ? (
        <div>
          <span>weapon:</span>
          <select
            value={selectedWeaponName(selectedItemData) || ""}
            onChange={(e) => {
              const [shot_damage, shot_timeout] = WEAPONS[e.target.value];
              setSelectedItemData({
                ...selectedItemData,
                weaponshot_damage: shot_damage,
                weaponshot_timeout: shot_timeout,
              });
            }}
          >
            <option value="" disabled>
              choose a weapon
            </option>
            {WEAPON_LOOT_NAMES.map((name) => (
              <option key={name} value={name}>
                {name}
              </option>
            ))}
          </select>
        </div>
      ) : (
        ITEM_PARAMS[selectedItemType].map((data_name) => {
          const key = selectedItemType + data_name;

          return (
            <div key={key}>
              <span>{data_name}:</span>
              <input
                type="number"
                value={key in selectedItemData ? selectedItemData[key] : ""}
                onChange={(e) => {
                  // Clone the object to trigger a state update
                  const new_data = { ...selectedItemData };
                  new_data[key] = e.target.value;
                  setSelectedItemData(new_data);
                }}
              />
            </div>
          );
        })
      )}

      <br />
      <label htmlFor="collected_only_once">collected_only_once</label>
      <input
        id="collected_only_once"
        type="checkbox"
        checked={collected_only_once}
        onChange={(_) => {
          set_collected_only_once(!collected_only_once);
        }}
      />

      <br />
      <label htmlFor="collected_as_team">collected_as_team</label>
      <input
        id="collected_as_team"
        type="checkbox"
        checked={collected_as_team}
        onChange={(_) => {
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
