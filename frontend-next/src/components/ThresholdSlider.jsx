import { motion } from "motion/react";
import { useState } from "react";
import { count, signedInr } from "../lib/format";

// Drag to choose the risk score above which COD is refused, and see what that cut-off would have done.
// rows: [{ threshold (percent), flagged, caught, good, net }], in rising threshold order.
// period: words for the time the numbers cover, e.g. "ten weeks". It only ever shows the rows it is given.
export default function ThresholdSlider({ rows, period, id = "cut" }) {
  const best = rows.reduce((a, r) => (r.net > a.net ? r : a), rows[0]);
  const [n, setN] = useState(Math.max(0, rows.indexOf(best)));
  const r = rows[Math.min(n, rows.length - 1)];
  const worthIt = best.net > 0;
  return (
    <div>
      <label htmlFor={id} className="flex items-baseline justify-between gap-3">
        <span className="font-semibold">Refuse COD when the risk score is above</span>
        <span className="figure text-3xl text-brand">{r.threshold}%</span>
      </label>
      <input id={id} type="range" min="0" max={rows.length - 1} step="1" value={n} onChange={(e) => setN(+e.target.value)} className="mt-4 h-2 w-full cursor-pointer accent-brand" />
      <div className="mt-1 flex justify-between font-mono text-xs text-graphite"><span>{rows[0].threshold}%</span><span>strict ← → relaxed</span><span>{rows[rows.length - 1].threshold}%</span></div>
      <div className="mt-6 grid grid-cols-3 gap-3 text-center">
        {[["COD orders flagged", r.flagged, ""], ["returns avoided", r.caught, "text-gain"], ["good buyers flagged", r.good, "text-loss"]].map(([label, v, colour]) => (
          <div key={label} className="rounded-xl bg-wash px-2 py-4">
            <motion.p key={v} initial={{ scale: 0.9, opacity: 0.4 }} animate={{ scale: 1, opacity: 1 }} className={`figure text-3xl ${colour}`}>{count(v)}</motion.p>
            <p className="mt-1 text-xs text-graphite">{label}</p>
          </div>
        ))}
      </div>
      <div className={`mt-4 flex flex-wrap items-baseline justify-between gap-2 rounded-xl px-5 py-4 ${r.net >= 0 ? "bg-gain/10" : "bg-loss/10"}`}>
        <span className="font-medium">Net effect{period ? ` over ${period}` : ""}</span>
        <span className={`figure text-3xl ${r.net >= 0 ? "text-gain" : "text-loss"}`}>{signedInr(r.net)}</span>
      </div>
      <p className="mt-3 text-sm text-graphite">
        {!worthIt ? "No cut-off pays for itself with these assumptions."
          : r === best ? "This is the best cut-off."
          : `The best cut-off is ${best.threshold}%, worth ${signedInr(best.net)}.`}
      </p>
    </div>
  );
}
