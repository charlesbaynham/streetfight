import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

import WhatIsThis from "./WhatIsThis";
import prose from "./prose";

// Only the wiring is worth asserting here - the page is otherwise prose, and
// a test that repeats the words back has no behaviour in it. What can break
// is where the two links point, and the thing the page exists to *not* have.

function renderPage() {
  return render(
    <MemoryRouter>
      <WhatIsThis />
    </MemoryRouter>,
  );
}

test("offers the essay and a way to contact Charles", () => {
  renderPage();

  expect(
    screen.getByRole("link", { name: prose.whatIsThis.mathsLinkText }),
  ).toHaveAttribute("href", "/how-it-works");

  expect(
    screen.getByRole("link", { name: prose.whatIsThis.contactEmail }),
  ).toHaveAttribute("href", `mailto:${prose.whatIsThis.contactEmail}`);
});

test("gives a reader no way into a game", () => {
  renderPage();

  // No name box, no join button: this page is addressed to somebody who was
  // not invited, and an affordance that looks like a way in is an invitation
  // whatever it does on the server.
  expect(screen.queryByRole("textbox")).not.toBeInTheDocument();
  expect(screen.queryByRole("button")).not.toBeInTheDocument();
  expect(
    screen.queryByPlaceholderText(prose.onboardingView.namePlaceholder),
  ).not.toBeInTheDocument();
});
