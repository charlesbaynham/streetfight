
import fireButtonImg from './firebutton.png';


export default function FireButton({ buttonActive, onClick }) {
  return (
    <button disabled={!buttonActive} onClick={onClick} style={{
      position: 'absolute',
      right: 0,
      bottom: 0
    }}>
      <img src={fireButtonImg} />
    </button>
  );
}
