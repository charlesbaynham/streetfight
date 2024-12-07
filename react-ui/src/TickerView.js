import React, { useCallback, useEffect, useState } from "react";

import UpdateListener from "./UpdateListener";
import { sendAPIRequest } from "./utils";

import styles from "./TickerView.module.css";

export default function TickerView({ admin = false, num_messages = 3 }) {
  const [messages, setMessages] = useState([[]]);
  const [knownTickerHash, setKnownTickerHash] = useState(0);

  const updateMessages = useCallback(() => {
    sendAPIRequest(
      "ticker_messages",
      {
        num_messages: num_messages,
      },
      "GET",
      (data) => {
        setMessages(data);
      },
    );
  }, [setMessages, num_messages]);

  useEffect(updateMessages, [updateMessages, knownTickerHash]);

  const styleClass = admin ? styles.adminTickerview : styles.userTickerview;

  return (
    <>
      <UpdateListener
        update_type="ticker"
        callback={() => {
          setKnownTickerHash(knownTickerHash + 1);
        }}
      />
      <div className={styles.tickerview + " " + styleClass}>
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
