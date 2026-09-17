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

import { Swatch } from "./Swatch";
import useSoundCheck from "./useSoundCheck";
import CuriosityFooter from "./CuriosityFooter";
import TeamLeaderPanel from "./TeamLeaderPanel";
import styles from "./OnboardingView.module.css";
import prose from "./prose";

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

// pending marks a row the player cannot act on but which is not finished
// either - they have done their part and are now waiting on something else.
// It draws the waiting as a light running round the row (see .pending in the
// stylesheet), because a screen with nothing moving on it reads as a screen
// that has crashed.
const ActionItem = ({
  text,
  done,
  onClick = null,
  doable = true,
  animateReposition = true,
  warn = false,
  pending = false,
}) => (
  <button
    onClick={onClick}
    className={
      styles.stackedItem +
      (done ? " " + styles.done : "") +
      (warn ? " " + styles.warn : "") +
      (pending ? " " + styles.pending : "")
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
        placeholder={prose.onboardingView.namePlaceholder}
      />
      <button className={styles.actionButton} onClick={setUserName}>
        <img src={done ? actionDone : returnIcon} alt="" />
      </button>
    </motion.div>
  );
}

export { NameEntry };

// A swatch (same component the colour picker uses) beside each garment,
// e.g. [🟩] "white t-shirt" & [🟢] "green trousers". Both halves of an outfit
// are drawn with it: the garments the player supplies themselves
// (identity_admin's wardrobe channels) and the hat and armband we hand out at
// the door, which get a row each - see getActionItems.
function OutfitSummary({ garments }) {
  return Object.entries(garments).map(([channel, { colour, hex }], i) => (
    <span key={channel} className={styles.outfitGarment}>
      {i > 0 ? " & " : ""}
      <Swatch hex={hex} label={colour} size="large" />
      {colour} {prose.onboardingView.garmentNames[channel] || channel}
    </span>
  ));
}

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
  const [soundTested, testSound] = useSoundCheck();

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
    const hasOutfit = !!user.outfit_wardrobe;
    const hasProvided =
      !!user.outfit_provided && Object.keys(user.outfit_provided).length > 0;

    const actionItems = [<NameEntry user={user} key={"name"} />];

    if (hasName) {
      actionItems.push(
        <ActionItem
          text={
            hasOutfit
              ? prose.onboardingView.outfitChosen(
                  <OutfitSummary garments={user.outfit_wardrobe} />,
                )
              : prose.onboardingView.outfitNotChosen
          }
          done={hasOutfit}
          doable={hasOutfit}
          key={"outfit"}
        />,
      );
      // The hat and armband, which we hand over at the door rather than
      // leave to the player's own wardrobe. A row of its own, because a row
      // is a fixed height with its text centred in it and a second line
      // inside the outfit row above would overflow it; and nothing to do on
      // it, because there is nothing to do but know. Worth saying at all
      // because since R15 the hat is allocated per player rather than pinned
      // to their team, so this and the essay are the only places a player is
      // told which colours are coming.
      if (hasProvided)
        actionItems.push(
          <ActionItem
            text={prose.onboardingView.outfitProvided(
              <OutfitSummary garments={user.outfit_provided} />,
            )}
            done={true}
            doable={false}
            key={"provided"}
          />,
        );
      actionItems.push(
        <ActionItem
          text={prose.onboardingView.webcamPermission}
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
    } else return actionItems;

    if (webcamPermissionGranted) {
      actionItems.push(
        <ActionItem
          text={
            locationBypassed && !locationPermissionGranted
              ? prose.onboardingView.locationSkipped
              : prose.onboardingView.locationPermission
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
            {prose.onboardingView.locationError}
          </p>,
        );
    } else return actionItems;

    // The compass rung. Unlike the two above it this one does not gate what
    // follows: a heading is telemetry, and a phone without a compass (or a
    // player who says no) must still be able to finish joining and play.
    if (locationStepDone)
      actionItems.push(
        <ActionItem
          text={prose.onboardingView.compassPermission}
          done={compassPermissionGranted}
          onClick={async () => {
            const success = await requestOrientationPermission();
            setCompassPermissionGranted(success);
          }}
          key={"compass"}
        />,
      );

    // The sound check. Beside the compass rung and not before it: like that
    // one it gates nothing, and unlike the two above it there is nothing the
    // page can verify - see useSoundCheck.js for why it is a tap rather than
    // a sentence.
    if (locationStepDone)
      actionItems.push(
        <ActionItem
          text={
            soundTested
              ? prose.onboardingView.soundCheckDone
              : prose.onboardingView.soundCheck
          }
          done={soundTested}
          onClick={testSound}
          key={"sound"}
        />,
      );

    // Teams are scanned in at the door (roadmap R15): a player who signed
    // up through the game link arrives here with an outfit and no team.
    if (locationStepDone)
      actionItems.push(
        <ActionItem
          text={
            !teamName
              ? prose.onboardingView.joinTeamPrompt(hasOutfit)
              : prose.onboardingView.inTeam(teamName, user.identity_slot)
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
          text={prose.onboardingView.waitForGame}
          done={false}
          doable={false}
          pending={true}
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
            <img src={logo} alt={prose.onboardingView.logoAlt} />
          </p>
          {/* Same aside as the picker's: this screen is where a player waits
              for the game to start - at home the week before, or standing in
              the pub - so it is the other place worth offering the essay
              from. A new tab, so a tap never costs them their place in the
              join steps below. Under the logo rather than at the foot of the
              list, which is where the "better in full-screen" scrawl
              (FullscreenButton) is drawn while the game is waiting. */}
          <CuriosityFooter className={styles.curiosityFooter} />
          {getActionItems()}
          {/* Renders nothing unless this player was nominated a leader at the
              door (M7). Below the join steps, because a leader's own join
              comes first. */}
          <TeamLeaderPanel user={user} />
        </div>
      </AnimatePresence>
    </div>
  );
}

export default OnboardingView;
