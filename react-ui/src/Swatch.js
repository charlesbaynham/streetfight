// Shared colour swatch component. Used by the admin identity pages (light
// background) and, eventually, player-facing outfit pickers (black
// background) - see Swatch.module.css for how the colours are themed.

import React from "react";

import styles from "./Swatch.module.css";

export function hexFor(channels, channelName, label) {
  if (!label) return null;
  const channel = channels.find((c) => c.name === channelName);
  return (channel && channel.hex[label]) || null;
}

const SIZE_CLASS = {
  small: styles.swatchSmall,
  normal: "",
  large: styles.swatchLarge,
};

// A single colour swatch. Unknown / outside-palette shows as a hatched "?"
// square rather than being silently dropped.
export function Swatch({ hex, label, small, size = "normal" }) {
  const className = [
    styles.swatch,
    SIZE_CLASS[small ? "small" : size],
    hex ? "" : styles.swatchUnknown,
  ]
    .filter(Boolean)
    .join(" ");

  return (
    <span
      className={className}
      style={hex ? { background: hex } : undefined}
      title={label || "not in palette"}
    >
      {hex ? "" : "?"}
    </span>
  );
}
