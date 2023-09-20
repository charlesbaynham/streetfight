import { useCallback, useState } from "react";
import { sendAPIRequest } from "./utils";


import { motion, AnimatePresence } from "framer-motion"


import returnIcon from './return.svg';
import actionNotDone from './hand-pointer-solid.svg';
import actionDone from './check-solid.svg';
import styles from './OnboardingView.module.css';


const ActionItem = ({ text, done, onClick = null, doable = true }) => (
    <button onClick={onClick}
        className={styles.stackedItem +
            (done ? (" " + styles.done) : '')}>
        <motion.div layout>
            <p>{text}</p>
            {doable ?
                <button
                    className={styles.actionButton}
                >
                    <img src={done ? actionDone : actionNotDone} alt="" />
                </button>
                : null
            }
        </motion.div>
    </button>
)

function NameEntry({ userState }) {
    const [nameBoxValue, setNameBoxValue] = useState(userState.name ? userState.name : "");

    const setUserName = useCallback(() => {
        sendAPIRequest("set_name", { name: nameBoxValue }, 'POST', null);
    }, [nameBoxValue]);

    const handleKeyDown = (event) => {
        if (event.key === 'Enter') {
            setUserName();
        }
    }

    const done = userState.name !== null;

    return <motion.div layout className={styles.stackedItem + (
        done ? " " + styles.done : ""
    )}>
        <input
            className={styles.nameInput}
            value={nameBoxValue}
            onChange={(e) => { setNameBoxValue(e.target.value) }}
            onKeyDown={handleKeyDown}
            placeholder="Enter your name..."
        />
        <button
            className={styles.actionButton}
            onClick={setUserName}
        >
            <img src={returnIcon} alt="" />
        </button>
    </motion.div>
}

function requestWebcamAccess(callbackCompleted) {
    navigator.mediaDevices
        .getUserMedia({ video: true })
        .then((stream) => {
            stream.getTracks().forEach(function (track) {
                track.stop();
            });
        })
        .then(() => { callbackCompleted() })
}

function OnboardingView({ userState }) {
    const [webcamAvailable, setWebcamAvailable] = useState(false);

    return (
        <div className={styles.outerContainer}>
            <AnimatePresence>
                <div className={styles.innerContainer}>
                    <NameEntry userState={userState} />
                    {
                        userState.name ? <>
                            <ActionItem
                                text="Grant webcam permission:"
                                done={webcamAvailable}
                                onClick={
                                    () => {
                                        requestWebcamAccess(() => { setWebcamAvailable(true) })
                                    }
                                }
                            />
                            {webcamAvailable ?
                                <ActionItem
                                    text="Wait for game to start..."
                                    done={false}
                                    doable={false}
                                />
                                : null
                            }
                        </>
                            : null
                    }

                </div>
            </AnimatePresence>
        </div>
    );

}

export default OnboardingView;
