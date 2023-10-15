import React from 'react';

import styles from './Popup.module.css'
import buttonImg from './images/exit-button.svg'

function Popup({ children }) {
    return (
        <div className={styles.popup} >
            <button className={styles.exit_button}>
                <img src={buttonImg} alt="" />
            </button>
            {children}
        </div>
    );
}

export default Popup;
