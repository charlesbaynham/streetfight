import React from 'react';

import styles from './Popup.module.css'

function Popup({ children }) {
    return (
        <div className={styles.popup} >
            {children}
        </div>
    );
}

export default Popup;
