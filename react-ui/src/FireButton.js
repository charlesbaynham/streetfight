
import fireButtonImg from './firebutton.png';


export default function FireButton({ isAlive, onClick }) {
  return (
    <button disabled={!isAlive} onClick={onClick} style={{
      position: 'absolute',
      right: 0,
      bottom: 0
    }}>
      <img src={fireButtonImg} />
    </button>
  );
}
