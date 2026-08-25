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
function VersionFooter() {
  const [version, setVersion] = useState(null);

  useEffect(() => {
    sendAPIRequest("get_version", {}, "GET", ({ version }) =>
      setVersion(version),
    );
  }, []);

  if (!version) return null;

  return (
    <footer className={styles.versionFooter}>
      version <code>{version}</code>
    </footer>
  );
}

// Gate + shared chrome for every admin page: checks the login cookie, shows
// the login form if it is missing, and otherwise renders the nav bar, the admin
// SSE connection (which live-updates everything below it) and the page itself.
export function AdminPage({ children }) {
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

  return (
    <Container>
      <UpdateSSEConnection endpoint="sse_admin_updates" />
      <AdminNav />
      <AdminErrorLog />
      {children}
      <VersionFooter />
    </Container>
  );
}
