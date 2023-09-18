import React, { useEffect, useState } from 'react';

function SSEComponent() {
    const [messages, setMessages] = useState([]);


    useEffect(() => {
        const eventSource = new EventSource(document.origin + "/api/sse_updates");

        eventSource.onmessage = (event) => {
            console.log("Received SSE:", event);
            setMessages(messages => [...messages, event.data]);
        };

        eventSource.onerror = (error) => {
            console.log("SSE stream closed:", error);
        };

        return () => {
            // Cleanup: close the SSE connection when the component unmounts
            eventSource.close();
        };
    }, []);

    return (
        <div>
            {messages.map((m, i) => <div key={i}>{m}</div>)}
        </div>
    );
}

export default SSEComponent;
