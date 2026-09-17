import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { PrintablesPanel } from "./AdminPrintables";
import {
  installFetchMock,
  getLastAPICall,
  actAndFlush,
  makeGame,
} from "./testUtils";

const GAMES = [makeGame({ id: "game-1" })];

function renderPage() {
  installFetchMock({
    admin_list_games: GAMES,
    admin_game_join_url: { game_url: "https://example.com/?j=signup" },
    admin_team_cards_pdf: "%PDF-fake",
    admin_pub_pages_pdf: "%PDF-fake",
    admin_item_sheets_pdf: "%PDF-fake",
  });
  render(<PrintablesPanel />);
}

// Each printable is its own labelled panel, so a query says which one it means
// - three of them have a button that builds a PDF.
function panel(name) {
  return within(screen.getByRole("region", { name: name }));
}

async function press(name, buttonName) {
  await actAndFlush(() =>
    userEvent.click(panel(name).getByRole("button", { name: buttonName })),
  );
}

test("the team cards download names the selected game and has no side effects", async () => {
  renderPage();
  await actAndFlush(() => {});

  await press("Team cards", "Download team cards (PDF)");

  const call = getLastAPICall("admin_team_cards_pdf");
  expect(call.method).toBe("GET");
  expect(call.query).toEqual({ game_id: "game-1" });
});

test("minting pub certificates posts the page count and the bullets each is worth", async () => {
  renderPage();

  await press("Pub certificates", "Mint and download (PDF)");

  const call = getLastAPICall("admin_pub_pages_pdf");
  expect(call.method).toBe("POST");
  expect(call.query).toEqual({ count: "6", num_bullets: "5" });
});

test("minting drop cards posts the whole item definition", async () => {
  renderPage();

  await press("Drop cards", "Mint and download (PDF)");

  const call = getLastAPICall("admin_item_sheets_pdf");
  expect(call.method).toBe("POST");
  expect(call.query).toEqual({
    itype: "ammo",
    num: "5",
    sheets: "1",
    damage: "1",
    timeout: "25",
    collected_only_once: "true",
    collected_as_team: "false",
  });
});

test("a failed build says so rather than leaving the button looking pressed", async () => {
  installFetchMock({
    admin_list_games: GAMES,
    admin_pub_pages_pdf: { status: 400, body: "no" },
  });
  render(<PrintablesPanel />);

  await press("Pub certificates", "Mint and download (PDF)");

  expect(
    panel("Pub certificates").getByText("Failed (400)"),
  ).toBeInTheDocument();
});

test("a weapon card asks for damage and rate of fire; ammo does not", async () => {
  renderPage();
  const drops = panel("Drop cards");

  expect(drops.queryByLabelText("Damage per shot")).not.toBeInTheDocument();

  await actAndFlush(() =>
    userEvent.selectOptions(drops.getByLabelText("Item"), "weapon"),
  );

  expect(
    panel("Drop cards").getByLabelText("Damage per shot"),
  ).toBeInTheDocument();
});

test("only ammo can be collected for a whole team", async () => {
  renderPage();

  expect(
    panel("Drop cards").getByLabelText(/Collected for the whole team/),
  ).not.toBeDisabled();

  await actAndFlush(() =>
    userEvent.selectOptions(
      panel("Drop cards").getByLabelText("Item"),
      "medpack",
    ),
  );

  // item_actions._ACTIONS has no team handler for anything but ammo, so a card
  // asking for one would raise on the first scan.
  expect(
    panel("Drop cards").getByLabelText(/Collected for the whole team/),
  ).toBeDisabled();
});

test("the panel says how many codes a press mints, so a second press is a choice", async () => {
  renderPage();

  expect(
    panel("Drop cards").getByText("Mints 8 new codes when you press this."),
  ).toBeInTheDocument();

  await actAndFlush(() =>
    userEvent.clear(panel("Drop cards").getByLabelText(/^Sheets/)),
  );
  await actAndFlush(() =>
    userEvent.type(panel("Drop cards").getByLabelText(/^Sheets/), "3"),
  );

  expect(
    panel("Drop cards").getByText("Mints 24 new codes when you press this."),
  ).toBeInTheDocument();
});

// The sign-up link goes out over WhatsApp, so what the page owes is a link to
// paste and a QR to scan off another screen - not a PDF.
test("the sign-up link panel shows the game's join URL as text and as a QR", async () => {
  renderPage();
  await actAndFlush(() => {});

  const call = getLastAPICall("admin_game_join_url");
  expect(call.method).toBe("GET");
  expect(call.query).toEqual({ game_id: "game-1" });

  const signup = panel("Sign-up link");
  expect(signup.getByLabelText(/Join link text/)).toHaveValue(
    "https://example.com/?j=signup",
  );
  expect(signup.getByLabelText(/^Join link for/)).toHaveAttribute(
    "href",
    "https://example.com/?j=signup",
  );
});
