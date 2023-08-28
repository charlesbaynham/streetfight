import * as React from "react";
import * as ReactDOM from "react-dom/client";

import {
  createBrowserRouter,
  RouterProvider,
} from "react-router-dom";

import UserMode from "./UserMode";
import AdminMode from "./AdminMode";
import ShotQueue from "./ShotQueue";


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
    path: "admin/shots",
    element: <ShotQueue />
  },
]);

ReactDOM.createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <RouterProvider router={router} />
  </React.StrictMode>
);
