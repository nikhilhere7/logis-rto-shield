import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import { useState } from "react";
import { EASE } from "./motion";

const INK = "#0a2540", HAIR = "#e8eef7", GRAPHITE = "#475569", BRAND = "#635bff", GAIN = "#0d9488", LOSS = "#b91c1c", GOLD = "#c7a84b";
const inView = { once: true, margin: "-60px" };
const TONES = { ink: INK, brand: BRAND, gain: GAIN, loss: LOSS };

// A line that draws itself, with a soft fill under it. Move the pointer over it to read any point.
// values: numbers. names: one label per point (shown in the tooltip). labels: [[index, text], ...] for the axis.
export function LineChart({ values, names = [], labels = [], max, format = (v) => `${v}%`, height = 260, tone = "brand", describe }) {
  const still = useReducedMotion();
  const [hover, setHover] = useState(null);
  const W = 640, H = height, L = 48, R = 20, T = 24, B = 30;
  const top = max ?? niceMax(Math.max(...values, 1));
  const x = (i) => L + (i * (W - L - R)) / Math.max(1, values.length - 1);
  const y = (v) => H - B - (v / top) * (H - T - B);
  const d = values.map((v, i) => `${i ? "L" : "M"}${x(i).toFixed(1)},${y(v).toFixed(1)}`).join(" ");
  const area = `${d} L${x(values.length - 1).toFixed(1)},${H - B} L${L},${H - B} Z`;
  const last = values.length - 1, colour = TONES[tone];
  const shown = hover ?? last;

  const track = (e) => {
    const r = e.currentTarget.getBoundingClientRect();
    const px = ((e.clientX - r.left) / r.width) * W;
    setHover(Math.max(0, Math.min(last, Math.round(((px - L) / (W - L - R)) * last))));
  };

  return (
    <div className="relative min-w-0">
      <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label={describe} className="h-auto w-full touch-none select-none"
        onPointerMove={track} onPointerLeave={() => setHover(null)}>
        {[0, 0.25, 0.5, 0.75, 1].map((t) => (
          <g key={t}>
            <line x1={L} x2={W - R} y1={y(t * top)} y2={y(t * top)} stroke={HAIR} />
            <text x={L - 8} y={y(t * top) + 4} textAnchor="end" fontSize="11" fill={GRAPHITE}>{format(t * top)}</text>
          </g>
        ))}
        {labels.map(([i, text]) => (
          <text key={i} x={x(i)} y={H - 8} textAnchor={i === 0 ? "start" : i === last ? "end" : "middle"} fontSize="11" fill={GRAPHITE}>{text}</text>
        ))}
        <motion.path d={area} fill={colour} initial={still ? false : { opacity: 0 }} whileInView={{ opacity: 0.08 }} viewport={inView} transition={{ duration: 0.8, delay: 1 }} />
        <motion.path d={d} fill="none" stroke={colour} strokeWidth="2.25" strokeLinejoin="round" strokeLinecap="round"
          initial={still ? false : { pathLength: 0 }} whileInView={{ pathLength: 1 }} viewport={inView} transition={{ duration: 1.6, ease: "easeInOut" }} />
        <line x1={x(shown)} x2={x(shown)} y1={T} y2={H - B} stroke={INK} strokeOpacity={hover == null ? 0 : 0.25} strokeDasharray="3 3" />
        <circle cx={x(shown)} cy={y(values[shown])} r="5" fill="#fff" stroke={colour} strokeWidth="2.5" />
      </svg>
      <div className="pointer-events-none absolute top-0 whitespace-nowrap rounded-lg bg-ink px-2.5 py-1.5 text-xs text-white shadow-lg transition-[left] duration-100"
        style={{ left: `${(x(shown) / W) * 100}%`, transform: `translateX(${shown > last / 2 ? "-108%" : "8%"})` }}>
        <span className="num font-semibold">{format(values[shown])}</span>{names[shown] ? <span className="ml-1.5 text-white/70">{names[shown]}</span> : null}
      </div>
    </div>
  );
}

function niceMax(v) {
  const p = 10 ** Math.floor(Math.log10(v));
  return Math.ceil(v / p / 0.5) * 0.5 * p;
}

// Horizontal bars that grow from the left and re-flow when the data changes.
// rows: [{id?, label, value, note?}]. id (falls back to label) keys each row and is what `picked` compares to,
// so two rows with the same label never clash. onPick makes rows clickable. picked marks one row in gold.
export function BarList({ rows, format = (v) => v, flagMax = false, tone = "ink", onPick, picked }) {
  const still = useReducedMotion();
  const num = (v) => (Number.isFinite(Number(v)) ? Number(v) : 0);
  const max = Math.max(...rows.map((r) => num(r.value)), 0) || 1;
  const Row = onPick ? "button" : "div";
  return (
    <div className="flex flex-col gap-1">
      <AnimatePresence initial={false} mode="popLayout">
        {rows.map((r, i) => {
          const id = r.id ?? r.label;
          const on = picked != null && picked === id;
          const colour = on ? GOLD : flagMax && num(r.value) === max ? LOSS : TONES[tone];
          return (
            <motion.div key={String(id)} layout={!still} initial={still ? false : { opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }}
              transition={{ duration: 0.35, delay: i * 0.03, ease: EASE }}>
              <Row type={onPick ? "button" : undefined} onClick={onPick ? () => onPick(r) : undefined} aria-pressed={onPick ? on : undefined}
                className={`block w-full rounded-lg px-2 py-2 text-left ${onPick ? "transition hover:bg-wash" : ""} ${on ? "bg-wash" : ""}`}>
                <div className="flex items-baseline justify-between gap-3 text-sm">
                  <span className="min-w-0 truncate">{r.label}</span>
                  <span className="num shrink-0 font-medium">{format(r.value)}</span>
                </div>
                <div className="mt-1.5 h-2 overflow-hidden rounded-full bg-hair">
                  <motion.div className="h-2 origin-left rounded-full" initial={still ? false : { width: 0 }} animate={{ width: `${(num(r.value) / max) * 100}%`, background: colour }}
                    transition={{ duration: 0.7, delay: i * 0.05, ease: EASE }} />
                </div>
                {r.note && <p className="mt-1 text-xs text-graphite">{r.note}</p>}
              </Row>
            </motion.div>
          );
        })}
      </AnimatePresence>
    </div>
  );
}

// A ring that fills to a percentage, with whatever you pass as children in the middle.
export function Ring({ value, size = 150, tone = "brand", children }) {
  const still = useReducedMotion();
  const r = 54, c = 2 * Math.PI * r;
  return (
    <div className="relative shrink-0" style={{ width: size, height: size }}>
      <svg viewBox="0 0 128 128" className="h-full w-full -rotate-90" aria-hidden="true">
        <circle cx="64" cy="64" r={r} fill="none" stroke={HAIR} strokeWidth="10" />
        <motion.circle cx="64" cy="64" r={r} fill="none" stroke={TONES[tone]} strokeWidth="10" strokeLinecap="round" strokeDasharray={c}
          initial={still ? { strokeDashoffset: c * (1 - value / 100) } : { strokeDashoffset: c }} animate={{ strokeDashoffset: c * (1 - value / 100) }}
          transition={{ duration: 0.9, ease: EASE }} />
      </svg>
      <div className="absolute inset-0 flex items-center justify-center">{children}</div>
    </div>
  );
}

// A grid where deeper colour means a higher number. Hover a cell and its row and column light up.
export function Heatmap({ rows, columns, format = (v) => v, describe, columnLabel = (c) => c }) {
  const still = useReducedMotion();
  const [at, setAt] = useState(null);
  const all = rows.flatMap((r) => r.values);
  const lo = Math.min(...all), hi = Math.max(...all);
  const strength = (v) => 0.1 + 0.85 * ((v - lo) / (hi - lo || 1));
  const worst = rows.reduce((a, r, ri) => r.values.reduce((b, v, ci) => (v > b.v ? { v, ri, ci } : b), a), { v: -1 });
  const focus = at ?? worst;
  return (
    <div className="min-w-0">
      <div role="img" aria-label={describe} className="overflow-x-auto" onPointerLeave={() => setAt(null)}>
        <div className="grid min-w-[440px] gap-1.5 text-sm" style={{ gridTemplateColumns: `minmax(120px, 1.4fr) repeat(${columns.length}, minmax(0, 1fr))` }}>
          <span />
          {columns.map((c, ci) => <span key={c} className={`pb-1 text-center text-xs transition ${focus.ci === ci ? "font-semibold text-ink" : "text-graphite"}`}>{columnLabel(c)}</span>)}
          {rows.map((r, ri) => [
            <span key={r.label} className={`flex items-center pr-2 transition ${focus.ri === ri ? "font-semibold" : ""}`}>{r.label}</span>,
            ...r.values.map((v, ci) => {
              const dim = at && at.ri !== ri && at.ci !== ci, on = focus.ri === ri && focus.ci === ci;
              return (
                <motion.span key={`${r.label}-${ci}`} onPointerEnter={() => setAt({ v, ri, ci })}
                  className={`num flex h-12 cursor-default items-center justify-center rounded-lg font-medium transition-[opacity,box-shadow] ${dim ? "opacity-35" : ""} ${on ? "ring-2 ring-gold ring-offset-2" : ""}`}
                  style={{ background: `rgba(99,91,255,${strength(v).toFixed(2)})`, color: strength(v) > 0.55 ? "#fff" : INK }}
                  initial={still ? false : { opacity: 0, scale: 0.8 }} whileInView={{ opacity: dim ? 0.35 : 1, scale: 1 }} viewport={inView}
                  transition={{ duration: 0.35, delay: (ri * columns.length + ci) * 0.03, ease: EASE }}>
                  {format(v)}
                </motion.span>
              );
            }),
          ])}
        </div>
      </div>
      <p className="mt-4 rounded-lg bg-wash px-3.5 py-2.5 text-sm" aria-live="polite">
        <span className="font-semibold">{rows[focus.ri].label}</span> in {columnLabel(columns[focus.ci])}: <span className="num font-semibold">{format(focus.v)}</span> of parcels came back
        {focus.v === worst.v ? ", the highest on the board." : "."}
      </p>
    </div>
  );
}

// Bars that point right (raises risk, red) or left (lowers risk, teal) from a centre line.
export function FactorBars({ factors }) {
  const still = useReducedMotion();
  return (
    <div className="flex flex-col text-sm">
      <AnimatePresence initial={false} mode="popLayout">
        {factors.map((f, i) => {
          const up = f.effect !== "lowers risk";
          return (
            <motion.div key={f.label} layout={!still} initial={still ? false : { opacity: 0, x: up ? 12 : -12 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0 }}
              transition={{ duration: 0.35, delay: i * 0.05, ease: EASE }} className="flex flex-wrap items-center gap-x-3 gap-y-1 py-2">
              <div className="min-w-0 flex-[1_1_200px]"><span className="font-medium">{f.label}</span> <span className="text-graphite">{f.value}</span></div>
              <div className="flex flex-[1_1_180px] items-center">
                <div className="flex flex-1 justify-end">
                  {!up && <motion.div className="h-2.5 rounded-l-full bg-gain-fill" initial={still ? false : { width: 0 }} animate={{ width: `${f.size}%` }} transition={{ duration: 0.6, delay: 0.15 + i * 0.07, ease: EASE }} />}
                </div>
                <div className="flex-1 border-l border-ink py-1">
                  {up && <motion.div className="h-2.5 rounded-r-full bg-loss" initial={still ? false : { width: 0 }} animate={{ width: `${f.size}%` }} transition={{ duration: 0.6, delay: 0.15 + i * 0.07, ease: EASE }} />}
                </div>
              </div>
            </motion.div>
          );
        })}
      </AnimatePresence>
    </div>
  );
}
