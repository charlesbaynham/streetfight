import { useEffect, useState } from "react";

// Keeps the screen awake while the page is open: in user mode the phone is
// being held as a weapon, and the spectator screen is a tablet propped up and
// left running all evening, where a sleeping screen means the dashboard has
// simply vanished.
//
// One request is not enough. The browser takes the lock back whenever the page
// stops being visible, and iOS takes it back on its own besides - on a full
// screen change, when another app comes forward, when the tab is refocused.
// Only some of those arrive as `visibilitychange`, and only some of them tell
// the sentinel, so the lock is re-requested on every signal that the page is
// in front again, and - since a screen nobody is watching has nobody to notice
// - on a slow watchdog that just checks whether we still hold one. That also
// covers a refusal (a tablet in low power mode): the next tick tries again.
//
// Returns whether the screen is currently being held awake, so a caller can
// say so - false also covers a browser with no Wake Lock API at all.

const WATCHDOG_MS = 20000;

export default function useWakeLock() {
  const [held, setHeld] = useState(false);

  useEffect(() => {
    if (!navigator.wakeLock) return undefined;

    let sentinel = null;
    let requesting = false;
    let cancelled = false;

    // The lock has gone; the browser has already released it, so there is
    // nothing to release here.
    const forget = () => {
      sentinel = null;
      if (!cancelled) setHeld(false);
    };

    const acquire = () => {
      if (cancelled || sentinel || requesting) return;
      // A request while hidden is refused by spec, so don't spend one.
      if (document.visibilityState !== "visible") return;
      requesting = true;
      navigator.wakeLock
        .request("screen")
        .then((s) => {
          requesting = false;
          if (cancelled) {
            s.release().catch(() => {});
            return;
          }
          sentinel = s;
          setHeld(true);
          // The browser has taken it back. Ask again straight away rather
          // than waiting on the watchdog - the idle timer is already running.
          if (typeof s.addEventListener === "function")
            s.addEventListener("release", () => {
              if (sentinel !== s) return;
              forget();
              acquire();
            });
        })
        .catch(() => {
          requesting = false;
          forget(); // denied: the watchdog will try again
        });
    };

    // `released` is the sentinel we hold having gone stale without saying so.
    const check = () => {
      if (sentinel && sentinel.released) forget();
      acquire();
    };

    const handleVisibilityChange = () => {
      if (document.visibilityState === "visible") acquire();
      else forget();
    };

    acquire();
    document.addEventListener("visibilitychange", handleVisibilityChange);
    document.addEventListener("fullscreenchange", check);
    document.addEventListener("webkitfullscreenchange", check);
    window.addEventListener("focus", check);
    window.addEventListener("pageshow", check);
    const watchdog = setInterval(check, WATCHDOG_MS);

    return () => {
      cancelled = true;
      clearInterval(watchdog);
      document.removeEventListener("visibilitychange", handleVisibilityChange);
      document.removeEventListener("fullscreenchange", check);
      document.removeEventListener("webkitfullscreenchange", check);
      window.removeEventListener("focus", check);
      window.removeEventListener("pageshow", check);
      if (sentinel) sentinel.release().catch(() => {});
    };
  }, []);

  return held;
}
