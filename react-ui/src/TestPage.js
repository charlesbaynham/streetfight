import React, { useEffect, useState } from "react";
import MapView from "./MapView";

const TestPage = () => {
  const [loc, setLoc] = useState(null);

  const [orientation, setOrientation] = useState(null);

  useEffect(() => {
    const handleOrientation = (event) => {
      if (event.absolute) {
        setOrientation(event.alpha);
      } else {
        setOrientation("Orientation not absolute");
      }
      console.log(event);
    };

    window.addEventListener("deviceorientation", handleOrientation);

    return () => {
      window.removeEventListener("deviceorientation", handleOrientation);
    };
  }, []);

  useEffect(() => {
    if (navigator.geolocation) {
      const watchId = navigator.geolocation.watchPosition(
        (position) => {
          setLoc(position);
        },
        (error) => {
          console.error("Error watching position:", error);
          setLoc("Error getting position");
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

      {loc ? <MapView position={loc} /> : null}

      <h3>Your orientation:</h3>

      {orientation ? <p>Orientation: {orientation}</p> : <p>Unknown</p>}
    </div>
  );
};

export default TestPage;
