// The "interested in what's happening here?" destination, linked from the
// bottom of the outfit picker. Read-only and a dead end: nothing a player can
// break by landing on it mid-flow (which is why the footer opens it in a new
// tab - the picker's wardrobe selections are React state and would not survive
// a navigation).
//
// The one request it makes is GET /api/how_it_works, which carries the scheme
// the figures are drawn from and, for a reader who has already picked, their
// own outfit and their nearest neighbours. It is fetched rather than bundled
// so that the essay cannot outlive the scheme it describes; the essay still
// reads correctly if the request fails, minus the two figures that need it.

import React from "react";
import { useEffect } from "react";
import { useState } from "react";

import prose from "./prose";
import styles from "./HowItWorks.module.css";
import { FigureCameraRead } from "./HowItWorksFigures";
import { FigureCodewordGrid } from "./HowItWorksFigures";
import { FigureSpotTheDifference } from "./HowItWorksFigures";
import { YourOutfit } from "./HowItWorksFigures";
import { sendAPIRequest } from "./utils";

const p = prose.howItWorks;

// Which component a `{type: "figure", figure: ...}` block renders. The essay
// orders the figures; this decides what they are, so prose.js stays prose.
const FIGURES = {
  cameraRead: () => <FigureCameraRead />,
  spotTheDifference: () => <FigureSpotTheDifference />,
  codewordGrid: (data) => (
    <FigureCodewordGrid
      grid={data.grid}
      you={data.you}
      neighbours={data.neighbours}
      overridden={data.overridden}
    />
  ),
};

function HowItWorksBlock({ block, data }) {
  if (block.type !== "figure")
    return <p className={styles.paragraph}>{block.text}</p>;

  const node = FIGURES[block.figure](data);
  if (!node) return null;

  return (
    <figure className={styles.diagram}>
      {node}
      {block.caption ? <figcaption>{block.caption}</figcaption> : null}
    </figure>
  );
}

function HowItWorks() {
  const [data, setData] = useState({
    grid: null,
    you: null,
    neighbours: [],
    closest_count: 0,
    overridden: [],
  });

  useEffect(() => {
    sendAPIRequest("how_it_works", null, "GET", (body) => setData(body));
  }, []);

  return (
    <div className={styles.outerContainer}>
      <article className={styles.innerContainer}>
        <h1>{p.heading}</h1>

        {p.content.map((block, index) => (
          <HowItWorksBlock key={index} block={block} data={data} />
        ))}

        <YourOutfit
          you={data.you}
          neighbours={data.neighbours}
          closestCount={data.closest_count}
        />

        <p className={styles.backNote}>
          <a href="/">{p.backToGame}</a>
        </p>
      </article>
    </div>
  );
}

export default HowItWorks;
