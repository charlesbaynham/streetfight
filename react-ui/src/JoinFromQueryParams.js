import React, { useEffect, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";

import Popup from "./Popup";
import { sendAPIRequest } from "./utils";

// A custom hook that builds on useLocation to parse
// the query string for you.
// See https://v5.reactrouter.com/web/example/query-parameters
function useQuery() {
  const { search } = useLocation();

  return React.useMemo(() => new URLSearchParams(search), [search]);
}

// Handles the ?j=<code> query param a player lands with after scanning a
// team join QR code with their camera app: POSTs the code to join_game, shows
// the backend's explanation in a popup if joining fails, and strips the query
// by navigating back to "/" either way. Mounted at the top level of UserMode
// so it works during onboarding, before the player has a team.
function JoinFromQueryParams() {
  const navigate = useNavigate();
  const query = useQuery();

  const [errorMessage, setErrorMessage] = useState(null);
  const [errorVisible, setErrorVisible] = useState(false);

  const data = query.get("j");

  useEffect(() => {
    if (data !== null) {
      console.log(`Joining game with j=${data}`);

      function onTimeout() {
        sendAPIRequest("join_game", {}, "POST", null, {
          data: data,
        })
          .then(async (response) => {
            if (!response.ok) {
              // FastAPI errors arrive as {"detail": "..."}
              let detail = null;
              try {
                detail = (await response.json()).detail;
              } catch (e) {}
              setErrorMessage(
                typeof detail === "string" ? detail : "Could not join the game",
              );
              setErrorVisible(true);
            }
          })
          .catch((_) => {
            setErrorMessage("Could not join the game");
            setErrorVisible(true);
          })
          .then((_) => {
            navigate("/");
          });
      }
      const timeoutId = setTimeout(onTimeout, 200);

      return () => {
        console.log("Cancel join");
        clearTimeout(timeoutId);
      };
    }
  }, [data, navigate]);

  return (
    <Popup visible={errorVisible} setVisible={setErrorVisible}>
      <p>{errorMessage}</p>
    </Popup>
  );
}

export default JoinFromQueryParams;
