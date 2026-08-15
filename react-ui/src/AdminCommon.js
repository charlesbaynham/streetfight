// Shared plumbing for the admin pages: the login gate, the nav bar and a POST
// helper that makes failures visible instead of silently logging to console.

import "bootstrap/dist/css/bootstrap.min.css";

import React, { useCallback, useEffect, useRef, useState } from "react";
import { Container } from "react-bootstrap";

import { sendAPIRequest } from "./utils";
import UpdateListener, { UpdateSSEConnection } from "./UpdateListener";

// POST wrapper for admin actions. The optional callback fires on success (with
// the parsed response body); any failure pops an alert so you know it happened.
export function adminPost(endpoint, params, callback = null) {
  return sendAPIRequest(endpoint, params, "POST", callback).then(
    async (response) => {
      if (!response.ok) {
        let detail = "";
        try {
          const body = await response.json();
          detail = JSON.stringify(
            body.detail !== undefined ? body.detail : body,
          );
        } catch (e) {}
        window.alert(`${endpoint} failed (${response.status}): ${detail}`);
      }
      return response;
    },
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

  if (authed === null) return <p>Checking admin login...</p>;

  if (!authed)
    return (
      <Container>
        <AdminLoginForm onSuccess={() => setAuthed(true)} />
      </Container>
    );

  return (
    <Container>
      <UpdateSSEConnection endpoint="sse_admin_updates" />
      <AdminNav />
      {children}
    </Container>
  );
}
