// The essay's figures (react-ui/src/HowItWorks.js).
//
// Two of the three are pictures of people and cannot be computed, so they are
// drawn artwork, delivered as self-contained SVGs and loaded like any other
// image in the app. The third is a picture of the *scheme* and is therefore
// drawn from what the backend says the scheme currently is
// (GET /api/how_it_works): a palette edit or a change to the code's parameters
// must not be able to leave a published essay lying about what the players are
// wearing.
//
// The two artwork files are 320 px wide with a viewBox, so they scale to the
// column; they are dark-on-transparent because the page behind them is black.
// Their text is real `<text>`, which is why they are worth keeping as SVG
// rather than flattening. Redrawing one means replacing the file - the
// caption, the ordering and the figure frame all live in HowItWorks.js /
// prose.js, and the brief each was drawn to is in
// docs/how_it_works_figures.md.

import React from "react";

import prose from "./prose";
import cameraReadArt from "./images/essay/f1-camera-read.svg";
import spotTheDifferenceArt from "./images/essay/f2-spot-the-difference.svg";
import { Swatch } from "./Swatch";
import styles from "./HowItWorks.module.css";

const p = prose.howItWorks;

// F1. A real shot photograph, what CharlesBot read off it, and who it decided
// that was - the reframe the whole essay rests on: the computer is not
// recognising a face, it is reading four colours.
export function FigureCameraRead() {
  return (
    <img
      className={styles.artwork}
      src={cameraReadArt}
      alt={p.figures.cameraRead.alt}
    />
  );
}

// F2. Two players a single garment apart, and the same pair as the scheme
// actually assigns them. The problem and the solution in one picture.
export function FigureSpotTheDifference() {
  return (
    <img
      className={styles.artwork}
      src={spotTheDifferenceArt}
      alt={p.figures.spotTheDifference.alt}
    />
  );
}

// Label geometry for F3, in grid units. The font size lives here rather than
// in the stylesheet because the placement below has to measure the text, and
// two sources of truth for it would drift.
const LABEL_SIZE = 2.6;
const LINE = LABEL_SIZE * 1.25;
const CHAR = LABEL_SIZE * 0.58; // a sans-serif character's rough advance width

function overlaps(a, b) {
  return a.x0 < b.x1 && b.x0 < a.x1 && a.y0 < b.y1 && b.y0 < a.y1;
}

function labelBox(x, y, text, anchor) {
  const width = CHAR * text.length;
  return {
    x0: anchor === "start" ? x : x - width,
    x1: anchor === "start" ? x + width : x,
    y0: y - LINE / 2,
    y1: y + LINE / 2,
  };
}

// Where each name goes, so that no two names and no name and ring collide.
//
// This is needed precisely when the figure matters most. Two players whose
// outfits nearly clash agree on their t-shirt and trousers, and the row of the
// grid *is* the t-shirt and trousers - so a near-clash puts them on the same
// line, a few cells apart, and their names would be drawn straight through
// each other. Leaving the labels where the rings are is fine until the moment
// a reader needs to tell two close players apart.
//
// Greedy, and only ever a handful of labels: take the natural side, then nudge
// a line at a time up and down, then try the other side, and take the first
// placement that hits nothing already placed. Anything that finds no room at
// all keeps its natural spot rather than vanishing.
export function placeLabels(entries, size) {
  const taken = entries.map(({ position, radius }) => ({
    x0: position.col + 0.5 - radius,
    x1: position.col + 0.5 + radius,
    y0: position.row + 0.5 - radius,
    y1: position.row + 0.5 + radius,
  }));

  return entries.map((entry) => {
    const { position, radius, text } = entry;
    const cx = position.col + 0.5;
    const cy = position.row + 0.5;
    const sides = position.col > size / 2 ? ["end", "start"] : ["start", "end"];
    const at = (anchor, dy) => {
      const x = cx + (anchor === "start" ? radius + 1 : -radius - 1);
      const y = cy + dy;
      return { ...entry, cx, cy, x, y, anchor, moved: dy !== 0 };
    };

    let placed = null;
    for (const dy of [0, -LINE, LINE, -2 * LINE, 2 * LINE]) {
      for (const anchor of sides) {
        const candidate = at(anchor, dy);
        const box = labelBox(candidate.x, candidate.y, text, anchor);
        // Inside the viewBox on both axes: a name that runs off the right
        // edge is as unreadable as one drawn through another.
        if (box.y0 < -2 || box.y1 > size + 2) continue;
        if (box.x0 < -2 || box.x1 > size + 2) continue;
        if (taken.some((other) => overlaps(box, other))) continue;
        placed = { ...candidate, box };
        break;
      }
      if (placed) break;
    }
    if (!placed) {
      const fallback = at(sides[0], 0);
      placed = {
        ...fallback,
        box: labelBox(fallback.x, fallback.y, text, fallback.anchor),
      };
    }

    taken.push(placed.box);
    return placed;
  });
}

// F3. Every possible outfit as one cell of a square: the row says what the
// player picked (t-shirt, trousers), the column says what we hand them (hat,
// armband). The scheme's codewords are lit, and they fall exactly one to a
// row and one to a column - the visible consequence of any two garments
// determining the other two.
//
// Drawn in grid units (0..size) with a viewBox, so it scales to the column
// width without any of the geometry knowing about pixels.
export function FigureCodewordGrid({ grid, you, neighbours, overridden }) {
  if (!grid) return null;

  const { size, cells } = grid;
  const garments = (names) => names.map(p.yourOutfit.garmentName).join(" + ");

  const sited = (position) => position.row !== null && position.col !== null;
  // The reader's ring is bigger than a neighbour's, so which is which survives
  // being looked at on a phone. The reader is placed first, so a crowded
  // corner moves somebody else's name rather than theirs.
  const marked = [
    ...(you && sited(you)
      ? [
          {
            key: "you",
            position: you,
            radius: 2.4,
            text: p.figures.codewordGrid.youLabel(you.name),
            ringClass: styles.gridYou,
            labelClass: styles.gridLabelYou,
          },
        ]
      : []),
    ...(neighbours || []).filter(sited).map((neighbour, index) => ({
      key: `n${index}`,
      position: neighbour,
      radius: 1.4,
      text: p.yourOutfit.neighbourName(neighbour.name),
      ringClass: styles.gridNeighbour,
      labelClass: styles.gridLabel,
    })),
  ];
  const labels = placeLabels(marked, size);

  return (
    <>
      <p className={styles.gridAxes}>
        <span>
          {p.figures.codewordGrid.across(garments(grid.col_channels))}
        </span>
        <span>{p.figures.codewordGrid.down(garments(grid.row_channels))}</span>
      </p>
      <svg
        className={styles.grid}
        viewBox={`-2 -2 ${size + 4} ${size + 4}`}
        role="img"
        aria-label={p.figures.codewordGrid.alt(cells.length, grid.total)}
      >
        <rect
          className={styles.gridField}
          x={-2}
          y={-2}
          width={size + 4}
          height={size + 4}
        />
        {/* Where the reader sits, carried right across the figure: the row
            is everyone sharing their t-shirt and trousers, the column
            everyone sharing their hat and armband. Under the cells, so it
            guides the eye without competing with them. */}
        {you && you.row !== null && you.col !== null ? (
          <>
            <line
              className={styles.gridCrosshair}
              x1={-2}
              y1={you.row + 0.5}
              x2={size + 2}
              y2={you.row + 0.5}
            />
            <line
              className={styles.gridCrosshair}
              x1={you.col + 0.5}
              y1={-2}
              x2={you.col + 0.5}
              y2={size + 2}
            />
          </>
        ) : null}
        {cells.map((cell) => (
          <rect
            key={cell.slot}
            className={cell.usable ? styles.gridCell : styles.gridCellWithheld}
            x={cell.col + 0.15}
            y={cell.row + 0.15}
            width={0.7}
            height={0.7}
          />
        ))}
        {/* Players wearing something the codebook never offered. They are off
            the constellation by construction, so they get their own colour
            rather than being drawn as though they were codewords. */}
        {(overridden || []).map((entry) => (
          <rect
            key={`o-${entry.row}-${entry.col}`}
            className={styles.gridOverridden}
            x={entry.col + 0.15}
            y={entry.row + 0.15}
            width={0.7}
            height={0.7}
          />
        ))}
        {labels.map((entry) => (
          <circle
            key={entry.key}
            className={entry.ringClass}
            cx={entry.cx}
            cy={entry.cy}
            r={entry.radius}
          />
        ))}
        {/* A name that had to be nudged gets a line back to its ring, so a
            reader is never left guessing which dot it belongs to. */}
        {labels
          .filter((entry) => entry.moved)
          .map((entry) => (
            <line
              key={`${entry.key}-leader`}
              className={`${styles.gridLeader} ${entry.labelClass}`}
              x1={entry.cx + (entry.anchor === "start" ? 1 : -1) * entry.radius}
              y1={entry.cy}
              x2={entry.x}
              y2={entry.y}
            />
          ))}
        {labels.map((entry) => (
          <text
            key={`${entry.key}-label`}
            className={entry.labelClass}
            x={entry.x}
            y={entry.y}
            // An inline style, not a font-size attribute: index.css's global
            // `* { font-size: 12px }` is a CSS declaration and beats any
            // presentation attribute, which rendered these names four times
            // over-size and out of the figure.
            style={{ fontSize: `${LABEL_SIZE}px` }}
            textAnchor={entry.anchor}
            dominantBaseline="middle"
          >
            {entry.text}
          </text>
        ))}
      </svg>
    </>
  );
}

// The reward for reading this far: the two garments we will hand the reader at
// the door, which they have not been told anywhere else, and who in their game
// is dressed most like them.
export function YourOutfit({ you, neighbours, closestCount }) {
  if (!you) return <p className={styles.hint}>{p.yourOutfit.noneYet}</p>;

  const entries = Object.entries(you.appearance);
  const provided = entries.filter(([, entry]) => entry.provided);
  const chosen = entries.filter(([, entry]) => !entry.provided);

  return (
    <div className={styles.yourOutfit}>
      <h2>{p.yourOutfit.heading}</h2>
      <OutfitRow label={p.yourOutfit.weHandYou} entries={provided} />
      <OutfitRow label={p.yourOutfit.youPicked} entries={chosen} />
      {neighbours && neighbours.length > 0 ? (
        <>
          <h2>{p.yourOutfit.neighboursHeading}</h2>
          <p>
            {p.yourOutfit.neighboursIntro(
              neighbours[0].distance,
              closestCount || neighbours.length,
            )}
          </p>
          <ul className={styles.neighbours}>
            {neighbours.map((neighbour, index) => (
              <li key={index} className={styles.neighbour}>
                <Garments appearance={neighbour.appearance} />
                <span className={styles.neighbourName}>
                  {p.yourOutfit.neighbourName(neighbour.name)}
                </span>
                <span className={styles.neighbourDistance}>
                  {p.yourOutfit.apart(neighbour.distance)}
                </span>
              </li>
            ))}
          </ul>
        </>
      ) : null}
    </div>
  );
}

function OutfitRow({ label, entries }) {
  if (entries.length === 0) return null;
  return (
    <p className={styles.outfitRow}>
      <span className={styles.outfitLabel}>{label}</span>
      {entries.map(([name, entry]) => (
        <span key={name} className={styles.garment}>
          <Swatch hex={entry.hex} label={entry.colour} />
          {p.yourOutfit.garment(name, entry.colour)}
        </span>
      ))}
    </p>
  );
}

function Garments({ appearance }) {
  return (
    <span className={styles.garmentStrip}>
      {Object.entries(appearance).map(([name, entry]) => (
        <Swatch
          key={name}
          hex={entry.hex}
          label={`${name}: ${entry.colour || "-"}`}
          small
        />
      ))}
    </span>
  );
}
