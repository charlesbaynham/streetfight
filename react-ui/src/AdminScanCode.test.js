import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { ScanCodePanel } from "./AdminScanCode";
import { installFetchMock, getLastAPICall, actAndFlush } from "./testUtils";

const SPENT_CARD = {
  kind: "item",
  headline: "5 bullets",
  verdict: { tone: "bad", text: "Spent: already collected by Ada (Red)" },
  facts: [
    { label: "Batch", value: "game" },
    { label: "Scanning", value: "Once ever, by the first player to scan it" },
  ],
};

async function renderPage(routes = {}) {
  installFetchMock(routes);
  render(<ScanCodePanel />);
  await actAndFlush(() => {});
}

async function paste(text) {
  await actAndFlush(() =>
    userEvent.type(screen.getByLabelText("Or paste a code"), text),
  );
  await actAndFlush(() =>
    userEvent.click(
      screen.getByRole("button", { name: "Tell me what that is" }),
    ),
  );
}

test("a scanned code is identified and nothing else is called", async () => {
  await renderPage({ admin_identify_code: SPENT_CARD });

  await paste("https://x/?d=abc");

  expect(getLastAPICall("admin_identify_code").body).toEqual({
    data: "https://x/?d=abc",
  });
  expect(screen.getByText("5 bullets")).toBeInTheDocument();
  expect(
    screen.getByText("Spent: already collected by Ada (Red)"),
  ).toBeInTheDocument();
  expect(
    screen.getByText("Once ever, by the first player to scan it"),
  ).toBeInTheDocument();
});

test("nothing is shown until something has been scanned", async () => {
  await renderPage({ admin_identify_code: SPENT_CARD });

  expect(
    screen.queryByRole("region", { name: "What that code is" }),
  ).toBeNull();
});

test("the camera is not started until it is asked for", async () => {
  await renderPage({ admin_identify_code: SPENT_CARD });

  await actAndFlush(() =>
    userEvent.click(
      screen.getByRole("button", { name: "Scan a code with the camera" }),
    ),
  );

  expect(
    screen.getByRole("button", { name: "Stop the camera" }),
  ).toBeInTheDocument();
});

test("a failed request says so rather than leaving the last answer up", async () => {
  await renderPage({
    admin_identify_code: { status: 500, body: { detail: "boom" } },
  });

  await paste("anything");

  expect(
    screen.getByText("Could not read that code (500)"),
  ).toBeInTheDocument();
});
