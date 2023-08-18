
import scanButtonImg from './scanbutton.png';


export default function ScanButton() {
  return (
    <button onClick={null} style={{
        position: 'absolute',
        left: 0,
        bottom: 0
    }}>
        <img src={scanButtonImg} />
    </button>
  );
}

