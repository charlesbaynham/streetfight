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
    admin_map_poster_pdf: "%PDF-fake",
    admin_team_cards_pdf: "%PDF-fake",
    admin_pub_pages_pdf: "%PDF-fake",
    admin_item_sheets_pdf: "%PDF-fake",
    admin_sandbox_sheets_pdf: "%PDF-fake",
    admin_revoked_batches: [],
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

test("the map poster is a GET of the chosen paper size, and mints nothing", async () => {
  renderPage();

  await actAndFlush(() =>
    userEvent.selectOptions(panel("Map poster").getByRole("combobox"), "A4"),
  );
  await press("Map poster", "Download map poster (PDF)");

  const call = getLastAPICall("admin_map_poster_pdf");
  expect(call.method).toBe("GET");
  expect(call.query).toEqual({ size: "A4" });
});

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
  expect(call.query).toEqual({ count: "6", num_bullets: "5", batch: "game" });
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
    batch: "game",
  });
});

test("a radar card asks for minutes rather than an amount, and is batched like the rest", async () => {
  renderPage();

  await actAndFlush(() =>
    userEvent.selectOptions(panel("Drop cards").getByRole("combobox"), "radar"),
  );
  await press("Drop cards", "Mint and download (PDF)");

  const call = getLastAPICall("admin_item_sheets_pdf");
  expect(call.query.itype).toBe("radar");
  // The default that comes with the payload schema, not one chosen here.
  expect(call.query.minutes).toBe("5");
  expect(call.query.batch).toBe("game");
});

test("a batch is what the admin types, so a sandbox run can be withdrawn on its own", async () => {
  renderPage();

  const field = panel("Drop cards").getByLabelText(/Batch/);
  await actAndFlush(() => userEvent.clear(field));
  await actAndFlush(() => userEvent.type(field, "sandbox"));
  await press("Drop cards", "Mint and download (PDF)");

  expect(getLastAPICall("admin_item_sheets_pdf").query.batch).toBe("sandbox");
});

test("the sandbox sheet posts only how many copies, and says what a press costs", async () => {
  renderPage();

  const sandbox = panel("Sandbox posters");
  // Six kinds of poster, one code each, whatever the copy count.
  expect(sandbox.getByText(/mints 6 new codes/i)).toBeInTheDocument();

  await press("Sandbox posters", "Mint and download (PDF)");

  const call = getLastAPICall("admin_sandbox_sheets_pdf");
  expect(call.method).toBe("POST");
  expect(call.query).toEqual({ copies: "1" });
});

test("withdrawing a batch posts it, and the list it comes back with is what is shown", async () => {
  installFetchMock({
    admin_list_games: GAMES,
    admin_game_join_url: { game_url: "https://example.com/?j=signup" },
    admin_revoked_batches: [],
    admin_withdraw_batch: [
      { batch: "sandbox", revoked_at: "2026-09-19T16:00:00" },
    ],
  });
  render(<PrintablesPanel />);
  await actAndFlush(() => {});

  const withdraw = panel("Withdraw codes");
  expect(withdraw.getByText(/nothing is withdrawn/i)).toBeInTheDocument();

  // The button names what it is about to turn off.
  await press("Withdraw codes", 'Withdraw "sandbox"');

  expect(getLastAPICall("admin_withdraw_batch").query).toEqual({
    batch: "sandbox",
  });
  // The row that came back, with its way out - not the blurb, which also
  // names the sandbox.
  const row = withdraw.getByRole("button", {
    name: "Allow again",
  }).parentElement;
  expect(within(row).getByText("sandbox")).toBeInTheDocument();
});

test("a batch that is not the sandbox is warned about before it is withdrawn", async () => {
  installFetchMock({
    admin_list_games: GAMES,
    admin_game_join_url: { game_url: "https://example.com/?j=signup" },
    admin_revoked_batches: [],
  });
  render(<PrintablesPanel />);
  await actAndFlush(() => {});

  const withdraw = panel("Withdraw codes");
  expect(withdraw.queryByText(/is not the sandbox/i)).not.toBeInTheDocument();

  const field = withdraw.getByLabelText("Batch");
  await actAndFlush(() => userEvent.clear(field));
  await actAndFlush(() => userEvent.type(field, "game"));

  expect(withdraw.getByText(/is not the sandbox/i)).toBeInTheDocument();
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
