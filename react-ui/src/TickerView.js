import React, { useCallback, useEffect, useState } from 'react';

import HashUpdater from './HashUpdater';
import { sendAPIRequest } from './utils';





export default function TickerView() {

    const [messages, setMessages] = useState(["test"]);
    const [knownTickerHash, setKnownTickerHash] = useState(0);

    const updateMessages = useCallback(() => {
        sendAPIRequest("ticker_messages", null, "GET", data => {
            setMessages(data)
        })
    }, [setMessages]);

    useEffect(updateMessages, [updateMessages, knownTickerHash]);

    return <>
        <HashUpdater
            known_hash={knownTickerHash}
            callback={(d) => {
                console.log(`Old hash = ${knownTickerHash}, new_hash=${d}`)
                setKnownTickerHash(d)
            }}
            api_call="ticker_hash"
        />
        {messages.map((m) => <span>- {m}</span>)}
    </>
}
