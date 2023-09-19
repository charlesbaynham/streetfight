import { useCallback, useState } from "react";
import { sendAPIRequest } from "./utils";

import returnIcon from './return.svg';
import actionNotDone from './hand-pointer-solid.svg';
import actionDone from './check-solid.svg';
import styles from './NoNameView.module.css';


const ActionItem = ({ text }) => <a href="#">
    <div className={styles.stackedItem + " " + styles.active}>
        <p>Do something important</p>
        <button
            className={styles.actionButton}
        >
            <img src={actionNotDone} alt="" />
        </button>
    </div>
</a>


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
            <div className={styles.innerContainer}>
                <div className={styles.stackedItem}>
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
                </div>
                <ActionItem text="Do something really important" />
            </div>
        </div>
    );

}

export default NoNameView;
