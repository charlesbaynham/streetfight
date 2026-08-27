import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import JoinQRCodes from "./JoinQRCodes";
import { installFetchMock, getLastAPICall, actAndFlush } from "./testUtils";

const REPORT = {
  team_channel: "hat",
  teams: [
    {
      team_id: "team-red",
      team_name: "Red",
      team_colour: "red",
      team_colour_hex: "#B00020",
      capacity: 5,
      encoded_url: "https://example.com?j=red",
    },
    {
      team_id: "team-blue",
      team_name: "Blue",
      team_colour: "blue",
      team_colour_hex: "#0000FF",
      capacity: 4,
      encoded_url: "https://example.com?j=blue",
    },
  ],
};

test("Generate fetches admin_join_qr_codes with game_id only and renders one QR per team", async () => {
  installFetchMock({ admin_join_qr_codes: REPORT });
  const { container } = render(<JoinQRCodes game_id="game-1" />);

  await actAndFlush(() =>
    userEvent.click(screen.getByRole("button", { name: "Generate" })),
  );

  await screen.findByText("Team Red");

  expect(getLastAPICall("admin_join_qr_codes").method).toBe("GET");
  expect(getLastAPICall("admin_join_qr_codes").query).toEqual({
    game_id: "game-1",
  });

  // One QR (react-qr-code renders an svg) per team, not per outfit slot.
  expect(container.querySelectorAll("svg")).toHaveLength(2);
  expect(screen.getByText("Team Blue")).toBeInTheDocument();
});

test("each team card names its colour and full-accuracy capacity", async () => {
  installFetchMock({ admin_join_qr_codes: REPORT });
  render(<JoinQRCodes game_id="game-1" />);

  await actAndFlush(() =>
    userEvent.click(screen.getByRole("button", { name: "Generate" })),
  );

  await screen.findByText(/red hats/);
  expect(screen.getByText(/blue hats/)).toBeInTheDocument();
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
  await screen.findByText("Team Red");

  window.print = jest.fn();
  userEvent.click(screen.getByRole("button", { name: "Print" }));
  expect(window.print).toHaveBeenCalled();
});
