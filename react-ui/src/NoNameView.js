import { useCallback, useState } from "react";
import { sendAPIRequest } from "./utils";

import returnIcon from './return.svg';
import styles from './NoNameView.module.css';

function NoNameView({ callback = null }) {
    const [nameBoxValue, setNameBoxValue] = useState("");

    const setUserName = useCallback(() => {
        sendAPIRequest("set_name", { name: nameBoxValue }, 'POST', callback);
    }, [callback, nameBoxValue]);

    const handleKeyDown = (event) => {
        if (event.key === 'Enter') {
            setUserName();
        }
    }

    return (
        <div className={styles.outerContainer}>
            <div className={styles.inputHolder}>
                <input
                    className={styles.nameInput}
                    value={nameBoxValue}
                    onChange={(e) => { setNameBoxValue(e.target.value) }}
                    onKeyDown={handleKeyDown}
                    placeholder="Enter your name..."
                />
                <button
                    className={styles.nameButton}
                    onClick={setUserName}>
                    <img src={returnIcon} alt="" />
                </button>
            </div>
        </div>
    );

}

export default NoNameView;
