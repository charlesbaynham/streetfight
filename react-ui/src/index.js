import * as React from "react";
import * as ReactDOM from "react-dom/client";

import { createBrowserRouter, RouterProvider } from "react-router-dom";

import UserMode from "./UserMode";
import AdminMode from "./AdminMode";
import ShotQueue from "./ShotQueue";
import TestPage from "./TestPage";
import IdentityDemo from "./IdentityDemo";
import AdminIdentity from "./AdminIdentity";

import "./index.css";
import AdminLogin from "./AdminLogin";
import { AdminPage } from "./AdminCommon";

const router = createBrowserRouter([
  {
    path: "/",
    element: <UserMode />,
  },
  {
    path: "admin",
    element: <AdminMode />,
  },
  {
    path: "admin/login",
    element: <AdminLogin />,
  },
  {
    path: "admin/shots",
    element: <ShotQueue />,
  },
  {
    path: "admin/identity",
    element: (
      <AdminPage>
        <IdentityDemo />
      </AdminPage>
    ),
  },
  {
    path: "admin/identity-overrides",
    element: (
      <AdminPage>
        <AdminIdentity />
      </AdminPage>
    ),
  },
  {
    path: "test",
    element: <TestPage />,
  },
]);

ReactDOM.createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <RouterProvider router={router} />
  </React.StrictMode>,
);
