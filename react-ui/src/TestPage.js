import React, { useEffect } from "react";
import {
  deregisterListener,
  registerListener,
  UpdateSSEConnection,
} from "./UpdateListener";

const TestPage = () => {
  const [messages, setMessages] = React.useState([]);

  useEffect(() => {
    const handle = registerListener("user", () => {
      setMessages((messages) => [...messages, "User event received"]);
    });

    return () => {
      deregisterListener("user", handle);
    };
  }, []);

  useEffect(() => {
    const handle = registerListener("ticker", () => {
      setMessages((messages) => [...messages, "Ticker event received"]);
    });

    return () => {
      deregisterListener("ticker", handle);
    };
  }, []);

  return (
    <div>
      <h1>This is a test</h1>

      <ul>
        {messages.map((m, i) => (
          <li key={i}>{m}</li>
        ))}
      </ul>

      <UpdateSSEConnection />
    </div>
  );
};

export default TestPage;
