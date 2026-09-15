import React, { useState } from "react";

import QRCode from "react-qr-code";

import { sendAPIRequest } from "./utils";

import styles from "./JoinQRCodes.module.css";

// Admin generator for the join codes (roadmap R15). Two kinds come back from
// one call: the game's *sign-up link*, sent to everyone before the night, which
// puts a player in the game with an outfit but no team; and one *door code*
// per team, printed and handed to the team leads, which a player scans on
// arrival to join that team keeping the outfit they picked. The printable
// version of the door codes is the team cards PDF (backend/team_cards.py).
export default function JoinQRCodes({ game_id }) {
  const [data, setData] = useState(null);

  const generate = () => {
    sendAPIRequest("admin_join_qr_codes", { game_id: game_id }, "GET", setData);
  };

  return (
    <>
      <button onClick={generate}>Generate</button>{" "}
      {data ? <button onClick={() => window.print()}>Print</button> : null}{" "}
      {data ? (
        <a
          className={styles.pdfLink}
          href={`/api/admin_team_cards_pdf?game_id=${encodeURIComponent(game_id)}`}
          download="team_cards.pdf"
        >
          Download team cards (PDF)
        </a>
      ) : null}
      {data ? (
        <>
          <h4>Sign-up link - send this to everyone</h4>
          <div className={styles.cardGrid}>
            <JoinCard label="the game" url={data.game_url} title="Sign up" />
          </div>
          <h4>Team codes - for the door</h4>
          <div className={styles.cardGrid}>
            {data.teams.map((team) => (
              <JoinCard
                key={team.team_id}
                label={`team ${team.team_name}`}
                url={team.encoded_url}
                title={`Team ${team.team_name}`}
              />
            ))}
          </div>
        </>
      ) : null}
    </>
  );
}

export function JoinCard({ label, url, title }) {
  return (
    <div className={styles.card}>
      <h4>{title}</h4>
      <a
        className={styles.qrLink}
        href={url}
        target="_blank"
        rel="noreferrer"
        aria-label={`Join link for ${label}`}
      >
        <QRCode value={url} size={256} />
      </a>
      {/* A QR image is useless to forward from the same phone someone would
          scan it with (item 1 of the 30 Aug dry-run feedback) - this is the
          plain link, visible and selectable, to paste straight into a
          WhatsApp message. */}
      <div className={styles.joinLinkRow}>
        <input
          className={styles.joinLinkInput}
          type="text"
          readOnly
          value={url}
          aria-label={`Join link text for ${label}`}
          onFocus={(e) => e.target.select()}
        />
        <button
          type="button"
          className={styles.copyButton}
          onClick={() => {
            if (navigator.clipboard && navigator.clipboard.writeText) {
              navigator.clipboard.writeText(url);
            }
          }}
        >
          Copy
        </button>
      </div>
    </div>
  );
}
