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
// join QR code with their camera app: POSTs the code to join_game, shows the
// backend's explanation in a popup if joining fails, and strips the query by
// navigating back to "/" - unless the code was a *team* code, in which case
// join_game writes nothing and hands back needs_pick, and this navigates to
// /pick?j=<code> (carrying the code onward) so the player can choose their
// own outfit instead. Mounted at the top level of UserMode so it works
// during onboarding, before the player has a team.
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
              navigate("/");
              return;
            }

            // A team code (rather than a per-slot code) writes nothing and
            // hands back needs_pick instead - route to the outfit picker,
            // carrying the same code so it can call join_options itself.
            let body = null;
            try {
              body = await response.json();
            } catch (e) {}
            if (body && body.needs_pick) {
              navigate(`/pick?j=${encodeURIComponent(data)}`);
            } else {
              navigate("/");
            }
          })
          .catch((_) => {
            setErrorMessage("Could not join the game");
            setErrorVisible(true);
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
