import React, { useState } from 'react';

import { motion, AnimatePresence } from "framer-motion"

import styles from './Popup.module.css'
import buttonImg from './images/exit-button.svg'

const variants = {
    // open: { opacity: 1, scale: 1 },
    // closed: { opacity: 0, scale: 0 },
    open: { opacity: 1 },
    closed: { opacity: 0 },
}

function Popup({ children, visible, setVisible }) {
    const [animate, setAnimate] = useState("open");

    return (
        <motion.div
            className={styles.outerContainer}
            initial="closed"
            animate={visible ? "open" : "closed"}
            transition={{ duration: 0.5 }}
            variants={variants}
            exit="closed"
        >
            <button
                className={styles.exitButton}
                onClick={() => {
                    setAnimate("closed")
                    setVisible(false)
                }}
            >
                <img src={buttonImg} alt="" />
            </button>
            <div className={styles.innerContainer} >
                {children}
            </div>
        </motion.div >
    );
}

export default Popup;
