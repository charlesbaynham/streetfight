import React, { useEffect } from "react";
import { useLocation, useNavigate } from "react-router-dom";

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
          .then((r) => {
            console.log(r);
          })
          .then((_) => {
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
