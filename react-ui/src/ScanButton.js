
import scanButtonImg from './scanbutton.png';


export default function ScanButton(props) {
  return (
    <button onClick={props.onClick} style={{
        position: 'absolute',
        left: 0,
        bottom: 0
    }}>
        <img src={scanButtonImg} />
    </button>
  );
}
