import React, { useEffect } from "react";
import { useLocation, useNavigate } from "react-router-dom";

import prose from "./prose";
import { clearRefusal, reportRefusal } from "./refusalStore";
import { sendAPIRequest } from "./utils";

// A custom hook that builds on useLocation to parse
// the query string for you.
// See https://v5.reactrouter.com/web/example/query-parameters
function useQuery() {
  const { search } = useLocation();

  return React.useMemo(() => new URLSearchParams(search), [search]);
}

function CollectItemFromQueryParam({ enabled }) {
  const navigate = useNavigate();
  const query = useQuery();

  const data = query.get("d");

  useEffect(() => {
    if (enabled && data !== null) {
      console.log(`Collecting item with d=${data}`);

      function onTimeout() {
        sendAPIRequest("collect_item", {}, "POST", null, {
          data: data,
        })
          .then(async (response) => {
            // The other way a card is scanned: the player's own camera opens
            // the URL rather than the in-game scanner reading it (QRParser.js,
            // which says why a refusal happened). This path used to log the
            // response to a console nobody on a phone can see and navigate
            // home regardless, so a card the game refused and a card it
            // accepted looked exactly the same from the street.
            if (response.status === 403) {
              const detail = await response
                .json()
                .then((body) => body.detail)
                .catch(() => null);
              reportRefusal(
                detail
                  ? prose.qrScanner.scanRefused(detail)
                  : prose.qrScanner.scanRefusedUnknown,
              );
            } else if (response.ok) {
              clearRefusal();
            }
          })
          .catch(() => {
            reportRefusal(prose.qrScanner.scanOffline);
          })
          .then((_) => {
            // Home either way: the `?d=` has been spent, and the notice is
            // mounted there.
            navigate("/");
          });
      }
      const timeoutId = setTimeout(onTimeout, 200);

      return () => {
        console.log("Cancel collection");
        clearTimeout(timeoutId);
      };
    }
  }, [data, enabled, navigate]);

  return null;
}

export default CollectItemFromQueryParam;
