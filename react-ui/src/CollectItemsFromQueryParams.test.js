import React from "react";
import { render, screen, act } from "@testing-library/react";
import { MemoryRouter, useLocation } from "react-router-dom";

import CollectItemFromQueryParam from "./CollectItemsFromQueryParams";
import { installFetchMock, getAPICalls } from "./testUtils";

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
