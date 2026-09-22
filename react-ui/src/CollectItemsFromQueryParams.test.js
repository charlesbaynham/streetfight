import React from "react";
import { render, screen, act, waitFor } from "@testing-library/react";
import { MemoryRouter, useLocation } from "react-router-dom";

import CollectItemFromQueryParam from "./CollectItemsFromQueryParams";
import prose from "./prose";
import { clearRefusal, getRefusal, reportRefusal } from "./refusalStore";
import { installFetchMock, getAPICalls } from "./testUtils";

beforeEach(clearRefusal);
afterEach(clearRefusal);

// Renders the current router location so navigation triggered by the
// component under test (navigate("/") after a successful collection) is
// observable.
function LocationDisplay() {
  const location = useLocation();
  return (
    <div data-testid="location">{location.pathname + location.search}</div>
  );
}

function renderWithRouter(initialEntry, enabled) {
  return render(
    <MemoryRouter initialEntries={[initialEntry]}>
      <CollectItemFromQueryParam enabled={enabled} />
      <LocationDisplay />
    </MemoryRouter>,
  );
}

test("posts collect_item with the code after the debounce, then navigates to /", async () => {
  installFetchMock({ collect_item: { ok: true } });
  renderWithRouter("/somewhere?d=ABC123", true);

  await screen.findByText("/");

  const calls = getAPICalls("collect_item");
  expect(calls).toHaveLength(1);
  expect(calls[0].method).toBe("POST");
  expect(calls[0].body).toEqual({ data: "ABC123" });
});

test("does not fire when the d param is absent", () => {
  jest.useFakeTimers();
  installFetchMock({ collect_item: { ok: true } });
  renderWithRouter("/somewhere", true);

  act(() => {
    jest.advanceTimersByTime(500);
  });

  expect(getAPICalls("collect_item")).toHaveLength(0);
  jest.useRealTimers();
});

test("does not fire when disabled", () => {
  jest.useFakeTimers();
  installFetchMock({ collect_item: { ok: true } });
  renderWithRouter("/somewhere?d=ABC123", false);

  act(() => {
    jest.advanceTimersByTime(500);
  });

  expect(getAPICalls("collect_item")).toHaveLength(0);
  jest.useRealTimers();
});

test("unmounting before the debounce elapses cancels the request", () => {
  jest.useFakeTimers();
  installFetchMock({ collect_item: { ok: true } });
  const { unmount } = renderWithRouter("/somewhere?d=ABC123", true);

  act(() => {
    jest.advanceTimersByTime(50);
  });
  unmount();

  act(() => {
    jest.advanceTimersByTime(500);
  });

  expect(getAPICalls("collect_item")).toHaveLength(0);
  jest.useRealTimers();
});

// A card opened with the phone's own camera used to end the same way whatever
// the game said about it: a line in a console nobody can see, and a navigate
// home. From the street a withdrawn card and a collected one were identical.

test("a refused card says why, instead of going quietly home", async () => {
  installFetchMock({
    collect_item: {
      status: 403,
      body: { detail: "This code has been withdrawn" },
    },
  });
  renderWithRouter("/somewhere?d=withdrawn-card", true);

  await waitFor(() => expect(getRefusal()).not.toBeNull());
  expect(getRefusal().message).toBe(
    prose.qrScanner.scanRefused("This code has been withdrawn"),
  );
  await screen.findByText("/");
});

test("a card that is collected clears a refusal still on screen", async () => {
  installFetchMock({ collect_item: { ok: true } });
  reportRefusal("something older");
  renderWithRouter("/somewhere?d=good-card", true);

  await waitFor(() => expect(getRefusal()).toBeNull());
});
