import React, { useEffect, useState } from "react";


const TestPage = () => {
  const [loc, setLoc] = useState(null);

  useEffect(() => {
    if (navigator.geolocation) {
      const watchId = navigator.geolocation.watchPosition(
        (position) => {
          const { latitude, longitude } = position.coords;
          setLoc(`Latitude: ${latitude}, Longitude: ${longitude}`);
        },
        (error) => {
          console.error("Error watching position:", error);
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
