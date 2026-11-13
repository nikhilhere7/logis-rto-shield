import { AnimatePresence, motion } from "motion/react";
import { useState } from "react";
import { Link } from "react-router-dom";
import { PageHeader, Panel } from "../components/AppShell";
import { BarList, LineChart } from "../components/charts";
import FeatureAvailability, { WorkspaceError } from "../components/FeatureAvailability";
import { CountUp, Reveal } from "../components/motion";
import { featuresFor, uploadLink } from "../lib/features";
import { count, DASH, inr, inrShort, pct } from "../lib/format";
import { useApi } from "../lib/useApi";
import { useWorkspace } from "../lib/useWorkspace";
import Onboarding from "./Onboarding";

const PATHS = {
  overview: "/api/metrics/overview/", monthly: "/api/metrics/monthly/", byMode: "/api/metrics/rto/?by=payment_mode",
  couriers: "/api/metrics/delivery/?by=courier", courierRto: "/api/metrics/rto/?by=courier",
  audit: "/api/audit/summary/", segments: "/api/customers/segments/",
};
const SECTIONS = [["money", "Money"], ["trend", "Trend"], ["returns", "Returns"], ["couriers", "Couriers"], ["customers", "Customers"]];
const CUTS = [["payment_mode", "Payment"], ["zone", "Zone"], ["city", "City"], ["pincode", "Pincode"], ["sales_channel", "Channel"], ["first_order", "First order"], ["order_hour", "Hour"]];
const SERIES = [["rto_rate_pct", "RTO rate", (v) => pct(v), "brand"], ["orders", "Orders", (v) => count(v), "ink"], ["delivered_revenue_inr", "Delivered revenue", (v) => inrShort(v), "gain"], ["rto_courier_cost_inr", "Cost of returns", (v) => inrShort(v), "loss"]];
// The API sends months as "2024-01".
const monthName = (m) => (/^\d{4}-\d{2}$/.test(m || "") ? new Date(m + "-01").toLocaleString("en-IN", { month: "short", year: "2-digit" }) : DASH);
const list = (v) => (Array.isArray(v) ? v : []);
const avgDays = (d) => (d == null || !Number.isFinite(Number(d)) ? DASH : `${d} days on average`);

// The dashboard's error look, with a way to try again. Failed data is never replaced with sample figures.
function SectionError({ message, onRetry, colSpan }) {
  const body = (
    <div role="alert" className="rounded-lg border border-loss px-4 py-3 text-sm text-loss">
      <p>Couldn't load this section. {message}</p>
      {onRetry && <button type="button" onClick={onRetry} className="btn-quiet mt-3 px-4 py-2 text-sm text-ink">Try again</button>}
    </div>
  );
  return colSpan ? <tr><td colSpan={colSpan} className="px-3 py-4">{body}</td></tr> : body;
}

function Tile({ label, value, format, note, tone, to, delay = 0 }) {
  const colour = tone === "gain" ? "text-gain" : tone === "loss" ? "text-loss" : "";
  return (
    <Reveal delay={delay}>
      <a href={to} className="card group block px-5 py-4 transition hover:-translate-y-0.5 hover:border-brand hover:shadow-[0_16px_32px_-20px_rgba(99,91,255,0.55)]">
        <p className="flex items-center justify-between text-[13px] text-graphite">{label}<span aria-hidden="true" className="opacity-0 transition group-hover:opacity-100">↓</span></p>
        <CountUp value={value} format={format} className={`figure mt-1 block text-[30px] leading-tight ${colour}`} />
        <p className="mt-0.5 text-[13px] text-graphite">{note}</p>
      </a>
    </Reveal>
  );
}

// Orders are in but no parcel has a delivered or returned outcome yet: one quiet strip, not a wall of zeros.
function NextStrip({ counts }) {
  const loaded = Number(counts.shipments) > 0;
  return (
    <div className="mb-6 flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-rule bg-wash px-5 py-4">
      <p className="text-sm">
        <span className="font-semibold">{loaded ? "Waiting for delivery outcomes." : "Next: import your shipments."}</span>{" "}
        <span className="text-graphite">{loaded
          ? "Your shipments are loaded, but none is marked delivered or returned yet. Import an updated shipment report when outcomes are in."
          : "The shipment report unlocks delivery, RTO and courier analytics."}</span>
      </p>
      <Link to={uploadLink("shipments")} className="btn py-2.5 text-sm">Import shipments</Link>
    </div>
  );
}

// Billing audit and COD reconciliation live in the money section. Each one shows its findings when its
// files are in, or its FeatureAvailability panel when they are not.
function MoneyGate({ audit, features }) {
  const auditOn = features.audit.status === "available", codOn = features.cod.status === "available";
  if (!auditOn && !codOn) {
    return (
      <div className="grid gap-4 md:grid-cols-2">
        <FeatureAvailability {...features.audit} />
        <FeatureAvailability {...features.cod} />
      </div>
    );
  }
  return (
    <div className="flex flex-col gap-4">
      {auditOn && features.audit.note && (
        <div className="flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-rule bg-wash px-5 py-4 text-sm">
          <p className="text-graphite">{features.audit.note}</p>
          <Link to={features.audit.noteAction.to} className="btn-quiet py-2 text-sm">{features.audit.noteAction.label}</Link>
        </div>
      )}
      <Money audit={audit} />
      {!auditOn && <FeatureAvailability {...features.audit} />}
      {!codOn && <FeatureAvailability {...features.cod} />}
    </div>
  );
}

// Pick how to cut the RTO rate; the bars are fetched for that cut.
function Returns() {
  const [by, setBy] = useState("payment_mode");
  const floor = by === "pincode" || by === "city" ? "&min_shipments=30" : "";
  const { data, error, loading, reload } = useApi({ rows: `/api/metrics/rto/?by=${by}${floor}` });
  const label = (r) => {
    const v = r[by];
    if (by === "first_order") return v ? "First order" : "Repeat order";
    if (by === "order_hour") return v == null ? "Not recorded" : `${String(v).padStart(2, "0")}:00`;
    if (by === "zone") return v ? `Zone ${v}` : "No zone on file";
    return String(v || "Not recorded");
  };
  const rows = list(data?.rows).slice(0, 8).map((r) => ({ id: String(r[by]), label: label(r), value: r.rto_rate_pct ?? 0, note: `${count(r.shipments)} parcels · ${count(r.rto)} returned` }));
  return (
    <Panel title="Who sends parcels back?" note={by === "pincode" || by === "city" ? "At least 30 parcels each" : null}>
      <div className="mb-4 flex flex-wrap gap-2" role="tablist" aria-label="Cut the RTO rate by">
        {CUTS.map(([id, name]) => <button key={id} type="button" role="tab" aria-selected={id === by} onClick={() => setBy(id)} className={id === by ? "chip-on" : "chip"}>{name}</button>)}
      </div>
      <div className="min-h-[280px]">
        {error ? <SectionError message={error} onRetry={reload} />
          : loading ? <p className="text-sm text-graphite" role="status">Loading…</p>
          : !Array.isArray(data?.rows) ? <SectionError message="The server sent an unexpected response." onRetry={reload} />
          : !rows.length ? <p className="text-sm text-graphite">No shipments to compare for this cut yet.</p>
          : <BarList key={by} rows={rows} format={(v) => pct(v)} flagMax tone="brand" />}
      </div>
    </Panel>
  );
}

// Click a kind of overcharge to see the biggest parcels behind it.
// The audit summary labels each kind with `label`; rows are picked and keyed by the stable `kind` code.
function Money({ audit }) {
  const kinds = list(audit?.by_kind);
  const [kind, setKind] = useState(kinds[0]?.kind);
  // GET /api/audit/findings/ returns a bare array of findings.
  const { data, error, loading, reload } = useApi(kind ? { findings: `/api/audit/findings/?kind=${encodeURIComponent(kind)}&limit=6` } : {});
  if (!kinds.length) return <Panel title="Nothing to claim yet"><p className="text-sm text-graphite">Upload courier invoices, a rate card and COD statements to run the audit.</p></Panel>;
  const picked = kinds.find((k) => k.kind === kind);
  const findings = !loading && !error && Array.isArray(data?.findings) ? data.findings : null;
  const invalid = !loading && !error && kind && !Array.isArray(data?.findings);
  return (
    <div className="grid gap-4 xl:grid-cols-[1fr_1.4fr]">
      <Panel title="Where the claim comes from" note="Click a row">
        <BarList rows={kinds.map((k) => ({ id: k.kind, label: k.label || k.kind, value: k.claim_inr, note: `${count(k.findings)} parcels` }))} format={inr} tone="gain" picked={kind} onPick={(r) => setKind(r.id)} />
      </Panel>
      <Panel title={picked?.label || picked?.kind} note={findings ? `Largest ${findings.length} of ${count(picked?.findings)}` : null} action={<Link to="/app/audit" className="text-sm font-medium text-brand-deep underline underline-offset-4">Open the audit</Link>}>
        <div className="-mx-2 overflow-x-auto">
          <table className="num w-full min-w-[560px] text-sm">
            <thead><tr className="text-left text-graphite">{["Courier", "AWB", "Why", "Claim"].map((h, i) => <th key={h} className={`border-b border-rule px-3 py-2.5 font-medium ${i === 3 ? "text-right" : ""}`}>{h}</th>)}</tr></thead>
            <AnimatePresence mode="wait">
              <motion.tbody key={`${kind}-${findings ? "y" : "n"}`} initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} transition={{ duration: 0.2 }}>
                {(findings || []).map((f, i) => (
                  <tr key={f.id ?? `${f.awb_number}-${f.line_ref}-${i}`} className="border-b border-hair last:border-b-0">
                    <td className="px-3 py-3 font-sans">{f.courier_name}</td>
                    <td className="px-3 py-3 font-mono text-xs">{f.awb_number}</td>
                    <td className="px-3 py-3 font-sans text-graphite">{f.detail}</td>
                    <td className="px-3 py-3 text-right font-semibold text-gain">{inr(f.claim_inr)}</td>
                  </tr>
                ))}
                {loading && <tr><td colSpan="4" className="px-3 py-6 text-graphite" role="status">Loading…</td></tr>}
                {error && <SectionError message={error} onRetry={reload} colSpan="4" />}
                {invalid && <SectionError message="The server sent an unexpected response." onRetry={reload} colSpan="4" />}
                {findings && !findings.length && <tr><td colSpan="4" className="px-3 py-6 text-graphite">No findings of this kind.</td></tr>}
              </motion.tbody>
            </AnimatePresence>
          </table>
        </div>
      </Panel>
    </div>
  );
}

// Click a column heading to sort.
function Couriers({ couriers, rtoOf }) {
  const [sort, setSort] = useState({ key: "rto", dir: -1 });
  const rows = couriers.map((c) => ({ ...c, rto: rtoOf[c.courier] }));
  rows.sort((a, b) => (sort.key === "courier" ? String(a.courier ?? "").localeCompare(String(b.courier ?? "")) : (a[sort.key] ?? 0) - (b[sort.key] ?? 0)) * sort.dir);
  const cols = [["courier", "Courier"], ["shipments", "Shipments"], ["rto", "RTO rate"], ["on_time_pct", "On time"], ["first_attempt_delivery_pct", "First attempt"], ["avg_delivery_days", "Avg days"], ["avg_billed_per_shipment_inr", "Billed per parcel"]];
  const rtos = rows.map((r) => r.rto).filter((v) => v != null), times = rows.map((r) => r.on_time_pct).filter((v) => v != null);
  const worst = rtos.length > 1 ? Math.max(...rtos) : null, slow = times.length > 1 ? Math.min(...times) : null;
  return (
    <Panel title="Courier performance" note="Click a heading to sort" action={<Link to="/app/couriers" className="text-sm font-medium text-brand-deep underline underline-offset-4">All couriers</Link>}>
      <div className="-mx-2 overflow-x-auto">
        <table className="num w-full min-w-[760px] text-sm">
          <thead>
            <tr className="text-graphite">
              {cols.map(([key, name], i) => (
                <th key={key} className={`border-b border-rule px-1 py-1 font-medium ${i ? "text-right" : "text-left"}`} aria-sort={sort.key === key ? (sort.dir > 0 ? "ascending" : "descending") : "none"}>
                  <button type="button" onClick={() => setSort({ key, dir: sort.key === key ? -sort.dir : -1 })} className={`rounded-md px-2 py-2 transition hover:bg-wash hover:text-ink ${sort.key === key ? "text-ink" : ""}`}>
                    {name} <span aria-hidden="true" className="font-mono text-xs">{sort.key === key ? (sort.dir > 0 ? "↑" : "↓") : ""}</span>
                  </button>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((c, i) => (
              <motion.tr layout key={c.courier ?? `unknown-${i}`} className="border-b border-hair last:border-b-0">
                <td className="px-3 py-3.5 font-sans font-medium">{c.courier ?? "Unknown courier"}</td>
                <td className="px-3 py-3.5 text-right">{count(c.shipments)}</td>
                <td className={`px-3 py-3.5 text-right ${worst != null && c.rto === worst ? "font-semibold text-loss" : ""}`}>{pct(c.rto)}</td>
                <td className={`px-3 py-3.5 text-right ${slow != null && c.on_time_pct === slow ? "font-semibold text-loss" : ""}`}>{pct(c.on_time_pct)}</td>
                <td className="px-3 py-3.5 text-right">{pct(c.first_attempt_delivery_pct)}</td>
                <td className="px-3 py-3.5 text-right">{c.avg_delivery_days ?? DASH}</td>
                <td className="px-3 py-3.5 text-right">{inr(c.avg_billed_per_shipment_inr)}</td>
              </motion.tr>
            ))}
          </tbody>
        </table>
      </div>
    </Panel>
  );
}

// Click a segment to see who is in it.
function Customers({ segments }) {
  const [seg, setSeg] = useState(segments.find((s) => s.segment === "Repeat returner")?.segment || segments[0]?.segment);
  // GET /api/customers/ returns { count, results: [...] }.
  const { data, error, loading, reload } = useApi(seg ? { page: `/api/customers/?segment=${encodeURIComponent(seg)}&sort=${seg === "Loyal" ? "value" : "returned"}&limit=6` } : {});
  const s = segments.find((x) => x.segment === seg);
  const rows = !loading && !error && Array.isArray(data?.page?.results) ? data.page.results : null;
  const invalid = !loading && !error && seg && !rows;
  if (!segments.length) return <Panel title="Customers by segment"><p className="text-sm text-graphite">No customers with a delivery outcome yet.</p></Panel>;
  return (
    <div className="grid gap-4 xl:grid-cols-[1fr_1.4fr]">
      <Panel title="Customers by segment" note="Click a row">
        <BarList rows={segments.map((x) => ({ id: x.segment, label: x.segment, value: x.customers, note: x.rto_rate_pct == null ? "no outcomes yet" : `${pct(x.rto_rate_pct)} returned · ${pct(x.revenue_share_pct)} of revenue` }))}
          format={count} tone="ink" picked={seg} onPick={(r) => setSeg(r.id)} />
      </Panel>
      <Panel title={seg} note={s?.meaning} action={<Link to="/app/customers" className="text-sm font-medium text-brand-deep underline underline-offset-4">All customers</Link>}>
        <div className="-mx-2 overflow-x-auto">
          <table className="num w-full min-w-[520px] text-sm">
            <thead><tr className="text-left text-graphite">{["Customer", "Pays by", "Parcels", "Returned", "Delivered value"].map((h, i) => <th key={h} className={`border-b border-rule px-3 py-2.5 font-medium ${i > 1 ? "text-right" : ""}`}>{h}</th>)}</tr></thead>
            <tbody>
              {(rows || []).map((c, i) => (
                <tr key={c.customer_id ?? i} className="border-b border-hair last:border-b-0">
                  <td className="px-3 py-3 font-sans"><span className="font-medium">{c.name || c.customer_id}</span><span className="block text-xs text-graphite">{c.pincode}</span></td>
                  <td className="px-3 py-3 font-sans">{c.payment_preference}</td>
                  <td className="px-3 py-3 text-right">{count(c.parcels)}</td>
                  <td className={`px-3 py-3 text-right ${c.returned ? "font-semibold text-loss" : ""}`}>{count(c.returned)}</td>
                  <td className="px-3 py-3 text-right">{inr(c.delivered_value_inr)}</td>
                </tr>
              ))}
              {loading && <tr><td colSpan="5" className="px-3 py-6 text-graphite" role="status">Loading…</td></tr>}
              {error && <SectionError message={error} onRetry={reload} colSpan="5" />}
              {invalid && <SectionError message="The server sent an unexpected response." onRetry={reload} colSpan="5" />}
              {rows && !rows.length && <tr><td colSpan="5" className="px-3 py-6 text-graphite">No customers in this segment.</td></tr>}
            </tbody>
          </table>
        </div>
      </Panel>
    </div>
  );
}

function Heading({ id, eyebrow, title }) {
  return <div id={id} className="scroll-mt-28 pb-4 pt-12"><p className="eyebrow">{eyebrow}</p><h2 className="display mt-1.5 text-2xl sm:text-3xl">{title}</h2></div>;
}

// Which dashboard to show is decided only from the workspace counts, never from a metric being zero.
export default function Dashboard() {
  const ws = useWorkspace();
  if (ws.status === "loading") return <p className="text-graphite" role="status">Loading your workspace…</p>;
  if (ws.status === "error") return <WorkspaceError message={ws.message} onRetry={ws.retry} />;
  const features = featuresFor(ws.counts, ws.model);
  if (!(Number(ws.counts.orders) > 0)) return <Onboarding counts={ws.counts} model={ws.model} />;
  if (!(Number(ws.counts.shipments_with_outcome) > 0)) return <OrdersDashboard counts={ws.counts} features={features} />;
  return <FullDashboard features={features} />;
}

function LoadError({ error, reload }) {
  return (
    <div role="alert" className="max-w-xl rounded-lg border border-loss px-4 py-3 text-loss">
      <p>Couldn't load the dashboard. {error}</p>
      <button type="button" onClick={reload} className="btn-quiet mt-3 px-4 py-2 text-sm text-ink">Try again</button>
    </div>
  );
}

// Orders and customers, no delivery outcomes yet. Only figures the APIs return correctly without shipments:
// overview.total_orders and cancelled_orders, monthly orders and order value, and the customer endpoints.
const ORDER_PATHS = { overview: "/api/metrics/overview/", monthly: "/api/metrics/monthly/", segments: "/api/customers/segments/" };
const ORDER_SERIES = [["orders", "Orders", (v) => count(v), "ink"], ["order_value_inr", "Order value", (v) => inrShort(v), "brand"]];

function OrdersDashboard({ counts, features }) {
  const { data, error, loading, reload } = useApi(ORDER_PATHS);
  const [series, setSeries] = useState(ORDER_SERIES[0]);
  if (loading) return <p className="text-graphite" role="status">Loading your numbers…</p>;
  if (error) return <LoadError error={error} reload={reload} />;
  const o = data.overview ?? {};
  const months = list(data.monthly);
  const value = months.reduce((sum, m) => sum + (Number(m.order_value_inr) || 0), 0);
  const labels = months.length > 1 ? [...new Set([0, Math.floor((months.length - 1) / 2), months.length - 1])].map((i) => [i, monthName(months[i].month)]) : [];
  const [key, , format, tone] = series;
  const period = months.length ? `${monthName(months[0].month)} to ${monthName(months[months.length - 1].month)} · ` : "";

  return (
    <>
      <PageHeader title="Dashboard" sub={`${period}${count(o.total_orders)} orders`}>
        <Link to="/app/uploads" className="btn-quiet py-2.5 text-sm">Upload new data</Link>
      </PageHeader>
      <NextStrip counts={counts} />

      <div className="grid gap-4 sm:grid-cols-3">
        <Tile to="#trend" label="Orders" value={o.total_orders} format={count} note={`${count(o.cancelled_orders)} cancelled before dispatch`} />
        <Tile to="#trend" label="Order value" value={value} format={inrShort} note="Orders not cancelled" delay={0.04} />
        <Tile to="#customers" label="Customers" value={counts.customers} format={count} note="Who have placed an order" delay={0.08} />
      </div>

      <Heading id="trend" eyebrow="Trend" title="How orders are moving" />
      <Panel>
        <div className="mb-4 flex flex-wrap gap-2" role="tablist" aria-label="Series to chart">
          {ORDER_SERIES.map((s) => <button key={s[0]} type="button" role="tab" aria-selected={s === series} onClick={() => setSeries(s)} className={s === series ? "chip-on" : "chip"}>{s[1]}</button>)}
        </div>
        {months.length > 1 ? (
          <LineChart key={key} values={months.map((m) => m[key] ?? 0)} names={months.map((m) => monthName(m.month))} labels={labels} format={format} tone={tone} height={300}
            describe={`${series[1]} by month`} />
        ) : <p className="text-sm text-graphite">Not enough months of data to draw a trend yet.</p>}
      </Panel>

      <Heading id="deliveries" eyebrow="Deliveries" title="Returns and couriers" />
      <div className="grid gap-4 md:grid-cols-2">
        <FeatureAvailability {...features.rto} />
        <FeatureAvailability {...features.couriers} />
      </div>

      <Heading id="customers" eyebrow="Customers" title="Who you are selling to" />
      <Customers segments={list(data.segments)} />
    </>
  );
}

// The full dashboard, unchanged except that the money section follows audit and COD readiness.
function FullDashboard({ features }) {
  const { data, error, loading, reload } = useApi(PATHS);
  const [series, setSeries] = useState(SERIES[0]);

  if (loading) return <p className="text-graphite" role="status">Loading your numbers…</p>;
  if (error) return <LoadError error={error} reload={reload} />;
  const o = data.overview ?? {};

  const audit = data.audit ?? {};
  const moneyOn = features.audit.status === "available" || features.cod.status === "available";
  const mode = Object.fromEntries(list(data.byMode).map((m) => [m.payment_mode, m.rto_rate_pct]));
  const months = list(data.monthly);
  const labels = months.length > 1 ? [...new Set([0, Math.floor((months.length - 1) / 2), months.length - 1])].map((i) => [i, monthName(months[i].month)]) : [];
  const rtoOf = Object.fromEntries(list(data.courierRto).map((c) => [c.courier, c.rto_rate_pct]));
  const [key, , format, tone] = series;
  const period = months.length ? `${monthName(months[0].month)} to ${monthName(months[months.length - 1].month)} · ` : "";

  return (
    <>
      <PageHeader title="Dashboard" sub={`${period}${count(o.total_shipments)} shipments`}>
        <Link to="/app/uploads" className="btn-quiet py-2.5 text-sm">Upload new data</Link>
      </PageHeader>

      <nav aria-label="Dashboard sections" className="sticky top-0 z-10 -mx-5 mb-5 flex gap-2 overflow-x-auto border-b border-rule bg-paper/90 px-5 py-2.5 backdrop-blur sm:-mx-8 sm:px-8 lg:-mx-10 lg:px-10">
        {SECTIONS.map(([id, name]) => <a key={id} href={`#${id}`} className="chip whitespace-nowrap">{name}</a>)}
      </nav>

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        {moneyOn
          ? <Tile to="#money" label="Recoverable from couriers" value={audit.total_recoverable_inr} format={inr} note={`${count((audit.billing_findings ?? 0) + (audit.cod_findings ?? 0))} charges to dispute`} tone="gain" />
          : <Tile to="#money" label="Recoverable from couriers" value={null} format={inr} note="Needs courier invoices or COD remittances" />}
        <Tile to="#returns" label="Spent on returned parcels" value={o.rto_courier_cost_inr} format={inr} note={`${count(o.rto)} parcels came back`} tone="loss" delay={0.04} />
        <Tile to="#returns" label="RTO rate" value={o.rto_rate_pct} format={(n) => pct(n)} note={`COD ${pct(mode.COD)} · Prepaid ${pct(mode.Prepaid)}`} delay={0.08} />
        <Tile to="#couriers" label="On-time delivery" value={o.on_time_pct} format={(n) => pct(n)} note={avgDays(o.avg_delivery_days)} delay={0.12} />
        <Tile to="#trend" label="Orders" value={o.total_orders} format={count} note={`${count(o.cancelled_orders)} cancelled before dispatch`} delay={0.16} />
        <Tile to="#trend" label="Delivered revenue" value={o.delivered_revenue_inr} format={inrShort} note={`${inrShort(o.rto_order_value_inr)} of orders returned`} delay={0.2} />
        <Tile to="#couriers" label="Delivered" value={o.delivered_rate_pct} format={(n) => pct(n)} note={`${count(o.delivered)} of ${count(o.total_shipments)}`} delay={0.24} />
        <Tile to="#customers" label="COD share" value={o.cod_share_pct} format={(n) => pct(n)} note="of all shipments" delay={0.28} />
      </div>

      <Heading id="money" eyebrow="Money" title={moneyOn ? `${inr(audit.total_recoverable_inr ?? 0)} is waiting to be claimed` : "Find what couriers owe you"} />
      <MoneyGate audit={audit} features={features} />

      <Heading id="trend" eyebrow="Trend" title="How the business is moving" />
      <Panel>
        <div className="mb-4 flex flex-wrap gap-2" role="tablist" aria-label="Series to chart">
          {SERIES.map((s) => <button key={s[0]} type="button" role="tab" aria-selected={s === series} onClick={() => setSeries(s)} className={s === series ? "chip-on" : "chip"}>{s[1]}</button>)}
        </div>
        {months.length > 1 ? (
          <LineChart key={key} values={months.map((m) => m[key] ?? 0)} names={months.map((m) => monthName(m.month))} labels={labels} format={format} tone={tone} height={300}
            describe={`${series[1]} by month`} />
        ) : <p className="text-sm text-graphite">Not enough months of data to draw a trend yet.</p>}
      </Panel>

      <Heading id="returns" eyebrow="Returns" title="Where returns come from" />
      <Returns />

      <Heading id="couriers" eyebrow="Couriers" title="Who delivers, and who doesn't" />
      <Couriers couriers={list(data.couriers)} rtoOf={rtoOf} />

      <Heading id="customers" eyebrow="Customers" title="Who you are selling to" />
      <Customers segments={list(data.segments)} />
    </>
  );
}
