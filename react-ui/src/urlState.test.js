// The URL-state hooks in src/urlState.js. What is worth pinning down here is
// the merge: every page using these has at least one parameter it must not
// lose - the join code on /pick, the game being worked through on
// /admin/reference - and a patch that rebuilt the query string instead of
// merging into it would drop them silently.

import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";

import { useNavigateKeepingSearch, usePatchSearchParams } from "./urlState";
import { actAndFlush } from "./testUtils";

function Harness({ patch, goTo }) {
  const location = useLocation();
  const patchSearchParams = usePatchSearchParams();
  const navigateKeepingSearch = useNavigateKeepingSearch();

  return (
    <>
      <div data-testid="location">{location.pathname + location.search}</div>
      <button onClick={() => patchSearchParams(patch)}>patch</button>
      <button onClick={() => navigateKeepingSearch(goTo)}>go</button>
    </>
  );
}

async function renderHarness(url, { patch = {}, goTo = "/elsewhere" } = {}) {
  await actAndFlush(() =>
    render(
      <MemoryRouter initialEntries={[url]}>
        <Routes>
          <Route path="/*" element={<Harness patch={patch} goTo={goTo} />} />
        </Routes>
      </MemoryRouter>,
    ),
  );
}

async function press(name) {
  await actAndFlush(() =>
    userEvent.click(screen.getByRole("button", { name })),
  );
}

function currentURL() {
  return screen.getByTestId("location").textContent;
}

test("a patch merges into the query string rather than replacing it", async () => {
  await renderHarness("/pick?j=CODE1&page=2", { patch: { page: 3 } });

  await press("patch");

  expect(currentURL()).toBe("/pick?j=CODE1&page=3");
});

test("a null in the patch deletes that parameter and leaves the rest", async () => {
  await renderHarness("/pick?j=CODE1&page=2&outfit=x", {
    patch: { page: null, outfit: null },
  });

  await press("patch");

  expect(currentURL()).toBe("/pick?j=CODE1");
});

test("an empty string is kept, since it is not the same as an absent parameter", async () => {
  // On /pick this is the difference between "unticked every colour" and
  // "never touched the wardrobe", which is the whole default.
  await renderHarness("/pick?j=CODE1", { patch: { w_tshirt: "" } });

  await press("patch");

  expect(currentURL()).toBe("/pick?j=CODE1&w_tshirt=");
});

test("navigating keeps the query string across the path change", async () => {
  await renderHarness("/admin/reference?game=game-2", {
    goTo: "/admin/reference/user-1",
  });

  await press("go");

  expect(currentURL()).toBe("/admin/reference/user-1?game=game-2");
});
