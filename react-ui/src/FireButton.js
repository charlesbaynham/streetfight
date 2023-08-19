
import fireButtonImg from './firebutton.png';


export default function FireButton(props) {
  return (
    <button onClick={props.onClick} style={{
        position: 'absolute',
        right: 0,
        bottom: 0
    }}>
        <img src={fireButtonImg} />
    </button>
  );
}
