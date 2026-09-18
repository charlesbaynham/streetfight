import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { CodesPanel } from "./AdminCodes";
import {
  installFetchMock,
  getAPICalls,
  getLastAPICall,
  actAndFlush,
} from "./testUtils";

const POSTER = {
  id: "code-1",
  description: "5 bullets",
  item_type: "ammo",
  batch: "sandbox",
  unlimited: true,
  enabled: true,
  first_seen: 1789488000,
};

function switchedOff(code) {
  return { ...code, enabled: false };
}

async function renderPage(routes = {}) {
  installFetchMock({ admin_known_codes: [], ...routes });
  render(<CodesPanel />);
  await actAndFlush(() => {});
}

test("a pasted code is registered and the list says what it is", async () => {
  await renderPage({
    admin_register_code: { code: POSTER, new: true, codes: [POSTER] },
  });

  await actAndFlush(() =>
    userEvent.type(
      screen.getByLabelText("Or paste a code"),
      "https://x/?d=abc",
    ),
  );
  await actAndFlush(() =>
    userEvent.click(
      screen.getByRole("button", { name: "Add that code to the list" }),
    ),
  );

  expect(getLastAPICall("admin_register_code").body).toEqual({
    data: "https://x/?d=abc",
  });
  expect(screen.getByText("Added: 5 bullets")).toBeInTheDocument();
  expect(screen.getByText("Working")).toBeInTheDocument();
});

test("switching a code off posts its id and shows it as off", async () => {
  await renderPage({
    admin_known_codes: [POSTER],
    admin_set_code_enabled: [switchedOff(POSTER)],
  });

  await actAndFlush(() =>
    userEvent.click(
      screen.getByRole("button", { name: "Switch this code off" }),
    ),
  );

  expect(getLastAPICall("admin_set_code_enabled").query).toEqual({
    code_id: "code-1",
    enabled: "false",
  });
  expect(screen.getByText("Switched off")).toBeInTheDocument();
  expect(
    screen.getByRole("button", { name: "Switch this code back on" }),
  ).toBeInTheDocument();
});

test("a code the server did not mint is refused, and nothing joins the list", async () => {
  await renderPage({
    admin_register_code: { status: 403, body: { detail: "nope" } },
  });

  await actAndFlush(() =>
    userEvent.type(screen.getByLabelText("Or paste a code"), "forged"),
  );
  await actAndFlush(() =>
    userEvent.click(
      screen.getByRole("button", { name: "Add that code to the list" }),
    ),
  );

  expect(
    screen.getByText("That is not a code this server minted."),
  ).toBeInTheDocument();
  expect(screen.queryByText("Working")).not.toBeInTheDocument();
});

test("the camera is not started until it is asked for", async () => {
  await renderPage();

  expect(getAPICalls("admin_known_codes")).toHaveLength(1);
  expect(
    screen.getByRole("button", { name: "Scan a code with the camera" }),
  ).toBeInTheDocument();

  await actAndFlush(() =>
    userEvent.click(
      screen.getByRole("button", { name: "Scan a code with the camera" }),
    ),
  );

  expect(
    screen.getByRole("button", { name: "Stop the camera" }),
  ).toBeInTheDocument();
});

test("an empty list says so, rather than looking like a page that failed to load", async () => {
  await renderPage();

  expect(
    within(screen.getByRole("region", { name: "Scanned codes" })).getByText(
      /Nothing scanned in yet/,
    ),
  ).toBeInTheDocument();
});
