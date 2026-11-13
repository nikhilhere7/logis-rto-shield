import { animate, motion, useInView, useReducedMotion } from "motion/react";
import { useEffect, useRef, useState } from "react";

const EASE = [0.22, 1, 0.36, 1];

// Fade and rise into place the first time the element scrolls into view.
export function Reveal({ children, delay = 0, className = "", as = "div" }) {
  const still = useReducedMotion();
  const Tag = motion[as];
  return (
    <Tag className={className} initial={still ? false : { opacity: 0, y: 18 }} whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, margin: "-60px" }} transition={{ duration: 0.5, delay, ease: EASE }}>
      {children}
    </Tag>
  );
}

// A number that counts up once, when it first becomes visible.
export function CountUp({ value, format = (n) => Math.round(n), duration = 1.2, className = "" }) {
  const ref = useRef(null);
  const seen = useInView(ref, { once: true, margin: "-40px" });
  const still = useReducedMotion();
  const [shown, setShown] = useState(still ? value : 0);

  useEffect(() => {
    if (!seen || value == null) return;
    if (still) return setShown(value);
    const run = animate(0, value, { duration, ease: EASE, onUpdate: setShown });
    return () => run.stop();
  }, [seen, value, still, duration]);

  return <span ref={ref} className={className}>{value == null ? "–" : format(shown)}</span>;
}

export { EASE };
