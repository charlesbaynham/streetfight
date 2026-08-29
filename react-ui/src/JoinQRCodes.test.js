import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import JoinQRCodes from "./JoinQRCodes";
import { installFetchMock, getLastAPICall, actAndFlush } from "./testUtils";

const REPORT = {
  team_channel: "hat",
  teams: [
    {
      team_id: "team-burgundy",
      team_name: "Burgundy",
      team_colour: "burgundy",
      team_colour_hex: "#A62C3E",
      capacity: 5,
      encoded_url: "https://example.com?j=burgundy",
    },
    {
      team_id: "team-navy",
      team_name: "Navy",
      team_colour: "navy",
      team_colour_hex: "#2D5170",
      capacity: 4,
      encoded_url: "https://example.com?j=navy",
    },
  ],
};

test("Generate fetches admin_join_qr_codes with game_id only and renders one QR per team", async () => {
  installFetchMock({ admin_join_qr_codes: REPORT });
  const { container } = render(<JoinQRCodes game_id="game-1" />);

  await actAndFlush(() =>
    userEvent.click(screen.getByRole("button", { name: "Generate" })),
  );

  await screen.findByText("Team Burgundy");

  expect(getLastAPICall("admin_join_qr_codes").method).toBe("GET");
  expect(getLastAPICall("admin_join_qr_codes").query).toEqual({
    game_id: "game-1",
  });

  // One QR (react-qr-code renders an svg) per team, not per outfit slot.
  expect(container.querySelectorAll("svg")).toHaveLength(2);
  expect(screen.getByText("Team Navy")).toBeInTheDocument();
});

test("each QR is itself a link to that team's join URL", async () => {
  installFetchMock({ admin_join_qr_codes: REPORT });
  render(<JoinQRCodes game_id="game-1" />);

  await actAndFlush(() =>
    userEvent.click(screen.getByRole("button", { name: "Generate" })),
  );

  const burgundy = await screen.findByRole("link", {
    name: "Join link for team Burgundy",
  });
  expect(burgundy).toHaveAttribute("href", "https://example.com?j=burgundy");
  expect(burgundy.querySelector("svg")).toBeInTheDocument();

  expect(
    screen.getByRole("link", { name: "Join link for team Navy" }),
  ).toHaveAttribute("href", "https://example.com?j=navy");
});

test("each team card names its colour and full-accuracy capacity", async () => {
  installFetchMock({ admin_join_qr_codes: REPORT });
  render(<JoinQRCodes game_id="game-1" />);

  await actAndFlush(() =>
    userEvent.click(screen.getByRole("button", { name: "Generate" })),
  );

  await screen.findByText(/burgundy hats/);
  expect(screen.getByText(/navy hats/)).toBeInTheDocument();
  expect(
    screen.getByText("holds 5 players at full accuracy"),
  ).toBeInTheDocument();
  expect(
    screen.getByText("holds 4 players at full accuracy"),
  ).toBeInTheDocument();
});

test("Print appears once codes are generated and calls window.print", async () => {
  installFetchMock({ admin_join_qr_codes: REPORT });
  render(<JoinQRCodes game_id="game-1" />);

  expect(
    screen.queryByRole("button", { name: "Print" }),
  ).not.toBeInTheDocument();

  await actAndFlush(() =>
    userEvent.click(screen.getByRole("button", { name: "Generate" })),
  );
  await screen.findByText("Team Burgundy");

  window.print = jest.fn();
  userEvent.click(screen.getByRole("button", { name: "Print" }));
  expect(window.print).toHaveBeenCalled();
});
