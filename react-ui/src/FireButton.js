
import styles from './FireButton.module.css';


const fireButtonImg = '/images/firebutton.svg';
const fireButtonImgNoAmmo = '/images/firebutton_no_ammo.svg';



export default function FireButton({ buttonActive, onClick }) {
  return (
    <button
      className={styles.fireButton}
      disabled={!buttonActive}
      onClick={onClick}
    >
      <img src={buttonActive ? fireButtonImg : fireButtonImgNoAmmo} alt="Fire button" />
    </button>
  );
}
