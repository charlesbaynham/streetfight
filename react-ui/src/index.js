import * as React from "react";
import * as ReactDOM from "react-dom/client";

import {
  createBrowserRouter,
  RouterProvider,
} from "react-router-dom";

import ShootMode from "./ShootMode";
import AdminMode from "./AdminMode";


const router = createBrowserRouter([
  {
    path: "/",
    element: <ShootMode />,
  },
  {
    path: "admin",
    element: <AdminMode />,
  },
]);

ReactDOM.createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <RouterProvider router={router} />
  </React.StrictMode>
);
