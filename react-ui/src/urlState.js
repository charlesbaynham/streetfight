// Keeping "where you are" in the URL rather than only in React state.
//
// The admin pages are worked one-handed on a phone, where a reload is one
// stray swipe away and a backgrounded tab gets thrown out by the browser on
// its own. A shot index or a selected player held only in useState does not
// survive that: the admin comes back to the top of the queue, mid-game, with
// no way to say where they were. So a page's position lives in the URL, and
// the page *derives* its position from the URL rather than mirroring state
// into it - one source of truth, and a link that lands somebody else in the
// same place.
//
// Two shapes, and the split is deliberate: *where you are* is a path segment
// (/admin/shots/<shot id>), and *what you are looking at it through* - a
// filter, a game selector, a page number - is a query parameter.

import { useCallback } from "react";
import { useLocation, useNavigate, useSearchParams } from "react-router-dom";

// Merge a patch into the current query string, leaving every other parameter
// alone: a key set to null or undefined is deleted, anything else is
// stringified. Callers say what changed rather than rebuilding the whole
// string, which is what stops the shot queue's filters and /pick's join code
// from deleting each other.
//
// Defaults to replacing the history entry, since most of these are settings
// rather than places: a filter toggled four times should not need the back
// button pressed four times to leave the page. Pass { replace: false } for a
// step somebody would expect the back button to undo.
export function usePatchSearchParams() {
  const [searchParams, setSearchParams] = useSearchParams();

  return useCallback(
    (patch, { replace = true } = {}) => {
      const next = new URLSearchParams(searchParams);
      for (const [key, value] of Object.entries(patch)) {
        if (value === null || value === undefined) next.delete(key);
        else next.set(key, String(value));
      }
      setSearchParams(next, { replace });
    },
    [searchParams, setSearchParams],
  );
}

// Navigate to another path, carrying the query string across unchanged: the
// player being looked at changes, the game they are being looked at in does
// not.
export function useNavigateKeepingSearch() {
  const navigate = useNavigate();
  const { search } = useLocation();

  return useCallback(
    (pathname, { replace = false } = {}) => {
      navigate({ pathname, search }, { replace });
    },
    [navigate, search],
  );
}
