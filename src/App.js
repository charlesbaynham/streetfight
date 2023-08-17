import logo from './logo.svg';
import crosshair from './crosshair.png';
import './App.css';


import Webcam from "react-webcam";


const SCREEN_FILL_STYLES = {
  position: "absolute",
  height: "100vh",
  width: "100vw",
  left: "0",
  top: "0",
  objectFit: "cover"
};

// const videoConstraints = {
//   width: 1280,
//   height: 720,
//   facingMode: "user"
// };

const WebcamCapture = () => (
  <Webcam
    audio={false}
    // height={720}
    screenshotFormat="image/jpeg"
    // width={1280}
    // videoConstraints={videoConstraints}
    style={SCREEN_FILL_STYLES}
  >
    {/* {({ getScreenshot }) => (
      <button
        onClick={() => {
          const imageSrc = getScreenshot()

          console.log(imageSrc)
        }}
      >
        Capture photo
      </button>
    )} */}
  </Webcam>
);

const Crosshair =() => (
  <img
  src={crosshair}
  style={SCREEN_FILL_STYLES}
  />
);

function App() {

  return (
    <div className="App">
        
      <WebcamCapture />
      <Crosshair />

    </div>
  );
}

export default App;
