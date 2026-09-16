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

import prose from "./prose";
import styles from "./HowItWorks.module.css";

function HowItWorksBlock({ block }) {
  if (block.type === "diagram") {
    return (
      <figure className={styles.diagram}>
        {block.node}
        {block.caption && <figcaption>{block.caption}</figcaption>}
      </figure>
    );
  }
  return <p className={styles.holdingNote}>{block.text}</p>;
}

function HowItWorks() {
  return (
    <div className={styles.outerContainer}>
      <article className={styles.innerContainer}>
        <h1>{prose.howItWorks.heading}</h1>

        {prose.howItWorks.content.map((block, index) => (
          <HowItWorksBlock key={index} block={block} />
        ))}

        <p className={styles.backNote}>
          <a href="/">{prose.howItWorks.backToGame}</a>
        </p>
      </article>
    </div>
  );
}

export default HowItWorks;
