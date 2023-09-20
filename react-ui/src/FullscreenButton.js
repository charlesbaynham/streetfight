
import styles from './FullscreenButton.module.css';
import icon from './fullscreen-icon.svg';

const FullscreenButton = ({ handle }) => (
    <button className={styles.button} onClick={handle.enter}>
        <img src={icon} alt="Fullscreen" />
    </button>
)

export default FullscreenButton;
