import { useState, useEffect } from "react";

const getOrientation = () => {
  const state = window.screen?.orientation?.type;
  if (state === null) return "unknown";
  return state;
};

const useScreenOrientation = () => {
  const [orientation, setOrientation] = useState(getOrientation());

  const updateOrientation = (event) => {
    setOrientation(getOrientation());
  };

  useEffect(() => {
    window.addEventListener("orientationchange", updateOrientation);
    return () => {
      window.removeEventListener("orientationchange", updateOrientation);
    };
  }, []);

  return orientation;
};

export default useScreenOrientation;
