import React, { useCallback, useEffect, useState } from 'react';

import HashUpdater from './HashUpdater';
import { sendAPIRequest } from './utils';

import styles from './TickerView.module.css'

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
            update_type="ticker"
            callback={() => {
                console.log(`Updating knownTickerHash to ${knownTickerHash + 1}`)
                setKnownTickerHash(knownTickerHash + 1)
            }}
        />
        <div className={styles.tickerview}>
            <ul>
                {messages.map((m, i) => <li key={i}>{m}</li>)}
            </ul>
        </div>
    </>
}
