import React from 'react';

import styles from './Popup.module.css'
import buttonImg from './images/exit-button.svg'

function Popup({ children }) {
    return (
        <div className={styles.outerContainer} >
            <button className={styles.exitButton}>
                <img src={buttonImg} alt="" />
            </button>
            <div className={styles.innerContainer} >
                {children}
            </div>
        </div >
    );
}

export default Popup;
