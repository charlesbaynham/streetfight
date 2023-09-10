
import styles from './FireButton.module.css';


const fireButtonImg = '/images/firebutton.svg';



export default function FireButton({ buttonActive, onClick }) {
  return (
    <button
      className={styles.fireButton}
      disabled={!buttonActive}
      onClick={onClick}
    >
      <img src={fireButtonImg} alt="Fire button" />
    </button>
  );
}
