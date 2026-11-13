import { AnimatePresence, motion } from "motion/react";
import { useState } from "react";
import { Link } from "react-router-dom";
import { BarList, FactorBars, Heatmap, LineChart, Ring } from "../components/charts";
import { CountUp, Reveal } from "../components/motion";
import { SAMPLE } from "../data/sample";
import { count, inr, pct } from "../lib/format";

// Read-only demo built only from fields in SAMPLE. No API calls, no storage, no write actions.
// Anything the sample does not contain (an overall RTO rate, courier delivery speed, customer records)
// is not shown as a number.

const BAND = { Low: "border border-rule text-graphite", Medium: "bg-caution-bg text-caution", High: "bg-caution-bg text-caution", "Very high": "bg-loss text-white" };
const TONE = { Low: "gain", Medium: "brand", High: "loss", "Very high": "loss" };

function Panel({ title, note, children, className = "" }) {
  return (
    <section className={`card p-5 sm:p-6 ${className}`}>
      {title && <div className="mb-4"><h3 className="font-semibold">{title}</h3>{note && <p className="text-[13px] text-graphite">{note}</p>}</div>}
      {children}
    </section>
  );
}

function Heading({ id, eyebrow, title, sub }) {
  return (
    <div id={id} className="scroll-mt-40 pb-4 pt-12 first:pt-0">
      <p className="eyebrow">{eyebrow}</p>
      <h2 className="display mt-1.5 text-2xl sm:text-3xl">{title}</h2>
      {sub && <p className="mt-1.5 text-sm text-graphite">{sub}</p>}
    </div>
  );
}

function Tile({ label, value, format, note, tone, delay = 0 }) {
  const colour = tone === "gain" ? "text-gain" : tone === "loss" ? "text-loss" : "";
  return (
    <Reveal delay={delay}>
      <div className="card h-full px-5 py-4">
        <p className="text-[13px] text-graphite">{label}</p>
        <CountUp value={value} format={format} className={`figure mt-1 block text-[30px] leading-tight ${colour}`} />
        <p className="mt-0.5 text-[13px] text-graphite">{note}</p>
      </div>
    </Reveal>
  );
}

function Returns() {
  const cuts = Object.keys(SAMPLE.cuts);
  const [cut, setCut] = useState(cuts[0]);
  return (
    <Panel title="Return rate, cut five ways" note="Share of parcels that came back">
      <div className="mb-4 flex flex-wrap gap-2" role="tablist" aria-label="Cut the return rate by">
        {cuts.map((c) => <button key={c} type="button" role="tab" aria-selected={c === cut} onClick={() => setCut(c)} className={c === cut ? "chip-on" : "chip"}>{c}</button>)}
      </div>
      <div className="min-h-[230px]"><BarList key={cut} rows={SAMPLE.cuts[cut]} format={(v) => pct(v)} flagMax tone="brand" /></div>
      <AnimatePresence mode="wait">
        <motion.p key={cut} initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }} transition={{ duration: 0.25 }}
          className="mt-4 rounded-lg bg-wash px-3.5 py-2.5 text-sm">{SAMPLE.cutNotes[cut]}</motion.p>
      </AnimatePresence>
    </Panel>
  );
}

function RiskExamples() {
  const [i, setI] = useState(0);
  const o = SAMPLE.orders[i];
  const tone = TONE[o.band] || "brand";
  return (
    <div className="grid gap-4 lg:grid-cols-[1fr_1.5fr]">
      <Panel title="Three sample orders" note="Pick one">
        <div className="flex flex-col gap-2">
          {SAMPLE.orders.map((x, n) => (
            <button key={x.name} type="button" onClick={() => setI(n)} aria-pressed={n === i}
              className={`rounded-xl border px-4 py-3 text-left transition ${n === i ? "border-brand bg-wash shadow-[0_0_0_3px_rgba(99,91,255,0.15)]" : "border-rule hover:border-ink"}`}>
              <span className="flex items-center justify-between gap-2"><span className="font-semibold">{x.name}</span><span className={`shrink-0 rounded-full px-2.5 py-0.5 text-xs font-medium ${BAND[x.band]}`}>{x.band}</span></span>
              <span className="mt-1 block text-sm text-graphite">{x.detail}</span>
            </button>
          ))}
        </div>
      </Panel>
      <Panel>
        <p className="eyebrow">Sample order, not a live prediction</p>
        <div className="mt-3 flex flex-wrap items-center gap-5">
          <Ring value={o.risk} size={132} tone={tone}>
            <CountUp key={o.name} value={o.risk} format={(n) => pct(n)} duration={0.9} className={`figure text-2xl ${tone === "loss" ? "text-loss" : tone === "gain" ? "text-gain" : ""}`} />
          </Ring>
          <div className="min-w-0 flex-1">
            <p className="flex flex-wrap items-center gap-2"><span className={`rounded-full px-2.5 py-0.5 text-xs font-medium ${BAND[o.band]}`}>{o.band}</span><span className="text-sm text-graphite">Confidence: {o.confidence}</span></p>
            <p className="mt-2 font-medium">{o.action}</p>
          </div>
        </div>
        <h4 className="mt-6 font-semibold">What drove the score</h4>
        <div className="mt-2"><FactorBars factors={o.factors} /></div>
      </Panel>
    </div>
  );
}

function Economics() {
  // Each row: [threshold %, COD orders flagged, returns caught, good orders flagged, net ₹]
  const best = SAMPLE.thresholds.reduce((a, t) => (t[4] > a[4] ? t : a));
  return (
    <Panel title="What refusing COD above each score would have done" note="Over the sample's test period. Net = return costs saved minus margin lost on good orders flagged.">
      <div className="-mx-2 overflow-x-auto">
        <table className="num w-full min-w-[540px] text-sm">
          <thead><tr className="text-graphite">{["Refuse COD above", "Orders flagged", "Returns caught", "Good orders flagged", "Net"].map((h, i) => <th key={h} className={`border-b border-rule px-3 py-2.5 font-medium ${i ? "text-right" : "text-left"}`}>{h}</th>)}</tr></thead>
          <tbody>
            {SAMPLE.thresholds.map((t) => {
              const top = t === best;
              return (
                <tr key={t[0]} className={`border-b border-hair last:border-b-0 ${top ? "bg-wash" : ""}`}>
                  <td className="px-3 py-2.5 font-sans">{t[0]}%{top && <span className="ml-2 rounded-full border border-gold px-2 py-0.5 text-[11px] text-ink">best</span>}</td>
                  <td className="px-3 py-2.5 text-right">{count(t[1])}</td>
                  <td className="px-3 py-2.5 text-right">{count(t[2])}</td>
                  <td className="px-3 py-2.5 text-right">{count(t[3])}</td>
                  <td className={`px-3 py-2.5 text-right font-semibold ${t[4] < 0 ? "text-loss" : "text-gain"}`}>{inr(t[4])}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </Panel>
  );
}

export default function DemoDashboard() {
  const first = SAMPLE.monthlyRto[0], last = SAMPLE.monthlyRto[SAMPLE.monthlyRto.length - 1];
  const period = `${SAMPLE.monthNames[0]} to ${SAMPLE.monthNames[SAMPLE.monthNames.length - 1]}`;
  return (
    <>
      <div className="mb-7">
        <h1 className="display text-3xl leading-tight sm:text-4xl">Demo Workspace — Sample Data</h1>
        <p className="mt-1.5 text-sm text-graphite">A sample store · {period} · {count(SAMPLE.shipments)} shipments. Your own figures will differ.</p>
      </div>

      <Heading id="overview" eyebrow="Overview" title="The sample store at a glance" />
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <Tile label="Recoverable from couriers" value={SAMPLE.recoverable} format={inr} note={`${count(SAMPLE.findings)} charges to dispute`} tone="gain" />
        <Tile label="Spent on returned parcels" value={SAMPLE.rtoCost} format={inr} note="Courier cost of returns" tone="loss" delay={0.04} />
        <Tile label="Shipments" value={SAMPLE.shipments} format={count} note={period} delay={0.08} />
        <Tile label="RTO rate, latest month" value={last} format={(n) => pct(n)} note={`Down from ${pct(first)} in ${SAMPLE.monthNames[0]}`} delay={0.12} />
      </div>
      <ul className="mt-4 grid gap-2 sm:grid-cols-2">
        {SAMPLE.facts.map((f) => <li key={f} className="flex items-start gap-2.5 rounded-xl bg-sheet px-4 py-3 text-sm"><span aria-hidden="true" className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-[2px] bg-gold" />{f}</li>)}
      </ul>

      <Heading id="money" eyebrow="Money" title={`${inr(SAMPLE.recoverable)} the couriers owe back`} sub={`${count(SAMPLE.findings)} audit findings, by kind of overcharge.`} />
      <Panel title="Where the claim comes from"><BarList rows={SAMPLE.byKind.map((k) => ({ label: k.label, value: k.value }))} format={inr} tone="gain" /></Panel>

      <Heading id="trend" eyebrow="Trend" title="Monthly RTO rate" />
      <Panel>
        <LineChart values={SAMPLE.monthlyRto} names={SAMPLE.monthNames} labels={SAMPLE.monthLabels} max={40} height={280} describe="Monthly RTO rate in the sample data" />
      </Panel>

      <Heading id="returns" eyebrow="Returns" title="Where returns come from" />
      <Returns />

      <Heading id="couriers" eyebrow="Couriers" title="Return rate by courier and zone" sub="The sample covers return rates only. Delivery speed and billing per courier appear in your own workspace." />
      <Panel>
        <Heatmap rows={SAMPLE.heat.map((h) => ({ label: h.courier, values: h.values }))} columns={SAMPLE.zones} columnLabel={(c) => `Zone ${c}`}
          format={(v) => pct(v)} describe="Return rate by courier and delivery zone in the sample data" />
      </Panel>

      <Heading id="risk" eyebrow="Risk checker" title="How a new order gets scored" />
      <RiskExamples />
      <Panel className="mt-4" title="Strongest risk factors in the sample">
        <FactorBars factors={SAMPLE.factors} />
      </Panel>

      <Heading id="economics" eyebrow="Economics" title="Where to stop offering COD" />
      <Economics />

      <Heading id="customers" eyebrow="Customers" title="Customer segments" />
      <Panel>
        <p className="text-sm text-graphite">The sample contains no customer records, so there is nothing to list here. In your own workspace this section groups your customers into segments, such as loyal buyers, repeat returners and first-time buyers, and shows how much of your revenue and how many of your returns each group accounts for.</p>
      </Panel>

      <section className="card mt-12 flex flex-wrap items-center justify-between gap-4 p-6">
        <div>
          <p className="display text-2xl">See these numbers for your own store.</p>
          <p className="mt-1 text-sm text-graphite">Import your orders to start. Nothing from this demo is carried into your workspace.</p>
        </div>
        <div className="flex flex-wrap gap-3">
          <Link to="/signup" className="btn">Sign up</Link>
          <Link to="/login" className="btn-quiet">Log in</Link>
        </div>
      </section>
    </>
  );
}
