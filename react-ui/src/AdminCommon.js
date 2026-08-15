// Shared plumbing for the admin pages: the login gate, the nav bar and a POST
// helper that makes failures visible instead of silently logging to console.

import "bootstrap/dist/css/bootstrap.min.css";

import React, { useCallback, useEffect, useRef, useState } from "react";
import { Container } from "react-bootstrap";

import { sendAPIRequest, setAPIErrorHandler } from "./utils";
import UpdateListener, { UpdateSSEConnection } from "./UpdateListener";

// POST wrapper for admin actions. The optional callback fires on success with
// the parsed response body; failures show up in the AdminErrorLog box.
export function adminPost(endpoint, params, callback = null) {
  return sendAPIRequest(endpoint, params, "POST", callback);
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
      <a href="/admin/shots">
        Shot queue{numShots === null ? "" : ` (${numShots})`}
      </a>
    </>
  );
}

export function AdminNav() {
  return (
    <p>
      <a href="/admin">Admin home</a> | <ShotQueueLink /> |{" "}
      <a href="/admin/identity">Identity workbench</a> |{" "}
      <a href="/">Player view</a>
    </p>
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
    </Container>
  );
}
