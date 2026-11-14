import { count } from "../lib/format";
import { CountUp, Reveal } from "./motion";

// Small pieces the workspace pages share. Nothing here fetches data.

// A failed request, with a way to try again. Failed data is never replaced with sample figures.
export function SectionError({ message, onRetry, colSpan }) {
  const body = (
    <div role="alert" className="rounded-lg border border-loss px-4 py-3 text-sm text-loss">
      <p>Couldn't load this. {message}</p>
      {onRetry && <button type="button" onClick={onRetry} className="btn-quiet mt-3 px-4 py-2 text-sm text-ink">Try again</button>}
    </div>
  );
  return colSpan ? <tr><td colSpan={colSpan} className="px-3 py-4">{body}</td></tr> : body;
}

export function Loading({ text = "Loading…" }) {
  return <p className="text-sm text-graphite" role="status">{text}</p>;
}

// A headline number. tone: "gain" | "loss" | undefined.
export function Stat({ label, value, format, note, tone, delay = 0 }) {
  const colour = tone === "gain" ? "text-gain" : tone === "loss" ? "text-loss" : "";
  return (
    <Reveal delay={delay}>
      <div className="card h-full px-5 py-4">
        <p className="text-[13px] text-graphite">{label}</p>
        <CountUp value={value} format={format} className={`figure mt-1 block text-[30px] leading-tight ${colour}`} />
        {note && <p className="mt-0.5 text-[13px] text-graphite">{note}</p>}
      </div>
    </Reveal>
  );
}

// A row of choices where one is on. options: [[id, name], ...]
export function Chips({ options, value, onChange, label }) {
  return (
    <div className="flex flex-wrap gap-2" role="tablist" aria-label={label}>
      {options.map(([id, name]) => (
        <button key={id} type="button" role="tab" aria-selected={id === value} onClick={() => onChange(id)} className={id === value ? "chip-on" : "chip"}>{name}</button>
      ))}
    </div>
  );
}

// A table heading you can click to sort. sort is { key, dir } with dir 1 (ascending) or -1.
export function SortTh({ id, name, sort, onSort, right = true }) {
  const on = sort.key === id;
  return (
    <th className={`border-b border-rule px-1 py-1 font-medium ${right ? "text-right" : "text-left"}`} aria-sort={on ? (sort.dir > 0 ? "ascending" : "descending") : "none"}>
      <button type="button" onClick={() => onSort({ key: id, dir: on ? -sort.dir : -1 })} className={`rounded-md px-2 py-2 transition hover:bg-wash hover:text-ink ${on ? "text-ink" : ""}`}>
        {name} <span aria-hidden="true" className="font-mono text-xs">{on ? (sort.dir > 0 ? "↑" : "↓") : ""}</span>
      </button>
    </th>
  );
}

// Sort rows by a key. Text sorts by name, numbers by size, and missing values always go last.
export function sorted(rows, { key, dir }) {
  return [...rows].sort((a, b) => {
    const x = a[key], y = b[key];
    if (x == null && y == null) return 0;
    if (x == null) return 1;
    if (y == null) return -1;
    return (typeof x === "string" || typeof y === "string" ? String(x).localeCompare(String(y)) : x - y) * dir;
  });
}

// Previous and next for a paged list. total may be null when the API doesn't say how many there are;
// then `more` (was the last page full?) decides whether Next is offered.
export function Pager({ offset, limit, total, shown, onChange }) {
  const more = total == null ? shown === limit : offset + limit < total;
  if (!offset && !more) return null;
  const from = shown ? offset + 1 : 0, to = offset + shown;
  return (
    <div className="mt-4 flex flex-wrap items-center justify-between gap-3 text-sm">
      <p className="num text-graphite">{count(from)} to {count(to)}{total == null ? "" : ` of ${count(total)}`}</p>
      <div className="flex gap-2">
        <button type="button" disabled={!offset} onClick={() => onChange(Math.max(0, offset - limit))} className="btn-quiet px-4 py-2 text-sm disabled:opacity-40">Previous</button>
        <button type="button" disabled={!more} onClick={() => onChange(offset + limit)} className="btn-quiet px-4 py-2 text-sm disabled:opacity-40">Next</button>
      </div>
    </div>
  );
}

const BAND = { Low: "border border-rule text-graphite", Medium: "bg-caution-bg text-caution", High: "bg-caution-bg text-caution", "Very high": "bg-loss text-white" };

export function BandPill({ band }) {
  return <span className={`shrink-0 rounded-full px-2.5 py-0.5 text-xs font-medium ${BAND[band] || BAND.Low}`}>{band}</span>;
}

// The one line that explains FactorBars.
export function FactorLegend() {
  return (
    <p className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-graphite">
      <span className="flex items-center gap-1.5"><span aria-hidden="true" className="h-2 w-4 rounded-full bg-loss" />raises the risk</span>
      <span className="flex items-center gap-1.5"><span aria-hidden="true" className="h-2 w-4 rounded-full bg-gain-fill" />lowers the risk</span>
      <span>A longer bar means a stronger push.</span>
    </p>
  );
}
