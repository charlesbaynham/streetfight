// The essay page: that the blocks come out in the order prose.js puts them in,
// that the one figure drawn from live data draws it, and that a player who has
// picked an outfit is told which hat and armband they are getting - which is
// the only place in the app that says so.

import React from "react";
import { render, screen } from "@testing-library/react";

import { actAndFlush, installFetchMock, proseFragment } from "./testUtils";

import HowItWorks from "./HowItWorks";
import { FigureCodewordGrid, placeLabels } from "./HowItWorksFigures";
import prose from "./prose";

const y = prose.howItWorks.yourOutfit;

const GRID = {
  size: 7,
  total: 49,
  row_channels: ["tshirt", "trousers"],
  col_channels: ["hat", "armbands"],
  cells: [
    { slot: 0, row: 0, col: 0, usable: false },
    { slot: 1, row: 1, col: 3, usable: true },
    { slot: 2, row: 2, col: 6, usable: true },
  ],
};

const YOU = {
  slot: 1,
  row: 1,
  col: 3,
  name: "Kathia",
  provided: ["hat", "armbands"],
  appearance: {
    tshirt: { colour: "blue", hex: "#0072CE", provided: false },
    trousers: { colour: "olive", hex: "#6B7A3A", provided: false },
    hat: { colour: "burgundy", hex: "#6E2639", provided: true },
    armbands: { colour: "lime", hex: "#A8C832", provided: true },
  },
};

const NEIGHBOUR = {
  distance: 3,
  name: "Dee",
  row: 2,
  col: 6,
  appearance: {
    tshirt: { colour: "red", hex: "#E4002B", provided: false },
    trousers: { colour: "grey", hex: "#808080", provided: false },
    hat: { colour: "navy", hex: "#2D5170", provided: true },
    armbands: { colour: "lime", hex: "#A8C832", provided: true },
  },
};

// The essay has three figures, and two of them are now artwork loaded as image
// files, so the role "img" finds all three. F3 is the only one drawn inline,
// which makes the tag the way to address it. The last one, because a test that
// mounts the page twice wants the figure it has just drawn.
const gridFigure = () =>
  Array.from(document.querySelectorAll("article svg")).pop() ?? null;

function mountWith(payload) {
  installFetchMock({ how_it_works: payload });
  return actAndFlush(() => render(<HowItWorks />));
}

test("renders the essay's blocks in the order prose.js gives them", async () => {
  const original = prose.howItWorks.content;
  prose.howItWorks.content = [
    { type: "paragraph", text: "First paragraph" },
    { type: "figure", figure: "codewordGrid", caption: "How it fits together" },
    { type: "paragraph", text: "Second paragraph" },
  ];

  try {
    await mountWith({ grid: GRID, you: null, neighbours: [] });

    const texts = Array.from(screen.getByRole("article").children).map(
      (el) => el.textContent,
    );
    const caption = texts.findIndex((t) => t.includes("How it fits together"));

    expect(texts.indexOf("First paragraph")).toBeLessThan(caption);
    expect(caption).toBeLessThan(texts.indexOf("Second paragraph"));
  } finally {
    prose.howItWorks.content = original;
  }
});

test("the grid figure draws every codeword, and names the ringed players", async () => {
  await mountWith({ grid: GRID, you: YOU, neighbours: [NEIGHBOUR] });

  const grid = gridFigure();
  // One rect per codeword plus the background field, and a ring plus a name
  // each for the reader and their nearest neighbour.
  expect(grid.querySelectorAll("rect")).toHaveLength(GRID.cells.length + 1);
  expect(grid.querySelectorAll("circle")).toHaveLength(2);
  expect(
    Array.from(grid.querySelectorAll("text")).map((t) => t.textContent),
  ).toEqual(["Kathia", "Dee"]);
});

test("the grid figure is skipped entirely when the request fails", async () => {
  await mountWith({ status: 500 });

  expect(gridFigure()).toBeNull();
});

test("tells a player which hat and armband they will be handed", async () => {
  await mountWith({ grid: GRID, you: YOU, neighbours: [NEIGHBOUR] });

  expect(screen.getByText(proseFragment(y.weHandYou))).toBeInTheDocument();
  expect(screen.getByText(y.garment("hat", "burgundy"))).toBeInTheDocument();
  expect(screen.getByText(y.garment("armbands", "lime"))).toBeInTheDocument();
  expect(screen.getByText(y.garment("tshirt", "blue"))).toBeInTheDocument();
});

test("names who is dressed most like the reader, and how far off they are", async () => {
  await mountWith({
    grid: GRID,
    you: YOU,
    neighbours: [NEIGHBOUR],
    closest_count: 5,
  });

  expect(
    screen.getByText(proseFragment(y.neighboursIntro(3, 5))),
  ).toBeVisible();
  // Twice: once labelling their ring on the grid, once in the list below.
  expect(screen.getAllByText("Dee")).toHaveLength(2);
  expect(screen.getByText(y.apart(3))).toBeInTheDocument();
});

test("a reader who has not picked is invited to, not shown an empty outfit", async () => {
  await mountWith({ grid: GRID, you: null, neighbours: [] });

  expect(screen.getByText(proseFragment(y.noneYet))).toBeInTheDocument();
  expect(screen.queryByText(proseFragment(y.weHandYou))).toBeNull();
});

test("names never overlap, even when two players nearly clash", () => {
  // A near-clash means the two agree on t-shirt and trousers - and the row of
  // the grid *is* the t-shirt and trousers - so they land on the same line a
  // few cells apart, which is exactly when their names would be drawn through
  // each other.
  const entries = [
    {
      key: "you",
      position: { row: 20, col: 10 },
      radius: 2.4,
      text: "Charles",
    },
    {
      key: "n0",
      position: { row: 20, col: 14 },
      radius: 1.4,
      text: "Marcus Quill",
    },
    { key: "n1", position: { row: 20, col: 12 }, radius: 1.4, text: "Dee" },
  ];

  const placed = placeLabels(entries, 49);

  for (let i = 0; i < placed.length; i++) {
    for (let j = i + 1; j < placed.length; j++) {
      const a = placed[i].box;
      const b = placed[j].box;
      const clash = a.x0 < b.x1 && b.x0 < a.x1 && a.y0 < b.y1 && b.y0 < a.y1;
      expect(clash).toBe(false);
    }
  }

  // Whoever had to move gets a line back to their own ring.
  expect(placed.filter((entry) => entry.moved).length).toBeGreaterThan(0);
});

test("a long name near the edge is kept inside the figure", () => {
  const [placed] = placeLabels(
    [
      {
        key: "n0",
        position: { row: 24, col: 47 },
        radius: 1.4,
        text: "Marcus Quill",
      },
    ],
    49,
  );

  expect(placed.box.x1).toBeLessThanOrEqual(51);
  expect(placed.box.x0).toBeGreaterThanOrEqual(-2);
});

test("a name pushed off its ring is drawn with a leader line back to it", async () => {
  // Two players on the same row, two cells apart: there is nowhere beside the
  // second one's ring that does not collide, so its name moves up a line and
  // takes a leader with it.
  const bigGrid = { ...GRID, size: 49, total: 2401 };
  await mountWith({
    grid: bigGrid,
    you: { ...YOU, row: 20, col: 10 },
    neighbours: [{ ...NEIGHBOUR, row: 20, col: 12 }],
  });

  const grid = gridFigure();
  expect(grid.querySelectorAll("line.gridLeader").length).toBeGreaterThan(0);

  const ys = Array.from(grid.querySelectorAll("text")).map((t) =>
    Number(t.getAttribute("y")),
  );
  expect(new Set(ys).size).toBe(ys.length);
});

test("label size is set inline, so the global font-size rule cannot win", () => {
  // index.css sets `* { font-size: 12px }`, and a CSS declaration beats a
  // presentation attribute - which rendered these names four times over-size
  // and spilling out of the figure.
  const { container } = render(
    <FigureCodewordGrid grid={GRID} you={YOU} neighbours={[]} />,
  );

  const label = container.querySelector("text");
  expect(label).toHaveStyle({ fontSize: "2.6px" });
});

test("players wearing something off the codebook get their own mark", async () => {
  await mountWith({
    grid: GRID,
    you: YOU,
    neighbours: [],
    overridden: [
      { row: 4, col: 4 },
      { row: 6, col: 1 },
    ],
  });

  const grid = gridFigure();
  expect(grid.querySelectorAll("rect.gridOverridden")).toHaveLength(2);
  // The lit codewords are untouched by them.
  expect(grid.querySelectorAll("rect.gridCell")).toHaveLength(
    GRID.cells.filter((cell) => cell.usable).length,
  );
});

test("the crosshair runs through the reader, and only when there is one", async () => {
  await mountWith({ grid: GRID, you: YOU, neighbours: [] });

  const crosshair = Array.from(
    gridFigure().querySelectorAll("line.gridCrosshair"),
  );
  expect(crosshair).toHaveLength(2);
  expect(crosshair.map((l) => Number(l.getAttribute("y1")))).toContain(
    YOU.row + 0.5,
  );
  expect(crosshair.map((l) => Number(l.getAttribute("x1")))).toContain(
    YOU.col + 0.5,
  );

  await mountWith({ grid: GRID, you: null, neighbours: [] });
  expect(gridFigure().querySelectorAll("line.gridCrosshair")).toHaveLength(0);
});
