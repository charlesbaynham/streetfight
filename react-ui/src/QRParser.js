// The player's half of the scanner: every QR code the camera sees is offered
// to collect_item, and a refusal flashes the screen red. The loop itself is
// useQRScanLoop.js, shared with the admin's code list.

import { useCallback, useState } from "react";
import useSound from "use-sound";

import useQRScanLoop from "./useQRScanLoop";
import { sendAPIRequest } from "./utils";

import error from "./error.mp3";
import BlankScreen from "./BlankScreen";

const QRParser = ({ webcamRef }) => {
  const [playError] = useSound(error);

  const [showBlankScreen, setShowBlankScreen] = useState(false);
  const [colorBlankScreen, setColorBlankScreen] = useState("red");

  const flashTheScreen = useCallback(
    (color) => {
      setColorBlankScreen(color);
      setShowBlankScreen(true);
      const timer_id = setTimeout(() => {
        setShowBlankScreen(false);
      }, 1000);
      return timer_id;
    },
    [setShowBlankScreen, setColorBlankScreen],
  );

  const onScan = useCallback(
    (data) => {
      // Submit the QR code to the API
      sendAPIRequest("collect_item", {}, "POST", null, {
        data: data,
      }).then(async (response) => {
        // Play an error sound if the API rejects us with a forbidden error
        // We might also get 404 errors for invalid QR codes - ignore these because the QR scanner occasionally misfires
        // Success sounds will be handled by the state updating
        if (response.status === 403) {
          flashTheScreen("red");
          playError();
        } else {
          // flashTheScreen("green");
        }
      });
    },
    [playError, flashTheScreen],
  );

  useQRScanLoop(webcamRef, onScan);

  return (
    <BlankScreen
      appear={showBlankScreen}
      color={colorBlankScreen}
      time_to_appear={0.3}
      time_to_show={0.7}
      time_to_disappear={3.0}
    />
  );
};

export default QRParser;
