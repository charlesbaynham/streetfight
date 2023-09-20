
import { motion } from "framer-motion"

import styles from './FullscreenButton.module.css';

import fullscreenImg from './images/fullscreen-icon.svg';
import hintImg from './images/better-in-fullscreen.svg';
import { useEffect, useState } from "react";

function FullscreenButton({ handle, keepHintVisible = false }) {
    const [hintHidden, setHintHidden] = useState(false);

    useEffect(() => {
        if (keepHintVisible)
            return

        const handle = setTimeout(() => { setHintHidden(true) }, 5000);

        return () => { clearTimeout(handle) }
    }, [keepHintVisible, setHintHidden])

    return (
        <motion.div className={styles.buttonContainer}>
            <button onClick={handle.enter}>
                <img src={fullscreenImg} alt="Fullscreen" />
            </button>
            <motion.img
                className={styles.fullscreenHint}
                animate={{
                    opacity: hintHidden ? 0 : 1
                }}
                transition={{
                    duration: 3
                }}
                src={hintImg} alt="This app is better in fullscreen"
            />
        </motion.div>
    )
}

export default FullscreenButton;
