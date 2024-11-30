import React, { useCallback, useRef } from "react";
import { sendAPIRequest } from "./utils";

export default function AdminLogin() {
  const login = useCallback((password) => {
    sendAPIRequest(
      "admin_authenticate",
      {
        password: password,
      },
      "POST",
    );
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
    </>
  );
}
