import React, { useEffect, useState } from 'react';

import { motion } from "framer-motion"
import useSound from 'use-sound';


import styles from './TemporaryOverlay.module.css'
import beep from './beep.mp3';


const _ = require('lodash');


function sleep(ms) {
    return new Promise(resolve => setTimeout(resolve, ms));
}


function TemporaryOverlay({
    appear,
    img,
    time_to_appear = 0.5,
    time_to_disappear = 1.5,
    time_to_show = 0.5,
    custom_variants = {}
}) {
    const [visible, setVisible] = useState(false);

    const [playBeep] = useSound(beep);
    navigator.vibrate(200);

    useEffect(() => {
        async function f() {
            if (appear === true) {
                console.log("Animating...")
                playBeep();
                setVisible(true);
                await sleep(1000 * (time_to_appear + time_to_show));
                setVisible(false);
                console.log("Animation completed")
            }
        }
        f()
    }, [appear, time_to_appear, time_to_show, playBeep])

    const default_variants = {
        hidden: {
            opacity: 0,
            scale: 1,
            width: ["100%", "0%"],
            height: ["100%", "0%"],
            transitionEnd: {
                display: "none",
                scale: 0,
                opacity: 0,
            },
            transition: { duration: time_to_disappear }
        },
        visible: {
            opacity: [0, 1],
            scale: 1,
            width: ["100%", "100%"],
            height: ["100%", "100%"],
            display: "block",
            transition: {
                duration: time_to_appear,
                type: "spring"
            }
        },
    }

    // Merge in any custom variant changes passed by the user
    const variants = _.merge({}, default_variants, custom_variants);

    return (
        <motion.img
            className={styles.overlay}
            src={img}
            initial="hidden"
            animate={visible ? "visible" : "hidden"}
            variants={variants}
        />
    )
}


export default TemporaryOverlay;
