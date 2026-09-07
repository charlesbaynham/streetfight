import * as React from "react";
import * as ReactDOM from "react-dom/client";

import { createBrowserRouter, RouterProvider } from "react-router-dom";

import UserMode from "./UserMode";
import PickOutfit from "./PickOutfit";
import HowItWorks from "./HowItWorks";
import AdminMode from "./AdminMode";
import ShotQueue from "./ShotQueue";
import ShotReplay from "./ShotReplay";
import ReferencePhotos from "./ReferencePhotos";
import SpectatorView from "./SpectatorView";
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
    path: "pick",
    element: <PickOutfit />,
  },
  {
    path: "how-it-works",
    element: <HowItWorks />,
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
    // One route, not two: an optional segment keeps the same element mounted
    // when the queue writes the shot it settled on into the path, where a
    // separate "admin/shots/:shotId" route would tear the page down and
    // rebuild it on the first render. Same for the reference-photo roster.
    path: "admin/shots/:shotId?",
    element: <ShotQueue />,
  },
  {
    path: "admin/replay",
    element: <ShotReplay />,
  },
  {
    path: "admin/reference/:userId?",
    element: <ReferencePhotos />,
  },
  {
    path: "admin/spectator",
    element: <SpectatorView />,
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
