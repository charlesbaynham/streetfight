
import useSound from 'use-sound';

import bang from './bang.mp3';
import styles from './FireButton.module.css';


const fireButtonImg = '/images/firebutton.svg';
const fireButtonImgNoAmmo = '/images/firebutton_no_ammo.svg';


export default function FireButton({ buttonActive, onClick }) {
  const [playBang] = useSound(bang);

  return (
    <button
      className={styles.fireButton}
      disabled={!buttonActive}
      onClick={(e) => {
        playBang();
        return onClick(e)
      }}
    >
      <img src={buttonActive ? fireButtonImg : fireButtonImgNoAmmo} alt="Fire button" />
    </button>
  );
}
