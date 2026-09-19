// The player's half of the scanner: every QR code the camera sees is offered
// to collect_item, and a refusal says why. The loop itself is
// useQRScanLoop.js, shared with the admin's code list.
//
// It used to say only that something was wrong: a full-screen flash of red and
// an error noise, with the server's `detail` read off the response and thrown
// away. The game has a dozen distinct reasons to turn a card down - a
// withdrawn print run, a code an admin switched off, a card somebody else
// already took, armour no better than what you are wearing, a medpack scanned
// by a player who is not knocked out - and a red screen is none of them. The
// flash stays, because at arm's length in the dark it is what gets the
// player's attention; what it means now goes on top of it (RefusedNotice,
// which sits above BlankScreen's z-index for exactly this reason).

import { useCallback, useRef, useState } from "react";
import useSound from "use-sound";

import prose from "./prose";
import { clearRefusal, reportRefusal } from "./refusalStore";
import useQRScanLoop from "./useQRScanLoop";
import { sendAPIRequest } from "./utils";

import error from "./error.mp3";
import BlankScreen from "./BlankScreen";

// A player holding the phone at a poster rescans it every REPEAT_SUPPRESSION_MS
// (useQRScanLoop.js), so the same refusal arrives again and again. The words
// are worth repeating - the notice is on screen for four seconds and the
// player may only now be looking - but the flash and the noise are not: the
// flash is opaque, lasts about as long as the notice does, and repeating it
// means strobing the screen over the message the player is trying to read.
const FLASH_SUPPRESSION_MS = 15000;

const QRParser = ({ webcamRef }) => {
  const [playError] = useSound(error);

  const [showBlankScreen, setShowBlankScreen] = useState(false);
  const [colorBlankScreen, setColorBlankScreen] = useState("red");

  // In a ref rather than state: it is read and written inside one scan and
  // must never re-run the loop below.
  const lastFlash = useRef({ message: null, at: 0 });

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

  const refuse = useCallback(
    (message) => {
      reportRefusal(message);

      const now = Date.now();
      const repeated =
        lastFlash.current.message === message &&
        now - lastFlash.current.at < FLASH_SUPPRESSION_MS;
      lastFlash.current = { message, at: now };
      if (repeated) return;

      flashTheScreen("red");
      playError();
    },
    [flashTheScreen, playError],
  );

  const onScan = useCallback(
    (data) => {
      // Submit the QR code to the API
      sendAPIRequest("collect_item", {}, "POST", null, {
        data: data,
      })
        .then(async (response) => {
          // 403 is the game saying no, and it always says why. A 404 or a 400
          // is the scanner having read half a code, or somebody else's QR
          // altogether, which happens often enough that reacting to it would
          // be noise - so those stay silent, as they always have.
          if (response.status === 403) {
            const detail = await response
              .json()
              .then((body) => body.detail)
              .catch(() => null);
            refuse(
              detail
                ? prose.qrScanner.scanRefused(detail)
                : prose.qrScanner.scanRefusedUnknown,
            );
            return;
          }
          // Success sounds are handled by the state updating
          if (response.ok) clearRefusal();
        })
        .catch(() => {
          // The code never reached the server. Worth saying out loud: a card
          // that cannot be submitted looks exactly like a card that does not
          // work.
          refuse(prose.qrScanner.scanOffline);
        });
    },
    [refuse],
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
