import React, { useCallback, useRef, useState } from "react";
import { sendAPIRequest } from "./utils";

export default function AdminLogin() {
  const [status, setStatus] = useState("ready");

  const login = useCallback((password) => {
    sendAPIRequest(
      "admin_authenticate",
      {
        password: password,
      },
      "POST",
    ).then((response) => {
      if (response.ok) {
        setStatus("success");
      } else {
        setStatus("failure");
      }
    });
  }, []);

  const passwordInput = useRef(null);

  return (
    <>
      <label htmlFor="password">Password:</label>
      <input name="password" ref={passwordInput} />
      <button
        onClick={() => {
          login(passwordInput.current.value);
        }}
      >
        Submit
      </button>
      Status: {status}
    </>
  );
}
