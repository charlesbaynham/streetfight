import React, { useCallback, useEffect, useState } from "react";

import UpdateListener from "./UpdateListener";
import { openShotHistory } from "./ShotHistory";
import { sendAPIRequest } from "./utils";

import styles from "./TickerView.module.css";

// Ticker messages arrive as (class, message, shot_id) - see Ticker.get_messages.
// A private line about one of this player's own shots is the way in to it, and
// to appealing it (roadmap R8); a public line naming somebody else's shot is
// not theirs to open.
function shotToOpen([messageClass, , shotId]) {
  return messageClass === "user" && shotId ? shotId : null;
}

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
          {messages.map((m, i) => {
            const shotId = shotToOpen(m);
            return (
              <li key={i} className={m[0]}>
                {shotId ? (
                  <button
                    className={styles.shotLink}
                    onClick={() => openShotHistory(shotId)}
                  >
                    {m[1]}
                  </button>
                ) : (
                  m[1]
                )}
              </li>
            );
          })}
        </ul>
      </div>
    </>
  );
}
