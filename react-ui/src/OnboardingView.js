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
import logo from "./images/art/logo.png";
import {
  isLocationPermissionGranted,
  isCameraPermissionGranted,
} from "./utils";

import styles from "./OnboardingView.module.css";

const ActionItem = ({ text, done, onClick = null, doable = true }) => (
  <button
    onClick={onClick}
    className={styles.stackedItem + (done ? " " + styles.done : "")}
  >
    <motion.div layout>
      <p>{text}</p>
      {doable ? (
        <div className={styles.actionButton}>
          <img
            className={styles.actionButton}
            src={done ? actionDone : actionNotDone}
            alt=""
          />
        </div>
      ) : null}
    </motion.div>
  </button>
);

function NameEntry({ user }) {
  const [nameBoxValue, setNameBoxValue] = useState(user.name ? user.name : "");

  const setUserName = useCallback(() => {
    sendAPIRequest("set_name", { name: nameBoxValue }, "POST", null);
  }, [nameBoxValue]);

  const handleKeyDown = (event) => {
    if (event.key === "Enter") {
      setUserName();
    }
  };

  const done = user.name !== null;

  return (
    <motion.div
      layout
      className={styles.stackedItem + (done ? " " + styles.done : "")}
    >
      <input
        className={styles.nameInput}
        value={nameBoxValue}
        onChange={(e) => {
          setNameBoxValue(e.target.value);
        }}
        onKeyDown={handleKeyDown}
        placeholder="Enter your name..."
      />
      <button className={styles.actionButton} onClick={setUserName}>
        <img src={returnIcon} alt="" />
      </button>
    </motion.div>
  );
}

function OnboardingView({ user }) {
  const [webcamPermissionGranted, setWebcamPermissionGranted] = useState(false);
  const [locationPermissionGranted, setLocationPermissionGranted] =
    useState(false);

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
          key={"webcam"}
        />,
      );
    else return actionItems;

    if (webcamPermissionGranted)
      actionItems.push(
        <ActionItem
          text={"Grant location permission:"}
          done={locationPermissionGranted}
          onClick={async () => {
            console.log("Requesting location permission from OnboardingView");
            const success = await requestGeolocationPermission();
            setLocationPermissionGranted(success);
          }}
          key={"location"}
        />,
      );
    else return actionItems;

    if (locationPermissionGranted)
      actionItems.push(
        <ActionItem
          text={
            !teamName
              ? "Wait to be added to a team..."
              : `You are in team "${teamName}"`
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
