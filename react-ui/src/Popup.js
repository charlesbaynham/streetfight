import React, { useCallback, useEffect, useRef, useState } from "react";

import { motion, AnimatePresence } from "framer-motion";

import styles from "./Popup.module.css";
import buttonImg from "./images/exit-button.svg";

const variants = {
  open: { opacity: 1 },
  closed: { opacity: 0 },
};

// Scroll offsets are fractional, so "at the bottom" needs a pixel or two of
// slack before the hint counts the last sliver of content as more to come
const SCROLL_SLACK_PX = 4;

function Popup({ children, visible, setVisible }) {
  const scrollRef = useRef(null);
  const [moreBelow, setMoreBelow] = useState(false);

  // The box is dark and has no scrollbar of its own, so content below the
  // fold - a shot's Appeal button, most of the time - reads as absent rather
  // than as out of view. Watch for anything under the fold and, while there
  // is some, float an arrow at the bottom that scrolls down to it.
  useEffect(() => {
    const container = scrollRef.current;
    if (!container) return undefined;

    const measure = () =>
      setMoreBelow(
        container.scrollHeight - container.clientHeight - container.scrollTop >
          SCROLL_SLACK_PX,
      );

    measure();
    container.addEventListener("scroll", measure);
    window.addEventListener("resize", measure);

    // The content keeps growing after mount as shot photos arrive, so a
    // single measurement would miss the fold appearing. The container's own
    // box is capped, so it is the children that change size.
    const observer =
      typeof ResizeObserver === "undefined"
        ? null
        : new ResizeObserver(measure);
    if (observer) {
      observer.observe(container);
      for (const child of container.children) observer.observe(child);
    }

    return () => {
      container.removeEventListener("scroll", measure);
      window.removeEventListener("resize", measure);
      if (observer) observer.disconnect();
    };
    // Re-measure (and re-observe) when the popup swaps what it is showing,
    // e.g. the shot list for one shot's detail view
  }, [visible, children]);

  const scrollToBottom = useCallback(() => {
    const container = scrollRef.current;
    if (!container) return;
    const top = container.scrollHeight - container.clientHeight;
    if (container.scrollTo) container.scrollTo({ top, behavior: "smooth" });
    else container.scrollTop = top;
  }, []);

  const out = (
    <div className={styles.fullscreenContainer}>
      <motion.div
        className={styles.outerContainer}
        initial="closed"
        animate={visible ? "open" : "closed"}
        transition={{ duration: 0.5 }}
        variants={variants}
        exit="closed"
      >
        <button
          className={styles.exitButton}
          onClick={() => {
            setVisible(false);
          }}
        >
          <img src={buttonImg} alt="" />
        </button>
        <div className={styles.innerContainer} ref={scrollRef}>
          {children}
        </div>
        {moreBelow ? (
          <button
            className={styles.scrollHint}
            aria-label="Scroll down for more"
            onClick={scrollToBottom}
          >
            <svg viewBox="0 0 24 24" aria-hidden="true" focusable="false">
              <path
                d="M5 9l7 7 7-7"
                fill="none"
                stroke="currentColor"
                strokeWidth="3"
                strokeLinecap="round"
                strokeLinejoin="round"
              />
            </svg>
          </button>
        ) : null}
      </motion.div>
    </div>
  );

  return <AnimatePresence>{visible ? out : null}</AnimatePresence>;
}

export default Popup;
