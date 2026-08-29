// The "interested in what's happening here?" destination, linked from the
// bottom of the outfit picker. Deliberately a dead end: no API calls, no
// state, nothing a player can break by landing on it mid-flow (which is why
// the footer opens it in a new tab - the picker's wardrobe selections are
// React state and would not survive a navigation).
//
// The essay itself is Charles's to write. Everything between the PLACEHOLDER
// markers below is scaffolding: headings to write into, and a holding note so
// that a player who taps the link before it's finished gets an honest "not
// written yet" rather than filler pretending to be prose.

import React from "react";

import styles from "./HowItWorks.module.css";

function HowItWorks() {
  return (
    <div className={styles.outerContainer}>
      <article className={styles.innerContainer}>
        <h1>Clothes, colours, and error correction</h1>

        <p className={styles.holdingNote}>
          I haven't written this yet! So you'll have to ask me. Though if you
          want, you could google Hamming distances and Reed-Solomon codes. And
          then ask me why I don't get a proper job.
        </p>

        <p className={styles.backNote}>
          <a href="/">Back to the game</a>
        </p>
      </article>
    </div>
  );
}

export default HowItWorks;
