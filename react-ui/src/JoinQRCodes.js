import React, { useState } from "react";

import QRCode from "react-qr-code";

import { sendAPIRequest } from "./utils";
import { Swatch } from "./Swatch";

import styles from "./JoinQRCodes.module.css";

// Admin generator for the per-team join QR codes. Each code encodes (game,
// team); a player scans their team's code and picks their own outfit from
// the team's hat colour (see PickOutfit.js / the C4 endpoints) rather than
// being handed a fixed slot.
//
// The backend allocates each team a block of slots sharing one colour in the
// team channel (the hat), so the card calls that colour out: it is the one
// garment the admin buys in bulk, and the one players use to tell friend
// from foe at a distance.
export default function JoinQRCodes({ game_id }) {
  const [data, setData] = useState(null);

  const generate = () => {
    sendAPIRequest("admin_join_qr_codes", { game_id: game_id }, "GET", setData);
  };

  return (
    <>
      <button onClick={generate}>Generate</button>{" "}
      {data ? <button onClick={() => window.print()}>Print</button> : null}
      {data ? (
        <div className={styles.cardGrid}>
          {data.teams.map((team) => (
            <div key={team.team_id} className={styles.card}>
              <h4>Team {team.team_name}</h4>
              <p className={styles.colourLine}>
                <Swatch hex={team.team_colour_hex} label={team.team_colour} />{" "}
                {team.team_colour} {data.team_channel}s
              </p>
              <a
                className={styles.qrLink}
                href={team.encoded_url}
                target="_blank"
                rel="noreferrer"
                aria-label={`Join link for team ${team.team_name}`}
              >
                <QRCode value={team.encoded_url} size={256} />
              </a>
              <p className={styles.capacityLine}>
                holds {team.capacity} players at full accuracy
              </p>
            </div>
          ))}
        </div>
      ) : null}
    </>
  );
}
