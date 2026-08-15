import React, { useState } from "react";

import QRCode from "react-qr-code";

import { sendAPIRequest } from "./utils";

import styles from "./JoinQRCodes.module.css";

// Admin generator for the per-slot team join QR codes. Each code encodes
// (game, team, identity slot); printing the grid gives one card per outfit to
// hand out with the matching clothing.
//
// The backend allocates each team a block of slots sharing one colour in the
// team channel (the hat), so the heading calls that colour out: it is the one
// garment the admin buys in bulk, and the one players use to tell friend from
// foe. A team big enough to outgrow one colour reports the extras too.
function teamColoursLabel(channel, colours) {
  if (!channel || !colours || colours.length === 0) return null;
  if (colours.length === 1) return `${colours[0]} ${channel}s`;
  return `${channel}s: ${colours.join(" then ")}`;
}

export default function JoinQRCodes({ game_id }) {
  const [slotsPerTeam, setSlotsPerTeam] = useState(8);
  const [data, setData] = useState(null);

  const generate = () => {
    sendAPIRequest(
      "admin_join_qr_codes",
      { game_id: game_id, slots_per_team: slotsPerTeam },
      "GET",
      setData,
    );
  };

  return (
    <>
      <label>
        Slots per team:{" "}
        <input
          type="number"
          min="1"
          value={slotsPerTeam}
          onChange={(e) => setSlotsPerTeam(e.target.value)}
        />
      </label>{" "}
      <button onClick={generate}>Generate</button>{" "}
      {data ? <button onClick={() => window.print()}>Print</button> : null}
      {data
        ? data.teams.map((team) => (
            <div key={team.team_id}>
              <h4>
                Team {team.team_name}
                {teamColoursLabel(data.team_channel, team.team_colours) ? (
                  <span className={styles.teamColours}>
                    {" — "}
                    {teamColoursLabel(data.team_channel, team.team_colours)}
                  </span>
                ) : null}
              </h4>
              <div className={styles.codeGrid}>
                {team.codes.map((code) => (
                  <div key={code.slot} className={styles.codeCard}>
                    <QRCode value={code.encoded_url} size={128} />
                    <p>
                      <b>
                        Team {team.team_name} — outfit #{code.slot}
                      </b>
                    </p>
                    <ul className={styles.appearanceList}>
                      {Object.entries(code.appearance).map(
                        ([channel, colour]) => (
                          <li key={channel}>
                            {channel}: {colour}
                          </li>
                        ),
                      )}
                    </ul>
                  </div>
                ))}
              </div>
            </div>
          ))
        : null}
    </>
  );
}
