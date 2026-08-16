import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import JoinQRCodes from "./JoinQRCodes";
import { installFetchMock, getLastAPICall } from "./testUtils";

const REPORT = {
  team_channel: "hat",
  teams: [
    {
      team_id: "team-red",
      team_name: "Red",
      team_colours: ["purple"],
      codes: [
        {
          slot: 7,
          encoded_url: "https://example.com?j=red7",
          appearance: { tshirt: "red", trousers: "black" },
        },
        {
          slot: 9,
          encoded_url: "https://example.com?j=red9",
          appearance: { tshirt: "red", trousers: "white" },
        },
      ],
    },
    {
      team_id: "team-blue",
      team_name: "Blue",
      team_colours: ["green", "yellow"],
      codes: [
        {
          slot: 11,
          encoded_url: "https://example.com?j=blue11",
          appearance: { tshirt: "blue", trousers: "black" },
        },
      ],
    },
  ],
};

test("Generate fetches admin_join_qr_codes and renders one QR per code with captions", async () => {
  installFetchMock({ admin_join_qr_codes: REPORT });
  const { container } = render(<JoinQRCodes game_id="game-1" />);

  userEvent.click(screen.getByRole("button", { name: "Generate" }));

  await screen.findByText("Team Red — outfit #7");

  expect(getLastAPICall("admin_join_qr_codes").method).toBe("GET");
  expect(getLastAPICall("admin_join_qr_codes").query).toEqual({
    game_id: "game-1",
    slots_per_team: "8",
  });

  // One QR (react-qr-code renders an svg) per code across both teams
  expect(container.querySelectorAll("svg")).toHaveLength(3);
  expect(screen.getByText("Team Red — outfit #9")).toBeInTheDocument();
  expect(screen.getByText("Team Blue — outfit #11")).toBeInTheDocument();

  // The appearance is listed channel by channel
  expect(screen.getByText("tshirt: blue")).toBeInTheDocument();
  expect(screen.getAllByText("trousers: black")).toHaveLength(2);
});

test("each team heading names the colour its whole team wears", async () => {
  installFetchMock({ admin_join_qr_codes: REPORT });
  render(<JoinQRCodes game_id="game-1" />);

  userEvent.click(screen.getByRole("button", { name: "Generate" }));

  // One colour for the whole team...
  await screen.findByText(/purple hats/);
  // ...and a team too big for one colour says which comes next
  expect(screen.getByText(/hats: green then yellow/)).toBeInTheDocument();
});

test("the slots-per-team input feeds the request", async () => {
  installFetchMock({ admin_join_qr_codes: REPORT });
  render(<JoinQRCodes game_id="game-1" />);

  const input = screen.getByLabelText(/Slots per team/);
  userEvent.clear(input);
  userEvent.type(input, "4");
  userEvent.click(screen.getByRole("button", { name: "Generate" }));

  await waitFor(() =>
    expect(getLastAPICall("admin_join_qr_codes")).toBeDefined(),
  );
  expect(getLastAPICall("admin_join_qr_codes").query).toEqual({
    game_id: "game-1",
    slots_per_team: "4",
  });
});

test("Print appears once codes are generated and calls window.print", async () => {
  installFetchMock({ admin_join_qr_codes: REPORT });
  render(<JoinQRCodes game_id="game-1" />);

  expect(
    screen.queryByRole("button", { name: "Print" }),
  ).not.toBeInTheDocument();

  userEvent.click(screen.getByRole("button", { name: "Generate" }));
  await screen.findByText("Team Red — outfit #7");

  window.print = jest.fn();
  userEvent.click(screen.getByRole("button", { name: "Print" }));
  expect(window.print).toHaveBeenCalled();
});
