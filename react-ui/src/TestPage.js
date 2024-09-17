import React, { useEffect, useState } from "react";
import MapView from "./MapView";

const TestPage = () => {
  const [position, setPosition] = useState(null);

  useEffect(() => {
    if (navigator.geolocation) {
      setPosition(null);

      const watchId = navigator.geolocation.watchPosition(setPosition,
        (error) => {
          console.error("Error watching position:", error);
          setPosition("Error getting position");
        },
      );

      return () => {
        navigator.geolocation.clearWatch(watchId);
      };
    } else {
      console.error("Geolocation is not supported by this browser.");
    }
  }, []);

  return (
    <div>
      <h1>This is a test</h1>

      <h3>Your location:</h3>

      <MapView position={position} />
    </div>
  );
};

export default TestPage;
