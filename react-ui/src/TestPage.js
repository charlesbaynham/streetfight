import React from "react";
import { MapViewAdmin, MapViewSelf } from "./MapView";

const TestPage = () => {
  return (
    <div>
      <h1>This is a test</h1>

      <h3>Your location:</h3>

      {/* <MapViewSelf /> */}
      <div>
        <MapViewAdmin />
      </div>
    </div>
  );
};

export default TestPage;
