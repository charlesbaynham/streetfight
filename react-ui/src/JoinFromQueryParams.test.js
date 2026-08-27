import React from "react";
import { render, screen, act } from "@testing-library/react";
import { MemoryRouter, useLocation } from "react-router-dom";

import JoinFromQueryParams from "./JoinFromQueryParams";
import { installFetchMock, getAPICalls } from "./testUtils";

// Renders the current router location so navigation triggered by the
// component under test (navigate("/") after a join attempt) is observable.
function LocationDisplay() {
  const location = useLocation();
  return (
    <div data-testid="location">{location.pathname + location.search}</div>
  );
}

function renderWithRouter(initialEntry) {
  return render(
    <MemoryRouter initialEntries={[initialEntry]}>
      <JoinFromQueryParams />
      <LocationDisplay />
    </MemoryRouter>,
  );
}

test("posts join_game with the code after the debounce, then navigates to /", async () => {
  installFetchMock({ join_game: { team_name: "Red" } });
  renderWithRouter("/somewhere?j=ABC123");

  await screen.findByText("/");

  const calls = getAPICalls("join_game");
  expect(calls).toHaveLength(1);
  expect(calls[0].method).toBe("POST");
  expect(calls[0].body).toEqual({ data: "ABC123" });
});

test("a needs_pick response navigates to /pick carrying the same code", async () => {
  installFetchMock({
    join_game: { needs_pick: true, team_id: "team-1", team_name: "Reds" },
  });
  renderWithRouter("/somewhere?j=ABC123");

  await screen.findByText("/pick?j=ABC123");
});

test("an error response shows the backend's detail text and still navigates to /", async () => {
  installFetchMock({
    join_game: {
      status: 400,
      body: { detail: "slot 3 is already used by Bob" },
    },
  });
  renderWithRouter("/somewhere?j=ABC123");

  await screen.findByText("/");
  expect(
    await screen.findByText("slot 3 is already used by Bob"),
  ).toBeInTheDocument();
});

test("an error response without a detail shows a generic message", async () => {
  installFetchMock({ join_game: { status: 500, body: null } });
  renderWithRouter("/somewhere?j=ABC123");

  await screen.findByText("/");
  expect(
    await screen.findByText("Could not join the game"),
  ).toBeInTheDocument();
});

test("does not fire when the j param is absent", () => {
  jest.useFakeTimers();
  installFetchMock({ join_game: {} });
  renderWithRouter("/somewhere");

  act(() => {
    jest.advanceTimersByTime(500);
  });

  expect(getAPICalls("join_game")).toHaveLength(0);
  jest.useRealTimers();
});

test("unmounting before the debounce elapses cancels the request", () => {
  jest.useFakeTimers();
  installFetchMock({ join_game: {} });
  const { unmount } = renderWithRouter("/somewhere?j=ABC123");

  act(() => {
    jest.advanceTimersByTime(50);
  });
  unmount();

  act(() => {
    jest.advanceTimersByTime(500);
  });

  expect(getAPICalls("join_game")).toHaveLength(0);
  jest.useRealTimers();
});
