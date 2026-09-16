import React from "react";

import prose from "./prose";
import styles from "./CuriosityFooter.module.css";

// The link to the essay (HowItWorks.js), shown under the two screens a player
// sits on before the game starts: the outfit picker and the onboarding front
// page. A plain anchor with target=_blank rather than a router Link on
// purpose - the picker's wardrobe ticks and fetched option list are React
// state on that page, so navigating away mid-pick would silently throw them
// away.
export default function CuriosityFooter({ className = "" }) {
  return (
    <p
      className={[styles.curiosityFooter, className].filter(Boolean).join(" ")}
    >
      <a href="/how-it-works" target="_blank" rel="noopener noreferrer">
        {prose.curiosityFooter.linkText}
      </a>
    </p>
  );
}
