import React from "react";

import { AdminPage } from "./AdminCommon";

// AdminPage shows the login form when not authed, so this page only needs to
// handle the already-logged-in case.
export default function AdminLogin() {
  return (
    <AdminPage>
      <p>
        You are logged in as admin. Head to the <a href="/admin">admin page</a>.
      </p>
    </AdminPage>
  );
}
