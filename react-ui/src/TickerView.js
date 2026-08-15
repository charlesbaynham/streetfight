import React, { useCallback, useEffect, useState } from "react";

import UpdateListener from "./UpdateListener";
import { sendAPIRequest } from "./utils";

import styles from "./TickerView.module.css";

// With a game_id, reads the admin endpoint (any game's public ticker);
// without, reads the player endpoint (the ticker of the player's own game).
export default function TickerView({
  admin = false,
  num_messages = 3,
  game_id = null,
}) {
  const [messages, setMessages] = useState([[]]);
  const [knownTickerHash, setKnownTickerHash] = useState(0);

  const updateMessages = useCallback(() => {
    sendAPIRequest(
      game_id ? "admin_ticker_messages" : "ticker_messages",
      game_id
        ? { game_id: game_id, num_messages: num_messages }
        : { num_messages: num_messages },
      "GET",
      (data) => {
        setMessages(data);
      },
    );
  }, [setMessages, num_messages, game_id]);

  useEffect(updateMessages, [updateMessages, knownTickerHash]);

  const styleClass = admin ? styles.adminTickerview : styles.userTickerview;

  return (
    <>
      <UpdateListener
        // The admin SSE stream signals "admin" on any change (and never
        // "ticker"); the player stream signals "ticker".
        update_type={game_id ? "admin" : "ticker"}
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
