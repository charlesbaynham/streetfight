// Shared plumbing for the admin pages: the login gate, the nav bar and a POST
// helper that makes failures visible instead of silently logging to console.

import "bootstrap/dist/css/bootstrap.min.css";

import React, { useCallback, useEffect, useRef, useState } from "react";
import { Container } from "react-bootstrap";
import { NavLink } from "react-router-dom";

import { sendAPIRequest, setAPIErrorHandler } from "./utils";
import UpdateListener, { UpdateSSEConnection } from "./UpdateListener";
import styles from "./AdminCommon.module.css";

// POST wrapper for admin actions. The optional callback fires on success with
// the parsed response body; failures show up in the AdminErrorLog box.
export function adminPost(endpoint, params, callback = null) {
  return sendAPIRequest(endpoint, params, "POST", callback);
}

// POST wrapper for admin actions whose response body is a file rather than
// JSON. Saves the response as a normal browser download; failures show up in
// the AdminErrorLog box like any other admin request.
export function adminDownload(endpoint, params, filename) {
  return sendAPIRequest(endpoint, params, "POST").then(async (response) => {
    if (!response.ok) return response;

    const blob = await response.blob();
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);

    return response;
  });
}

// A red box listing every API call that has failed on this page - status code
// and raw response text, because the admin is the one debugging. Registers
// itself as the global error handler from utils.sendAPIRequest, so it catches
// every request made by any component on the page. Consecutive identical
// failures collapse into one line with a counter (a failing 5-second poll
// should not scroll the page).
function AdminErrorLog() {
  const [errors, setErrors] = useState([]);

  useEffect(() => {
    setAPIErrorHandler(({ endpoint, status, text }) => {
      setErrors((previous) => {
        const last = previous[previous.length - 1];
        if (last && last.endpoint === endpoint && last.status === status) {
          return [...previous.slice(0, -1), { ...last, count: last.count + 1 }];
        }
        const entry = {
          time: new Date().toLocaleTimeString(),
          endpoint,
          status,
          text: String(text).slice(0, 500),
          count: 1,
        };
        // Keep the log bounded
        return [...previous.slice(-19), entry];
      });
    });
    return () => setAPIErrorHandler(null);
  }, []);

  if (errors.length === 0) return null;

  return (
    <div
      style={{
        background: "#ffe0e0",
        border: "2px solid red",
        padding: "0.5em",
        margin: "0.5em 0",
      }}
    >
      <b>API errors</b> <button onClick={() => setErrors([])}>Dismiss</button>
      <ul>
        {errors.map((error, idx) => (
          <li key={idx}>
            <code>
              {error.time} {error.endpoint} &rarr; {error.status}
              {error.count > 1 ? ` (x${error.count})` : ""}: {error.text}
            </code>
          </li>
        ))}
      </ul>
    </div>
  );
}

export function AdminLoginForm({ onSuccess }) {
  const [status, setStatus] = useState("");
  const passwordInput = useRef(null);

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        sendAPIRequest(
          "admin_authenticate",
          { password: passwordInput.current.value },
          "POST",
        ).then((response) => {
          if (response.ok) {
            setStatus("Logged in");
            if (onSuccess) onSuccess();
          } else {
            setStatus("Wrong password");
          }
        });
      }}
    >
      <h1>Admin login</h1>
      <label htmlFor="password">Password: </label>
      <input name="password" type="password" ref={passwordInput} />{" "}
      <button type="submit">Log in</button> {status}
      <p>
        Logging in sets a long-lived cookie in this browser, so you only need to
        do this once per device.
      </p>
    </form>
  );
}

// One nav entry, sized as a button rather than a word of body text. `end` is
// always set: none of the admin pages should light up because a sibling route
// happens to sit below it in the path.
function AdminNavLink({ to, children }) {
  return (
    <NavLink
      to={to}
      end
      className={({ isActive }) =>
        isActive ? `${styles.navLink} ${styles.navLinkActive}` : styles.navLink
      }
    >
      {children}
    </NavLink>
  );
}

// Link to the shot queue with a live count of unchecked shots.
function ShotQueueLink() {
  const [numShots, setNumShots] = useState(null);

  const update = useCallback(() => {
    sendAPIRequest("admin_get_shots_info", {}, "GET", (shot_ids) => {
      setNumShots(shot_ids.length);
    });
  }, []);

  useEffect(update, [update]);

  return (
    <>
      <UpdateListener update_type="shots" callback={update} />
      <AdminNavLink to="/admin/shots">
        Shot queue{numShots === null ? "" : ` (${numShots})`}
      </AdminNavLink>
    </>
  );
}

export function AdminNav() {
  return (
    <nav className={styles.nav}>
      <AdminNavLink to="/admin">Admin home</AdminNavLink>
      <ShotQueueLink />
      <AdminNavLink to="/admin/replay">Shot replay</AdminNavLink>
      <AdminNavLink to="/admin/reference">Reference photos</AdminNavLink>
      <AdminNavLink to="/admin/spectator">Spectator screen</AdminNavLink>
      <AdminNavLink to="/admin/identity">Identity workbench</AdminNavLink>
      <AdminNavLink to="/admin/identity-overrides">
        Identity overrides
      </AdminNavLink>
      <AdminNavLink to="/admin/login">Admin login</AdminNavLink>
      <AdminNavLink to="/">Player view</AdminNavLink>
    </nav>
  );
}

// The git hash the backend reports for itself, shown small at the bottom of
// every admin page so a screenshot of a problem says which code produced it.
function VersionReadout() {
  const [version, setVersion] = useState(null);

  useEffect(() => {
    sendAPIRequest("get_version", {}, "GET", ({ version }) =>
      setVersion(version),
    );
  }, []);

  if (!version) return null;

  return (
    <span>
      version <code>{version}</code>
    </span>
  );
}

// How much credit is left on the OpenRouter key CharlesBot spends against -
// nothing to show if the key isn't configured (the feature is simply off),
// and re-fetched every minute since usage moves while the admin is working
// the shot queue.
const OPENROUTER_BALANCE_POLL_MS = 60 * 1000;

// A shot review costs a fraction of a penny, so a gauge rounded to whole
// cents sits on the same number for a dozen shots at a time and reads as
// broken. Four places is enough for a single review to show up. Configured
// figures - a purchased total, a key's cap - are round numbers a human typed,
// so they keep the usual two.
function formatUSD(amount, decimals = 4) {
  if (amount === null || amount === undefined) return "unknown";
  return `$${amount.toFixed(decimals)}`;
}

function OpenRouterBalanceReadout() {
  const [balance, setBalance] = useState(null);

  const update = useCallback(() => {
    sendAPIRequest("admin_get_openrouter_balance", {}, "GET", setBalance);
  }, []);

  useEffect(() => {
    update();
    const interval = setInterval(update, OPENROUTER_BALANCE_POLL_MS);
    return () => clearInterval(interval);
  }, [update]);

  if (!balance || !balance.configured) return null;

  if (balance.error) return <span>OpenRouter balance unavailable</span>;

  // Three different numbers, in decreasing order of what the admin actually
  // wants to know. The account's remaining credit is the real fuel gauge, but
  // it comes from an endpoint a plain API key may be refused; a per-key
  // spending cap is the next best thing; and with neither, all OpenRouter
  // will tell us about an uncapped key is what it has spent so far.
  const { limit, limit_remaining, usage, credits_remaining } = balance;

  let readout;
  if (credits_remaining !== null && credits_remaining !== undefined) {
    readout = `${formatUSD(credits_remaining)} credit left`;
  } else if (limit !== null && limit !== undefined) {
    readout = `${formatUSD(limit_remaining)} left of the ${formatUSD(
      limit,
      2,
    )} key limit`;
  } else {
    readout = `${formatUSD(usage)} used (no key limit set)`;
  }

  return <span>OpenRouter: {readout}</span>;
}

function AdminFooter() {
  return (
    <footer className={styles.versionFooter}>
      <VersionReadout />
      <OpenRouterBalanceReadout />
    </footer>
  );
}

// Gate + shared chrome for every admin page: checks the login cookie, shows
// the login form if it is missing, and otherwise renders the nav bar, the admin
// SSE connection (which live-updates everything below it) and the page itself.
//
// `bare` drops the Container's max width, the nav and the footer, for a page
// that wants the whole viewport (the spectator screen). It keeps the gate, the
// SSE connection and the error log - a red box is how you notice from across
// the room that the screen has stopped working.
export function AdminPage({ children, bare = false }) {
  const [authed, setAuthed] = useState(null);

  useEffect(() => {
    sendAPIRequest("admin_is_authed", {}, "GET", (is_authed) => {
      setAuthed(is_authed);
    });
  }, []);

  if (authed === null)
    return (
      <Container>
        <AdminErrorLog />
        <p>Checking admin login...</p>
      </Container>
    );

  if (!authed)
    return (
      <Container>
        <AdminErrorLog />
        <AdminLoginForm onSuccess={() => setAuthed(true)} />
      </Container>
    );

  if (bare)
    return (
      <>
        <UpdateSSEConnection endpoint="sse_admin_updates" />
        <AdminErrorLog />
        {children}
      </>
    );

  return (
    <Container>
      <UpdateSSEConnection endpoint="sse_admin_updates" />
      <AdminNav />
      <AdminErrorLog />
      {children}
      <AdminFooter />
    </Container>
  );
}
