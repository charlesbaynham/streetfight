// The front page for somebody who is not in the game: they pointed a phone at
// a card taped to a lamppost, or were sent the bare URL. UserMode routes here
// instead of OnboardingView for a user who has never joined anything, so the
// one thing this page must not have is a way in - the people it is written
// for were not invited, and a name box is an invitation whatever it actually
// does on the server.
//
// Also mounted at /what-is-this, so the explanation has a link of its own to
// send somebody. Nothing changes for players: the essay is still reached from
// the outfit picker and the waiting page through CuriosityFooter, and a
// player never sees this page (see isStranger in UserMode.js).

import React from "react";
import { Link } from "react-router-dom";

import logo from "./images/art/logo.png";
import prose from "./prose";
import styles from "./WhatIsThis.module.css";

const p = prose.whatIsThis;

function WhatIsThis() {
  return (
    <div className={styles.outerContainer}>
      <article className={styles.innerContainer}>
        <p className={styles.logo}>
          <img src={logo} alt={p.logoAlt} />
        </p>

        <h1>{p.heading}</h1>

        {p.intro.map((text, index) => (
          <p className={styles.paragraph} key={index}>
            {text}
          </p>
        ))}

        {/* A router Link rather than a new tab, unlike CuriosityFooter's:
            there is no unsaved state on this page to lose by navigating, and
            the essay's own "back to the game" brings them here again. */}
        <p className={styles.mathsLink}>
          <Link to="/how-it-works">{p.mathsLinkText}</Link>
        </p>

        <p className={styles.contact}>
          {p.contact(<a href={`mailto:${p.contactEmail}`}>{p.contactEmail}</a>)}
        </p>
      </article>
    </div>
  );
}

export default WhatIsThis;
