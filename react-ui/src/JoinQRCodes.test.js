import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import JoinQRCodes from "./JoinQRCodes";
import { installFetchMock, getLastAPICall, actAndFlush } from "./testUtils";

const REPORT = {
  team_channel: "hat",
  game_url: "https://example.com?j=game",
  teams: [
    {
      team_id: "team-burgundy",
      team_name: "Burgundy",
      team_colour: "burgundy",
      team_colour_hex: "#A62C3E",
      encoded_url: "https://example.com?j=burgundy",
    },
    {
      team_id: "team-navy",
      team_name: "Navy",
      team_colour: "navy",
      team_colour_hex: "#2D5170",
      encoded_url: "https://example.com?j=navy",
    },
  ],
};

async function generate() {
  await actAndFlush(() =>
    userEvent.click(screen.getByRole("button", { name: "Generate" })),
  );
  await screen.findByText("Team Burgundy");
}

test("Generate fetches admin_join_qr_codes with game_id only and renders the sign-up QR plus one per team", async () => {
  installFetchMock({ admin_join_qr_codes: REPORT });
  const { container } = render(<JoinQRCodes game_id="game-1" />);

  await generate();

  expect(getLastAPICall("admin_join_qr_codes").method).toBe("GET");
  expect(getLastAPICall("admin_join_qr_codes").query).toEqual({
    game_id: "game-1",
  });

  // One QR (react-qr-code renders an svg) for the sign-up link and one per
  // team, not per outfit slot.
  expect(container.querySelectorAll("svg")).toHaveLength(3);
  expect(screen.getByText("Sign up")).toBeInTheDocument();
  expect(screen.getByText("Team Navy")).toBeInTheDocument();
});

test("the sign-up link is its own card, sent to everyone", async () => {
  installFetchMock({ admin_join_qr_codes: REPORT });
  render(<JoinQRCodes game_id="game-1" />);

  await generate();

  expect(
    screen.getByText("Sign-up link - send this to everyone"),
  ).toBeInTheDocument();
  expect(
    screen.getByRole("link", { name: "Join link for the game" }),
  ).toHaveAttribute("href", "https://example.com?j=game");
  expect(screen.getByLabelText("Join link text for the game")).toHaveValue(
    "https://example.com?j=game",
  );
});

test("each team QR is itself a link to that team's join URL", async () => {
  installFetchMock({ admin_join_qr_codes: REPORT });
  render(<JoinQRCodes game_id="game-1" />);

  await generate();

  const burgundy = screen.getByRole("link", {
    name: "Join link for team Burgundy",
  });
  expect(burgundy).toHaveAttribute("href", "https://example.com?j=burgundy");
  expect(burgundy.querySelector("svg")).toBeInTheDocument();

  expect(
    screen.getByRole("link", { name: "Join link for team Navy" }),
  ).toHaveAttribute("href", "https://example.com?j=navy");
});

test("each card shows the join link as visible, selectable text alongside the QR code", async () => {
  installFetchMock({ admin_join_qr_codes: REPORT });
  render(<JoinQRCodes game_id="game-1" />);

  await generate();

  const burgundyLinkText = screen.getByLabelText(
    "Join link text for team Burgundy",
  );
  expect(burgundyLinkText).toHaveValue("https://example.com?j=burgundy");
  expect(burgundyLinkText).toHaveAttribute("readonly");

  expect(screen.getByLabelText("Join link text for team Navy")).toHaveValue(
    "https://example.com?j=navy",
  );
});

test("Copy writes that card's join link to the clipboard", async () => {
  installFetchMock({ admin_join_qr_codes: REPORT });
  const writeText = jest.fn();
  Object.defineProperty(window.navigator, "clipboard", {
    configurable: true,
    value: { writeText },
  });
  render(<JoinQRCodes game_id="game-1" />);

  await generate();

  const copyButtons = screen.getAllByRole("button", { name: "Copy" });
  userEvent.click(copyButtons[0]);
  expect(writeText).toHaveBeenCalledWith("https://example.com?j=game");

  userEvent.click(copyButtons[1]);
  expect(writeText).toHaveBeenCalledWith("https://example.com?j=burgundy");
});

test("the team cards PDF link targets the route for this game", async () => {
  installFetchMock({ admin_join_qr_codes: REPORT });
  render(<JoinQRCodes game_id="game-1" />);

  expect(
    screen.queryByRole("link", { name: "Download team cards (PDF)" }),
  ).not.toBeInTheDocument();

  await generate();

  expect(
    screen.getByRole("link", { name: "Download team cards (PDF)" }),
  ).toHaveAttribute("href", "/api/admin_team_cards_pdf?game_id=game-1");
});

test("Print appears once codes are generated and calls window.print", async () => {
  installFetchMock({ admin_join_qr_codes: REPORT });
  render(<JoinQRCodes game_id="game-1" />);

  expect(
    screen.queryByRole("button", { name: "Print" }),
  ).not.toBeInTheDocument();

  await generate();

  window.print = jest.fn();
  userEvent.click(screen.getByRole("button", { name: "Print" }));
  expect(window.print).toHaveBeenCalled();
});
