import React, { useCallback, useEffect, useState } from "react";

import UpdateListener from "./UpdateListener";
import { sendAPIRequest } from "./utils";

import styles from "./TickerView.module.css";

export default function TickerView() {
  const [messages, setMessages] = useState([[]]);
  const [knownTickerHash, setKnownTickerHash] = useState(0);

  const updateMessages = useCallback(() => {
    sendAPIRequest("ticker_messages", null, "GET", (data) => {
      setMessages(data);
    });
  }, [setMessages]);

  useEffect(updateMessages, [updateMessages, knownTickerHash]);

  return (
    <>
      <UpdateListener
        update_type="ticker"
        callback={() => {
          setKnownTickerHash(knownTickerHash + 1);
        }}
      />
      <div className={styles.tickerview}>
        <ul>
          {messages.map((m, i) => (
            <li key={i} className={m[0]}>
              {m[1]}
            </li>
          ))}
        </ul>
      </div>
    </>
  );
}
