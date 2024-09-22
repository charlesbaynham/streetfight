import dotSrc from "./images/art/helmet.png";
import styles from "./MapView.module.css";


export default function Dot({ x, y, color = null }) {
  return color === null ? (
    <img
      className={styles.mapDotSelf}
      src={dotSrc}
      alt=""
      style={{
        left: x,
        bottom: y,
      }}
    />
  ) : (
    <div
      className={styles.mapDotGeneric}
      style={{
        left: x,
        bottom: y,
        backgroundColor: color,
      }}
    />
  );
}
