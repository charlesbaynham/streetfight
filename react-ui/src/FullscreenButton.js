
import styles from './FullscreenButton.module.css';
import icon from './fullscreen-icon.svg';

const FullscreenButton = ({ handle }) => (
    <>
        <button className={styles.button} onClick={handle.enter}>
            <img src={icon} alt="Fullscreen" />
        </button>
        <div className={styles.fullscreenHint}>
            Go fullscreen!
        </div>
    </>
)

export default FullscreenButton;
