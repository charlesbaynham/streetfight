import Popup from "./Popup";
import Scoreboard from "./Scoreboard";

import streetImage from "./images/test-street-image.jpg"

const TestPage = () => {
    return (
        <>
            <img
                src={streetImage}
                style={{
                    height: "100vh",
                    width: "100vw"
                }}
            />
            <Popup>
                <Scoreboard />
            </Popup>
        </>
    )
};


export default TestPage;
