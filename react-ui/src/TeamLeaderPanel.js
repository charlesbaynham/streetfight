import React, { useState } from "react";

import Popup from "./Popup";
import prose from "./prose";

import styles from "./TeamLeaderPanel.module.css";

// The checklist itself. A leader is walking round their team with a phone in
// one hand, so it is a list of things to look at and answer yes or no to,
// nothing to tick and nothing to submit - there is no state here to lose.
function TeamLeaderChecklist() {
  return (
    <div className={styles.checklist}>
      <h2>{prose.teamLeader.heading}</h2>
      <p>{prose.teamLeader.intro}</p>
      <ul>
        {prose.teamLeader.checklist.map((item, i) => (
          <li key={i}>{item}</li>
        ))}
      </ul>
      <p className={styles.footer}>{prose.teamLeader.footer}</p>
    </div>
  );
}

// The waiting page's version: open on the screen, because that page is where a
// leader has the time to read it and the team is still standing in front of
// them. Nothing at all for a player who is not a leader.
export default function TeamLeaderPanel({ user }) {
  if (!user || !user.is_team_leader) return null;

  return (
    <div className={styles.panel}>
      <TeamLeaderChecklist />
    </div>
  );
}

// The running game's version: one more button beside the scoreboard and shot
// history, since by then the screen belongs to the camera.
export function TeamLeaderButton({ user, standalone = false }) {
  const [showChecklist, setShowChecklist] = useState(false);

  if (!user || !user.is_team_leader) return null;

  return (
    <>
      <p>
        <button
          className={
            styles.showChecklistButton +
            (standalone ? " " + styles.standalone : "")
          }
          onClick={() => {
            setShowChecklist(true);
          }}
        >
          {prose.teamLeader.buttonText}
        </button>
      </p>

      <Popup visible={showChecklist} setVisible={setShowChecklist}>
        <TeamLeaderChecklist />
      </Popup>
    </>
  );
}
