import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

import { AdminPage, AdminLoginForm } from "./AdminCommon";
import styles from "./AdminCommon.module.css";
import { sendAPIRequest, setAPIErrorHandler } from "./utils";
import * as utils from "./utils";
import {
  installFetchMock,
  getLastAPICall,
  emitUpdate,
  actAndFlush,
} from "./testUtils";

afterEach(() => {
  // Belt and braces: RTL's automatic unmount already runs AdminErrorLog's
  // cleanup, but make sure no handler survives a test that renders it
  // without going through AdminPage.
  setAPIErrorHandler(null);
});

// ShotQueueLink (mounted by AdminNav, mounted by every authenticated
// AdminPage) kicks off its own admin_get_shots_info fetch from a plain
// useEffect with no way for a test to await it directly - it's a genuine
// fire-and-forget promise chain outside of any render() call's act() scope.
// A findByText that happens to wait for its result mostly resolves this,
// but not reliably: the state update itself can still land in a tick that
// isn't nested inside any act() call, which React warns about even though
// the DOM is later observed to be correct. actAndFlush (see testUtils.js)
// keeps the "acting" flag held across the whole chain.

describe("AdminPage", () => {
  test("shows the checking state before the auth check resolves, and does not render children", () => {
    installFetchMock({});
    // Leave the auth check permanently in flight, rather than merely
    // asserting before an already-scheduled mock resolves: a fetch that
    // finishes after this test returns would update state outside of any
    // act() boundary and warn on an unrelated later test.
    global.fetch = jest.fn(() => new Promise(() => {}));

    render(
      <MemoryRouter>
        <AdminPage>
          <p>Secret content</p>
        </AdminPage>
      </MemoryRouter>,
    );

    // Assert immediately, before the mocked fetch's microtask has a chance to
    // resolve - this is the synchronous first paint.
    expect(screen.getByText("Checking admin login...")).toBeInTheDocument();
    expect(screen.queryByText("Secret content")).not.toBeInTheDocument();
  });

  test("shows the login form when not authenticated, and does not render children", async () => {
    installFetchMock({ admin_is_authed: false });

    render(
      <MemoryRouter>
        <AdminPage>
          <p>Secret content</p>
        </AdminPage>
      </MemoryRouter>,
    );

    expect(
      await screen.findByRole("heading", { name: "Admin login" }),
    ).toBeInTheDocument();
    expect(screen.queryByText("Secret content")).not.toBeInTheDocument();
  });

  test("renders the nav bar and children once authenticated", async () => {
    installFetchMock({ admin_is_authed: true, admin_get_shots_info: [] });

    await actAndFlush(() =>
      render(
        <MemoryRouter>
          <AdminPage>
            <p>Secret content</p>
          </AdminPage>
        </MemoryRouter>,
      ),
    );

    expect(screen.getByText("Secret content")).toBeInTheDocument();
    expect(screen.getByText("Admin home")).toBeInTheDocument();
    expect(screen.getByText("Identity workbench")).toBeInTheDocument();
    expect(screen.getByText("Admin login")).toBeInTheDocument();
  });
});

describe("AdminNav", () => {
  // Every nav link is `end`, so a page must only highlight its own entry -
  // the danger being "/" and "/admin", which prefix-match everything below
  // them and would otherwise light up on every admin page.
  async function renderNavAt(path) {
    installFetchMock({ admin_is_authed: true, admin_get_shots_info: [] });
    await actAndFlush(() =>
      render(
        <MemoryRouter initialEntries={[path]}>
          <AdminPage>
            <p>Page content</p>
          </AdminPage>
        </MemoryRouter>,
      ),
    );
  }

  test.each([
    ["/admin", "Admin home"],
    ["/admin/shots", "Shot queue (0)"],
    ["/admin/identity-overrides", "Identity overrides"],
    ["/admin/login", "Admin login"],
  ])("on %s only the %s link is marked active", async (path, label) => {
    await renderNavAt(path);

    const links = screen.getAllByRole("link");
    const active = links.filter((link) =>
      link.classList.contains(styles.navLinkActive),
    );
    expect(active).toHaveLength(1);
    expect(active[0]).toHaveTextContent(label);
  });
});

// The <label htmlFor="password"> in AdminCommon.js points at an id the
// <input> doesn't actually have (the input only carries name="password"), so
// the label isn't programmatically associated with it and getByLabelText
// can't find it - a pre-existing accessibility bug, left as-is per the task
// brief. Fall back to a plain querySelector to drive the field.
function getPasswordInput(container) {
  return container.querySelector('input[name="password"]');
}

describe("AdminLoginForm", () => {
  test("submitting posts the typed password to admin_authenticate", async () => {
    installFetchMock({ admin_authenticate: true });

    const { container } = render(<AdminLoginForm onSuccess={() => {}} />);

    fireEvent.change(getPasswordInput(container), {
      target: { value: "hunter2" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Log in" }));

    // Wait for the whole request/response cycle to settle, not just for the
    // call to be recorded (which happens synchronously on the mock, well
    // before the response promise resolves and the component re-renders).
    await screen.findByText("Logged in");
    const call = getLastAPICall("admin_authenticate");
    expect(call.method).toBe("POST");
    // Surprising but correct: AdminLoginForm passes the password as
    // sendAPIRequest's query_params argument, not its post_object argument,
    // so it travels as a URL query parameter rather than a JSON body even
    // though the method is POST.
    expect(call.query).toEqual({ password: "hunter2" });
    expect(call.body).toBeUndefined();
  });

  test("a failed response shows 'Wrong password' and does not call onSuccess", async () => {
    installFetchMock({ admin_authenticate: { status: 403, body: {} } });
    const onSuccess = jest.fn();

    const { container } = render(<AdminLoginForm onSuccess={onSuccess} />);

    fireEvent.change(getPasswordInput(container), {
      target: { value: "wrong" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Log in" }));

    expect(await screen.findByText("Wrong password")).toBeInTheDocument();
    expect(onSuccess).not.toHaveBeenCalled();
  });

  test("a successful response shows 'Logged in' and calls onSuccess", async () => {
    installFetchMock({ admin_authenticate: true });
    const onSuccess = jest.fn();

    const { container } = render(<AdminLoginForm onSuccess={onSuccess} />);

    fireEvent.change(getPasswordInput(container), {
      target: { value: "correct" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Log in" }));

    expect(await screen.findByText("Logged in")).toBeInTheDocument();
    expect(onSuccess).toHaveBeenCalledTimes(1);
  });

  test("logging in successfully from the gate reveals the page content", async () => {
    installFetchMock({
      admin_is_authed: false,
      admin_authenticate: true,
      admin_get_shots_info: [],
    });

    const { container } = render(
      <MemoryRouter>
        <AdminPage>
          <p>Secret content</p>
        </AdminPage>
      </MemoryRouter>,
    );

    expect(
      await screen.findByRole("heading", { name: "Admin login" }),
    ).toBeInTheDocument();

    fireEvent.change(getPasswordInput(container), {
      target: { value: "hunter2" },
    });
    await actAndFlush(() =>
      fireEvent.click(screen.getByRole("button", { name: "Log in" })),
    );

    expect(screen.getByText("Secret content")).toBeInTheDocument();
  });
});

describe("AdminErrorLog", () => {
  // Renders the full AdminPage in its authenticated state, since AdminErrorLog
  // is internal to AdminCommon.js and only reachable that way. It registers
  // itself as the single global error handler from src/utils.js on mount, so
  // any sendAPIRequest call made anywhere - including directly from a test,
  // as below - shows up in it.
  async function renderAuthedAdminPage() {
    installFetchMock({ admin_is_authed: true, admin_get_shots_info: [] });
    await actAndFlush(() =>
      render(
        <MemoryRouter>
          <AdminPage>
            <p>Page content</p>
          </AdminPage>
        </MemoryRouter>,
      ),
    );
    expect(screen.getByText("Page content")).toBeInTheDocument();
  }

  test("renders nothing while there are no errors", async () => {
    await renderAuthedAdminPage();
    expect(screen.queryByText("API errors")).not.toBeInTheDocument();
  });

  test("a failed API request renders an entry with the endpoint, status and response text", async () => {
    await renderAuthedAdminPage();
    installFetchMock({ some_endpoint: { status: 500, body: "boom" } });

    sendAPIRequest("some_endpoint");

    await waitFor(() =>
      expect(screen.getByText("API errors")).toBeInTheDocument(),
    );
    const entry = screen.getByText(/some_endpoint/);
    expect(entry.textContent).toContain("500");
    expect(entry.textContent).toContain("boom");
  });

  test("consecutive identical failures collapse into one line with an (xN) counter", async () => {
    await renderAuthedAdminPage();
    installFetchMock({ flaky: { status: 500, body: "err" } });

    sendAPIRequest("flaky");
    sendAPIRequest("flaky");
    sendAPIRequest("flaky");

    await waitFor(() => expect(screen.getByText(/\(x3\)/)).toBeInTheDocument());
    expect(screen.getAllByRole("listitem")).toHaveLength(1);
  });

  test("a different endpoint or a different status code starts a new line instead of collapsing", async () => {
    await renderAuthedAdminPage();

    installFetchMock({ endpoint_a: { status: 500, body: "err" } });
    sendAPIRequest("endpoint_a");
    await waitFor(() =>
      expect(screen.getAllByRole("listitem")).toHaveLength(1),
    );

    // Same endpoint, different status.
    installFetchMock({ endpoint_a: { status: 404, body: "missing" } });
    sendAPIRequest("endpoint_a");
    await waitFor(() =>
      expect(screen.getAllByRole("listitem")).toHaveLength(2),
    );

    // Different endpoint, status matching the previous entry.
    installFetchMock({ endpoint_b: { status: 404, body: "missing" } });
    sendAPIRequest("endpoint_b");
    await waitFor(() =>
      expect(screen.getAllByRole("listitem")).toHaveLength(3),
    );
  });

  test("keeps only the most recent 20 entries once more than 20 distinct failures occur", async () => {
    await renderAuthedAdminPage();

    const routes = {};
    for (let i = 0; i < 25; i++) {
      routes[`endpoint_${i}`] = { status: 500, body: "err" };
    }
    installFetchMock(routes);

    for (let i = 0; i < 25; i++) {
      sendAPIRequest(`endpoint_${i}`);
    }

    await waitFor(() =>
      expect(screen.getAllByRole("listitem")).toHaveLength(20),
    );
    // The oldest 5 of the 25 distinct failures should have been dropped.
    expect(screen.queryByText(/endpoint_0\D/)).not.toBeInTheDocument();
    expect(screen.queryByText(/endpoint_4\D/)).not.toBeInTheDocument();
    expect(screen.getByText(/endpoint_5\D/)).toBeInTheDocument();
    expect(screen.getByText(/endpoint_24/)).toBeInTheDocument();
  });

  test("truncates a long response text to 500 characters", async () => {
    await renderAuthedAdminPage();
    const longText = "x".repeat(600);
    installFetchMock({ big_error: { status: 500, body: longText } });

    sendAPIRequest("big_error");

    await waitFor(() =>
      expect(screen.getByText(/big_error/)).toBeInTheDocument(),
    );
    const entry = screen.getByText(/big_error/);
    expect(entry.textContent).toContain("x".repeat(500));
    expect(entry.textContent).not.toContain("x".repeat(501));
  });

  test("the Dismiss button clears the log", async () => {
    await renderAuthedAdminPage();
    installFetchMock({ oops: { status: 500, body: "err" } });

    sendAPIRequest("oops");
    await waitFor(() =>
      expect(screen.getByText("API errors")).toBeInTheDocument(),
    );

    fireEvent.click(screen.getByRole("button", { name: "Dismiss" }));

    expect(screen.queryByText("API errors")).not.toBeInTheDocument();
  });

  test("unmounting deregisters the global error handler", async () => {
    const setHandlerSpy = jest.spyOn(utils, "setAPIErrorHandler");
    installFetchMock({ admin_is_authed: true, admin_get_shots_info: [] });

    const { unmount } = await actAndFlush(() =>
      render(
        <MemoryRouter>
          <AdminPage>
            <p>Page content</p>
          </AdminPage>
        </MemoryRouter>,
      ),
    );
    expect(screen.getByText("Page content")).toBeInTheDocument();
    setHandlerSpy.mockClear(); // drop the registration call from mount

    unmount();

    expect(setHandlerSpy).toHaveBeenLastCalledWith(null);
    setHandlerSpy.mockRestore();
  });
});

describe("ShotQueueLink (part of the nav bar)", () => {
  test("shows the live queued-shot count and updates it on a 'shots' SSE update", async () => {
    installFetchMock({
      admin_is_authed: true,
      admin_get_shots_info: ["s1", "s2"],
    });

    await actAndFlush(() =>
      render(
        <MemoryRouter>
          <AdminPage>
            <p>Page content</p>
          </AdminPage>
        </MemoryRouter>,
      ),
    );
    expect(screen.getByText("Shot queue (2)")).toBeInTheDocument();

    installFetchMock({
      admin_is_authed: true,
      admin_get_shots_info: ["s1"],
    });
    await actAndFlush(() => emitUpdate("shots"));

    expect(screen.getByText("Shot queue (1)")).toBeInTheDocument();
  });
});
