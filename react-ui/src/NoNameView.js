import { useCallback, useRef } from "react";
import { sendAPIRequest } from "./utils";

import styles from './NoNameView.module.css';

function NoNameView({ callback = null }) {

    const setUserName = useCallback((username) => {
        sendAPIRequest("set_name", { name: username }, 'POST', callback);
    }, [callback]);

    const setNameInput = useRef();
    return (
        <div className={styles.outerContainer}>
            <div className={styles.container}>
                <input
                    className={styles.nameInput} ref={setNameInput}
                    placeholder="Enter your name..."
                />
                <button
                    className={styles.nameButton}
                    onClick={() => { setUserName(setNameInput.current.value) }}>Submit</button>
            </div>
        </div>
    );

}

export default NoNameView;
