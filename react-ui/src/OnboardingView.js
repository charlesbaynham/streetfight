import { useCallback, useEffect, useState } from "react";
import {
  requestGeolocationPermission,
  requestWebcamAccess,
  sendAPIRequest,
} from "./utils";

import { motion, AnimatePresence } from "framer-motion";

import returnIcon from "./images/return.svg";
import actionNotDone from "./images/hand-pointer-solid.svg";
import actionDone from "./images/check-solid.svg";
import actionWarn from "./images/triangle-exclamation-solid.svg";
import logo from "./images/art/logo.png";
import {
  isLocationPermissionGranted,
  isCameraPermissionGranted,
  isOrientationPermissionGranted,
  requestOrientationPermission,
  isLocationBypassActive,
  setLocationBypass,
} from "./utils";

import styles from "./OnboardingView.module.css";

// animateReposition defaults on: as later rows appear, the centred container
// grows and every row above shifts up, and framer-motion's layout animation
// is what makes that shift a smooth slide instead of a snap. Off for the
// webcam/location rows specifically (see getActionItems below) - a tap
// landing mid-reflow on the one gating button that's load-bearing for the
// whole join flow is a plausible explanation for guests on Safari sometimes
// finding it unresponsive (dry-run item 5), and the animation there is
// purely cosmetic.

// Tapping the (stuck) location button this many times in a row skips it -
// see the bypass note above requestGeolocationPermission's LOCATION_BYPASS_KEY
// in utils.js.
const LOCATION_BYPASS_TAPS = 5;

const ActionItem = ({
  text,
  done,
  onClick = null,
  doable = true,
  animateReposition = true,
  warn = false,
}) => (
  <button
    onClick={onClick}
    className={
      styles.stackedItem +
      (done ? " " + styles.done : "") +
      (warn ? " " + styles.warn : "")
    }
  >
    <motion.div layout={animateReposition}>
      <p>{text}</p>
      {doable ? (
        <div className={styles.actionButton}>
          <img
            className={styles.actionButton}
            src={warn ? actionWarn : done ? actionDone : actionNotDone}
            alt=""
          />
        </div>
      ) : null}
    </motion.div>
  </button>
);

// onNameSet, when given, is called with the saved name - PickOutfit needs to
// know the moment the player stops being anonymous, since it will not let an
// outfit be claimed before then. A blank box is not a name: it is neither
// posted nor reported.
function NameEntry({ user, className, onNameSet = null }) {
  const [nameBoxValue, setNameBoxValue] = useState(user.name ? user.name : "");

  const setUserName = useCallback(() => {
    const name = nameBoxValue.trim();
    if (!name) return;
    sendAPIRequest("set_name", { name }, "POST", () => {
      if (onNameSet) onNameSet(name);
    });
  }, [nameBoxValue, onNameSet]);

  const handleKeyDown = (event) => {
    if (event.key === "Enter") {
      setUserName();
    }
  };

  const done = user.name !== null;

  return (
    <motion.div
      layout
      className={[styles.stackedItem, done ? styles.done : "", className || ""]
        .filter(Boolean)
        .join(" ")}
    >
      <input
        className={styles.nameInput}
        value={nameBoxValue}
        onChange={(e) => {
          setNameBoxValue(e.target.value);
        }}
        onKeyDown={handleKeyDown}
        onBlur={setUserName}
        placeholder="Enter your name..."
      />
      <button className={styles.actionButton} onClick={setUserName}>
        <img src={done ? actionDone : returnIcon} alt="" />
      </button>
    </motion.div>
  );
}

export { NameEntry };

function OnboardingView({ user }) {
  const [webcamPermissionGranted, setWebcamPermissionGranted] = useState(false);
  const [locationPermissionGranted, setLocationPermissionGranted] =
    useState(false);
  const [locationError, setLocationError] = useState(false);
  const [compassPermissionGranted, setCompassPermissionGranted] =
    useState(false);
  const [locationBypassed, setLocationBypassed] = useState(() =>
    isLocationBypassActive(),
  );
  const [locationTapCount, setLocationTapCount] = useState(0);

  // Location doesn't have to be granted to get past this gate, just either
  // granted or bypassed - see LOCATION_BYPASS_TAPS above.
  const locationStepDone = locationPermissionGranted || locationBypassed;

  // Check if permissions have already been granted on load
  useEffect(() => {
    isCameraPermissionGranted().then((result) => {
      setWebcamPermissionGranted(result);
    });
  }, []);

  useEffect(() => {
    isLocationPermissionGranted().then((result) => {
      setLocationPermissionGranted(result);
    });
  }, []);

  useEffect(() => {
    isOrientationPermissionGranted().then((result) => {
      setCompassPermissionGranted(result);
    });
  }, []);

  function getActionItems() {
    const hasName = user.name;
    const inTeam = user.team_name !== null;
    const teamName = user.team_name;

    const actionItems = [<NameEntry user={user} key={"name"} />];

    if (hasName)
      actionItems.push(
        <ActionItem
          text="Grant webcam permission:"
          done={webcamPermissionGranted}
          onClick={() => {
            requestWebcamAccess(() => {
              setWebcamPermissionGranted(true);
            });
          }}
          animateReposition={false}
          key={"webcam"}
        />,
      );
    else return actionItems;

    if (webcamPermissionGranted) {
      actionItems.push(
        <ActionItem
          text={
            locationBypassed && !locationPermissionGranted
              ? "Location skipped — no map"
              : "Grant location permission:"
          }
          done={locationStepDone}
          warn={locationBypassed && !locationPermissionGranted}
          onClick={async () => {
            if (locationBypassed) return;

            // Some iPhones never show the prompt at all, so a tap here can
            // hang forever with no resolve or reject. Count taps themselves,
            // synchronously, rather than counting failures.
            const nextTapCount = locationTapCount + 1;
            if (nextTapCount >= LOCATION_BYPASS_TAPS) {
              setLocationBypass();
              setLocationBypassed(true);
              return;
            }
            setLocationTapCount(nextTapCount);

            console.log("Requesting location permission from OnboardingView");
            setLocationError(false);
            const success = await requestGeolocationPermission();
            if (success) setLocationTapCount(0);
            setLocationPermissionGranted(success);
            setLocationError(!success);
          }}
          animateReposition={false}
          key={"location"}
        />,
      );
      if (locationError)
        actionItems.push(
          <p className={styles.locationError} key={"location-error"}>
            Couldn't get your location — check Settings &gt; Privacy &gt;
            Location Services, then tap again.
          </p>,
        );
    } else return actionItems;

    // The compass rung. Unlike the two above it this one does not gate what
    // follows: a heading is telemetry, and a phone without a compass (or a
    // player who says no) must still be able to finish joining and play.
    if (locationStepDone)
      actionItems.push(
        <ActionItem
          text={"Grant compass permission:"}
          done={compassPermissionGranted}
          onClick={async () => {
            const success = await requestOrientationPermission();
            setCompassPermissionGranted(success);
          }}
          key={"compass"}
        />,
      );

    const outfit =
      user.identity_slot !== null && user.identity_slot !== undefined
        ? ` — outfit #${user.identity_slot}`
        : "";

    if (locationStepDone)
      actionItems.push(
        <ActionItem
          text={
            !teamName
              ? "Scan your team's join QR code with your camera app..."
              : `You are in team "${teamName}"` + outfit
          }
          done={inTeam}
          doable={false}
          key={"team"}
        />,
      );
    else return actionItems;

    if (user.team_id !== null)
      actionItems.push(
        <ActionItem
          text="Wait for game to start..."
          done={false}
          doable={false}
          key={"game"}
        />,
      );

    return actionItems;
  }

  return (
    <div className={styles.outerContainer}>
      <AnimatePresence>
        <div className={styles.innerContainer}>
          <p className={styles.logo}>
            <img src={logo} alt="Streetfight, by Charles and Gaby" />
          </p>
          {getActionItems()}
        </div>
      </AnimatePresence>
    </div>
  );
}

export default OnboardingView;
