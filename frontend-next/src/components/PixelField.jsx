import { animate, stagger } from "animejs";
import { useEffect, useRef, useState } from "react";

const CELL = 26;                                   // distance between pixels
const COLOURS = ["#635bff", "#635bff", "#0a2540", "#c7a84b"];

// A quiet grid of pixels behind the hero. A ripple runs through it every few seconds,
// and another starts wherever the pointer moves. Built with Anime.js grid stagger.
export default function PixelField({ className = "" }) {
  const box = useRef(null);
  const [grid, setGrid] = useState({ cols: 0, rows: 0 });

  useEffect(() => {
    const measure = () => {
      const r = box.current.getBoundingClientRect();
      setGrid({ cols: Math.ceil(r.width / CELL), rows: Math.ceil(r.height / CELL) });
    };
    measure();
    window.addEventListener("resize", measure);
    return () => window.removeEventListener("resize", measure);
  }, []);

  useEffect(() => {
    const el = box.current;
    const cells = el.querySelectorAll("i");
    if (!cells.length || window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    let last = 0;

    const ripple = (from) =>
      animate(cells, {
        scale: [{ to: 2.2, duration: 260, ease: "outQuad" }, { to: 1, duration: 620, ease: "inOutQuad" }],
        opacity: [{ to: 0.55, duration: 260 }, { to: 0.1, duration: 620 }],
        delay: stagger(42, { grid: [grid.cols, grid.rows], from }),
      });

    const onMove = (e) => {
      const now = performance.now();
      if (now - last < 650) return;                // one ripple at a time is plenty
      last = now;
      const r = el.getBoundingClientRect();
      const col = Math.floor((e.clientX - r.left) / CELL), row = Math.floor((e.clientY - r.top) / CELL);
      if (col >= 0 && row >= 0 && col < grid.cols && row < grid.rows) ripple(row * grid.cols + col);
    };

    const first = setTimeout(() => ripple("center"), 500);
    const loop = setInterval(() => ripple(Math.floor(Math.random() * cells.length)), 4200);
    window.addEventListener("pointermove", onMove);
    return () => {
      clearTimeout(first);
      clearInterval(loop);
      window.removeEventListener("pointermove", onMove);
    };
  }, [grid]);

  return (
    <div ref={box} aria-hidden="true" className={`pointer-events-none absolute inset-0 overflow-hidden ${className}`}
      style={{ maskImage: "radial-gradient(ellipse 80% 75% at 50% 40%, black 30%, transparent 100%)", WebkitMaskImage: "radial-gradient(ellipse 80% 75% at 50% 40%, black 30%, transparent 100%)" }}>
      <div className="grid" style={{ gridTemplateColumns: `repeat(${grid.cols}, ${CELL}px)`, gridAutoRows: `${CELL}px` }}>
        {Array.from({ length: grid.cols * grid.rows }, (_, i) => (
          <span key={i} className="flex items-center justify-center">
            <i className="block h-[3px] w-[3px] rounded-[1px] opacity-10" style={{ background: COLOURS[(i * 7 + Math.floor(i / grid.cols) * 3) % COLOURS.length] }} />
          </span>
        ))}
      </div>
    </div>
  );
}
