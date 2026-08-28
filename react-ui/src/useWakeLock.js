import { useEffect } from "react";

// Keeps the screen awake while user mode is open: the phone is being held as
// a weapon, and the lock is auto-released whenever the page is hidden, so it
// must be re-requested on every return to visibility (same pattern as the
// camera restart in MyWebcam.js).
export default function useWakeLock() {
  useEffect(() => {
    if (!("wakeLock" in navigator)) return undefined;

    let sentinel = null;
    let cancelled = false;

    const acquire = () => {
      navigator.wakeLock
        .request("screen")
        .then((s) => {
          if (cancelled) s.release().catch(() => {});
          else sentinel = s;
        })
        .catch(() => {}); // denied (e.g. low battery): retry on next visibility
    };

    const handleVisibilityChange = () => {
      if (document.visibilityState === "visible") acquire();
    };

    acquire();
    document.addEventListener("visibilitychange", handleVisibilityChange);

    return () => {
      cancelled = true;
      document.removeEventListener("visibilitychange", handleVisibilityChange);
      if (sentinel) sentinel.release().catch(() => {});
    };
  }, []);
}
