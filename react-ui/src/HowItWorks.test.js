import React from "react";
import { render, screen } from "@testing-library/react";

import HowItWorks from "./HowItWorks";
import prose from "./prose";

test("renders each content block in order, paragraphs and diagrams alike", () => {
  const original = prose.howItWorks.content;
  prose.howItWorks.content = [
    { type: "paragraph", text: "First paragraph" },
    {
      type: "diagram",
      node: <img src="diagram.png" alt="A diagram" />,
      caption: "How it fits together",
    },
    { type: "paragraph", text: "Second paragraph" },
  ];

  try {
    render(<HowItWorks />);

    const blocks = screen.getByRole("article").children;
    const texts = Array.from(blocks).map((el) => el.textContent);

    expect(texts.indexOf("First paragraph")).toBeGreaterThanOrEqual(0);
    expect(texts.indexOf("First paragraph")).toBeLessThan(
      texts.findIndex((t) => t.includes("How it fits together")),
    );
    expect(
      texts.findIndex((t) => t.includes("How it fits together")),
    ).toBeLessThan(texts.indexOf("Second paragraph"));

    expect(screen.getByAltText("A diagram")).toBeInTheDocument();
    expect(screen.getByText("How it fits together")).toBeInTheDocument();
  } finally {
    prose.howItWorks.content = original;
  }
});
