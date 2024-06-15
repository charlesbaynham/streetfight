import React, { useState, useEffect } from "react";

function WebsocketTest() {
  const [ws, setWs] = useState(null);
  const [message, setMessage] = useState("");
  const [receivedData, setReceivedData] = useState([]);

  useEffect(() => {
    // Establish a WebSocket connection
    const newWs = new WebSocket("wss://localhost:3000/api/ws_updates");

    newWs.onopen = () => {
      console.log("WebSocket connected");
    };

    newWs.onmessage = (event) => {
      // Handle received data
      setReceivedData((prevData) => [...prevData, event.data]);
    };

    newWs.onclose = () => {
      console.log("WebSocket closed");
    };

    setWs(newWs);

    // Close the WebSocket when the component unmounts
    return () => {
      if (newWs) {
        newWs.close();
      }
    };
  }, []);

  const handleMessageChange = (e) => {
    setMessage(e.target.value);
  };

  const sendMessage = () => {
    if (ws && message) {
      // Send the message to the WebSocket server
      ws.send(message);
      setMessage("");
    }
  };

  return (
    <div>
      <h1>WebSocket Example</h1>
      <div>
        <input
          type="text"
          value={message}
          onChange={handleMessageChange}
          placeholder="Enter a message"
        />
        <button onClick={sendMessage}>Send</button>
      </div>
      <div>
        <h2>Received Data:</h2>
        <ul>
          {receivedData.map((data, index) => (
            <li key={index}>{data}</li>
          ))}
        </ul>
      </div>
    </div>
  );
}

export default WebsocketTest;
