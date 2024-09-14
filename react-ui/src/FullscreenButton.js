import { motion } from "framer-motion";

import styles from "./FullscreenButton.module.css";

import fullscreenImg from "./images/fullscreen-icon.svg";
import hintImg from "./images/better-in-fullscreen.svg";
import { prepareInstallPrompt, showInstallPrompt, isStandalone } from "./AddToHomeScreen";
import { useCallback, useEffect, useState } from "react";


const TIME_BETWEEN_INSTALL_PROMPTS = 5 * 60 * 1000; // 5 mins



function getTimeSinceLastPrompt() {
  const last_prompt = localStorage.getItem('last_install_prompt');
  var ts;

  if (last_prompt === null) {
    ts = 0;
  } else {
    ts = JSON.parse(last_prompt);
  }

  return Date.now() - ts;
}

function setLastPromptTime() {
  const time = Date.now();
  localStorage.setItem('last_install_prompt', time);
}



function FullscreenButton({ handle, isFullscreen, keepHintVisible = false }) {
  const [hintHidden, setHintHidden] = useState(false);
  const [isInstalled, setIsInstalled] = useState(false);

  useEffect(() => {
    prepareInstallPrompt();
    setIsInstalled(isStandalone());
  }, [])

  useEffect(() => {
    if (keepHintVisible) return;

    const handle = setTimeout(() => {
      setHintHidden(true);
    }, 5000);

    return () => {
      clearTimeout(handle);
    };
  }, [keepHintVisible, setHintHidden]);

  const toggleFullscreen = useCallback(() => {
    if (isFullscreen) handle.exit();
    else {
      // If we haven't shown a message in xxx minutes then prompt the user to
      // install the app
      const elapsed_time = getTimeSinceLastPrompt();
      console.log("getTimeSinceLastPrompt() = ", elapsed_time);
      if (elapsed_time > TIME_BETWEEN_INSTALL_PROMPTS) {
        setLastPromptTime();
        console.debug("Showing prompt");
        showInstallPrompt();
      } else {
        // Otherwise, just go fullscreen as requested
        handle.enter();
      }
    }

  }, [handle, isFullscreen]);

  return <>
    {isInstalled ? null :
      <motion.div className={styles.buttonContainer}>
        <button onClick={toggleFullscreen}>
          <img src={fullscreenImg} alt="Fullscreen" />
        </button>
        <motion.img
          className={styles.fullscreenHint}
          animate={{
            opacity: hintHidden ? 0 : 1,
          }}
          transition={{
            duration: 3,
          }}
          src={hintImg}
          alt="This app is better in fullscreen"
        />
      </motion.div>
    }
  </>;
}

export default FullscreenButton;
