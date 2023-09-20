
import { motion } from "framer-motion"

import styles from './FullscreenButton.module.css';

import fullscreenImg from './fullscreen-icon.svg';
import hintImg from './better-in-fullscreen.svg';
import { useEffect, useState } from "react";

function FullscreenButton({ handle }) {
    const [hintHidden, setHintHidden] = useState(false);

    useEffect(() => {
        const handle = setTimeout(() => { setHintHidden(true) }, 5000);

        return () => { clearTimeout(handle) }
    }, [])

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
