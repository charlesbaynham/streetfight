import { useCallback, useState } from "react";
import { sendAPIRequest } from "./utils";

import returnIcon from './return.svg';
import actionNotDone from './hand-pointer-solid.svg';
import actionDone from './check-solid.svg';
import styles from './OnboardingView.module.css';


const ActionItem = ({ text, done }) => <a href="#">
    <div className={styles.stackedItem +
        (done ? (" " + styles.done) : '')
    }>
        <p>{text}</p>
        <button
            className={styles.actionButton}
        >
            <img src={done ? actionDone : actionNotDone} alt="" />
        </button>
    </div>
</a>

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

    return <div className={styles.stackedItem + (
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
    </div>
}


function OnboardingView({ userState }) {
    return (
        <div className={styles.outerContainer}>
            <div className={styles.innerContainer}>
                <NameEntry userState={userState} />
                {
                    userState.name ? <>
                        < ActionItem
                            text="Do something"
                            done={true}
                        />
                        <ActionItem
                            text="Do something really important"
                            done={false}
                        />
                    </>
                        : null
                }

            </div>
        </div>
    );

}

export default OnboardingView;
