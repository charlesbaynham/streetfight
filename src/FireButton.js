
import fireButtonImg from './firebutton.png';


export default function FireButton() {
  return (
    <button onClick={null} style={{
        position: 'absolute',
        right: 0,
        bottom: 0
    }}>
        <img src={fireButtonImg} />
    </button>
  );
}

