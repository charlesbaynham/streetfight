import { useEffect, useState } from "react";
import Popup from "./Popup";
import Scoreboard from "./Scoreboard";

import streetImage from "./images/test-street-image.jpg"

const TestPage = () => {
    const [visible, setVisible] = useState(false);

    return (
        <>
            <button onClick={() => {
                setVisible(!visible)
            }}>
                Toggle
            </button >

            <img
                src={streetImage}
                style={{
                    height: "100vh",
                    width: "100vw"
                }}
            />

            < Popup visible={visible} setVisible={setVisible} >
                <Scoreboard />
            </Popup >
        </>
    )
};


export default TestPage;
