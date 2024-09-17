import React, { useEffect, useState } from "react";


const TestPage = () => {
  const [loc, setLoc] = useState(null);

  useEffect(() => {
    if (navigator.geolocation) {
      setLoc("Loading...");

      const watchId = navigator.geolocation.watchPosition(
        (position) => {
          const { latitude, longitude } = position.coords;
          setLoc(`Timestamp: ${position.timestamp}, Latitude: ${latitude}, Longitude: ${longitude}, Accuracy: ${position.coords.accuracy}`);
        },
        (error) => {
          console.error("Error watching position:", error);
          setLoc("Error getting position");
        }
      );

      return () => {
        navigator.geolocation.clearWatch(watchId);
      };
    } else {
      console.error("Geolocation is not supported by this browser.");
    }

  }, [])

  return (
    <div>
      <h1>This is a test</h1>

      <h3>Your location:</h3>

      {loc}

    </div>
  );
};

export default TestPage;
