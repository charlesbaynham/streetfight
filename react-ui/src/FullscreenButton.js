import { motion } from "framer-motion";

import styles from "./FullscreenButton.module.css";

import fullscreenImg from "./images/fullscreen-icon.svg";
import hintImg from "./images/better-in-fullscreen.svg";
import { prepareInstallPrompt, showInstallPrompt, isStandalone } from "./AddToHomeScreen";
import { useCallback, useEffect, useState } from "react";

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
    else handle.enter();
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
