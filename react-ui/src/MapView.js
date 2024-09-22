import React, { useCallback, useEffect, useRef, useState } from "react";
import { sendAPIRequest } from "./utils";

import mapSrc from "./images/art/medkit.png";
import dotSrc from "./images/art/helmet.png";

import styles from "./MapView.module.css";

const map_bottom_left = {
  long: -2.742,
  lat: 51.787,
};

const map_top_right = {
  long: -2.73,
  lat: 51.796,
};

const degreesLongitudePerKm = 1 / (111.32 * Math.cos((map_bottom_left.lat + map_top_right.lat) / 2 * (Math.PI / 180)));
const degreesLatitudePerKm = 1 / 110.574;

const MAP_WIDTH_KM = (map_top_right.long - map_bottom_left.long) / degreesLongitudePerKm;
const MAP_HEIGHT_KM = (map_top_right.lat - map_bottom_left.lat) / degreesLatitudePerKm;

const MAP_POLL_TIME = 5 * 1000;
const RATE_LIMIT_INTERVAL = 1 * 1000;

const CORNER_BOX_WIDTH_KM = 0.5;

// FIXME: needs to be centered in css
function Dot({ x, y, color = null }) {
  return color === null ? (
    <img
      className={styles.mapDotSelf}
      src={dotSrc}
      alt=""
      style={{
        left: x,
        bottom: y,
      }}
    />
  ) : (
    <div
      className={styles.mapDotGeneric}
      style={{
        left: x,
        bottom: y,
        backgroundColor: color,
      }}
    />
  );
}



function sendLocationUpdate(lat, long) {
  sendAPIRequest(
    "set_location",
    {
      latitude: lat,
      longitude: long,
    },
    "POST",
    null,
  );
}


function MapView({
  grayedOut = false,
  ownPosition = null,
  other_positions_and_colors = [],
  expanded = false,
}) {

  const mapContainerRef = useRef(null);
  const [boxWidthPx, setMapWidth] = useState(0);
  const [boxHeightPx, setMapHeight] = useState(0);


  // Measure the width and height of the map container so that we can scale the
  // map image. Tolerate resizes / screen rotations.
  useEffect(() => {
    const handleResize = () => {
      if (mapContainerRef.current) {
        setMapWidth(mapContainerRef.current.clientWidth);
        setMapHeight(mapContainerRef.current.clientHeight);
      }
    };

    window.addEventListener("resize", handleResize);

    // Initial measurement
    handleResize();

    return () => {
      window.removeEventListener("resize", handleResize);
    };
  }, [mapContainerRef]);

  const coordsToPixels = useCallback(
    (lat, long, map_centre_lat, map_centre_long) => {
      // Convert from lat / long to km from the bottom left corner
      const box_height_km = boxHeightPx / boxWidthPx * CORNER_BOX_WIDTH_KM;
      const x_km = (long - map_centre_long) / degreesLongitudePerKm + CORNER_BOX_WIDTH_KM / 2;
      const y_km = (lat - map_centre_lat) / degreesLatitudePerKm + box_height_km / 2;

      // Convert from km to pixels
      const x_px = x_km / CORNER_BOX_WIDTH_KM * boxWidthPx;
      const y_px = y_km / box_height_km * boxHeightPx;

      return [x_px, y_px];
    },
    [boxWidthPx, boxHeightPx],
  );

  const [mapData, setMapData] = useState({
    map_x0: 0,
    map_y0: 0,
    map_size_x: 0,
    map_size_y: 0,
    dot_x: 0,
    dot_y: 0,
    otherDots: [],
  });

  useEffect(() => {

    // Calculate the centre of the box, using our own position if provided
    const box_centre_lat = ownPosition ? ownPosition.coords.latitude : (map_bottom_left.lat + map_top_right.lat) / 2;
    const box_centre_long = ownPosition ? ownPosition.coords.longitude : (map_bottom_left.long + map_top_right.long) / 2;

    // Calculate map position based on box position
    const [map_x0, map_y0] = coordsToPixels(
      map_bottom_left.lat,
      map_bottom_left.long,
      box_centre_lat,
      box_centre_long
    );

    // Calculate map size based on box size
    const map_size_x = MAP_WIDTH_KM * boxWidthPx / CORNER_BOX_WIDTH_KM
    const box_height_km = boxHeightPx / boxWidthPx * CORNER_BOX_WIDTH_KM;
    const map_size_y = MAP_HEIGHT_KM * boxHeightPx / box_height_km;

    // Calculate our own dot
    const [dot_x, dot_y] = ownPosition
      ? coordsToPixels(ownPosition.coords.latitude, ownPosition.coords.longitude, box_centre_lat, box_centre_long)
      : [0, 0];

    // Calculate all the other dots
    const otherDots = other_positions_and_colors.map(
      ({ position, color }, index) => {
        const { x, y } = coordsToPixels(position.coords.latitude, position.coords.longitude, box_centre_lat, box_centre_long);
        return <Dot key={index} x={x} y={y} color={color} />;
      },
    );

    console.log("map pos", map_x0, map_y0);  // FIXME: overzealous updating is happening here
    console.log(`left ${map_x0}px bottom ${map_y0}px`);
    console.log("dot pos", dot_x, dot_y);

    setMapData({
      map_x0,
      map_y0,
      map_size_x,
      map_size_y,
      dot_x,
      dot_y,
      otherDots,
    });

  }, [
    boxWidthPx,
    boxHeightPx,
    ownPosition,
    // other_positions_and_colors, FIXME this is causing an infinite loop
    coordsToPixels,
    setMapData
  ]);

  const { map_x0, map_y0, map_size_x, map_size_y, dot_x, dot_y, otherDots } = mapData;


  return (
    <>
      <div
        className={`${styles.mapContainer} ${expanded ? styles.mapContainerExpanded : styles.mapContainerCorner}`}
        ref={mapContainerRef}
      >
        {grayedOut ? <div className={styles.mapOverlay}></div> : null}
        <div
          className={styles.mapImage}
          src={mapSrc}
          alt="Map"
          style={{
            backgroundImage: `url(${mapSrc})`,
            backgroundPosition: `left ${-map_x0}px bottom ${-map_y0}px`,
            backgroundRepeat: "no-repeat",
            backgroundSize: map_size_x + "px " + map_size_y + "px",
          }}
        />
        {!grayedOut && ownPosition !== null ? <Dot x={dot_x} y={dot_y} /> : null}
        {otherDots}
      </div>
    </>
  );
}

var lastUpdateTime = 0;

export function MapViewSelf() {
  const [position, setPosition] = useState(null);

  useEffect(() => {
    if (navigator.geolocation) {
      // Register a callback for changes to the user's position.
      // This a) updates the location on the map and b) sends the location to the server.
      const watchId = navigator.geolocation.watchPosition(
        (position) => {
          const currentTime = Date.now();
          if (currentTime - lastUpdateTime >= RATE_LIMIT_INTERVAL) {
            setPosition(position);
            sendLocationUpdate(
              position.coords.latitude,
              position.coords.longitude,
            );
            lastUpdateTime = currentTime;
          }
        },

        (error) => {
          console.error("Error watching position:", error);
        },
      );

      return () => {
        // Clean up the watch when this component is unmounted.
        navigator.geolocation.clearWatch(watchId);
      };
    } else {
      console.error("Geolocation is not supported by this browser.");
    }
  }, []);

  return <MapView ownPosition={position} />;
}

export function MapViewAdmin() {
  const [locationWithColors, setLocationWithColors] = useState([]);

  const updateLocations = useCallback(() => {
    sendAPIRequest("admin_get_locations").then(async (response) => {
      if (!response.ok) return;
      const locations = await response.json();

      const team_ids = locations.map((user) => user.team_id);
      const unique_team_ids = [...new Set(team_ids)];

      // Assign a color to each unique team
      const colors = [
        "brown",
        "black",
        "red",
        "blue",
        "green",
        "yellow",
        "purple",
        "orange",
        "pink",
        "cyan",
      ];
      const teamColors = {};
      unique_team_ids.forEach((team_id, index) => {
        teamColors[team_id] = colors[index % colors.length];
      });

      // Color each location point according to the team
      // FIXME: Should be gray if dead
      setLocationWithColors(
        locations.map((user) => ({
          position: {
            coords: { latitude: user.latitude, longitude: user.longitude },
          },
          color: teamColors[user.team_id],
        })),
      );
    });
  }, []);

  useEffect(() => {
    const handle = setInterval(updateLocations, MAP_POLL_TIME);
    updateLocations();
    return () => {
      clearInterval(handle);
    };
  }, [updateLocations]);

  return (
    <MapView other_positions_and_colors={locationWithColors} expanded={true} />
  );
}
