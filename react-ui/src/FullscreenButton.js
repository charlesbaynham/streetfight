
import styles from './FullscreenButton.module.css';

import fullscreenImg from './fullscreen-icon.svg';
import hintImg from './better-in-fullscreen.svg';

const FullscreenButton = ({ handle }) => (
    <div className={styles.buttonContainer}>
        <button onClick={handle.enter}>
            <img src={fullscreenImg} alt="Fullscreen" />
        </button>
        <img
            className={styles.fullscreenHint}
            src={hintImg} alt="This app is better in fullscreen"
        />
    </div>
)

export default FullscreenButton;
