import { useCallback, useRef } from "react";
import { sendAPIRequest } from "./utils";

function NoNameView({ callback = null }) {

    const setUserName = useCallback((username) => {
        sendAPIRequest("set_name", { name: username }, 'POST', callback);
    }, [callback]);

    const setNameInput = useRef();
    return <>
        <span>Enter your name:</span>
        <input ref={setNameInput} />
        <button onClick={() => { setUserName(setNameInput.current.value) }}>Submit</button>
    </>;

}

export default NoNameView;
