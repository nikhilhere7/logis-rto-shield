import { motion } from "motion/react";
import { useState } from "react";
import { Link } from "react-router-dom";
import { PageHeader, Panel } from "../components/AppShell";
import { BarList } from "../components/charts";
import FeatureAvailability from "../components/FeatureAvailability";
import { Chips, Loading, SectionError, SortTh, sorted } from "../components/parts";
import { featuresFor } from "../lib/features";
import { count, DASH, inr, pct } from "../lib/format";
import { useApi } from "../lib/useApi";
import { useWorkspace } from "../lib/useWorkspace";

const days = (v) => (v == null ? DASH : `${v} days`);
// [key, name, format, which end is bad, needs, how to say who is worst]
const METRICS = [
  ["rto_rate_pct", "Return rate", (v) => pct(v), "high", null, "has the highest return rate"],
  ["on_time_pct", "On time", (v) => pct(v), "low", null, "is on time least often"],
  ["first_attempt_delivery_pct", "Delivered first attempt", (v) => pct(v), "low", null, "delivers on the first attempt least often"],
  ["avg_delivery_days", "Days to deliver", days, "high", null, "takes the longest to deliver"],
  ["avg_billed_per_shipment_inr", "Billed per parcel", inr, "high", null, "bills the most per parcel"],
  ["claim_inr", "Owed to you", inr, "high", "money", "owes you the most"],
];
const COLS = [["courier", "Courier"], ["shipments", "Parcels"], ["rto_rate_pct", "Return rate"], ["delivered_rate_pct", "Delivered"], ["on_time_pct", "On time"],
  ["first_attempt_delivery_pct", "First attempt"], ["avg_delivery_days", "Days to deliver"], ["avg_days_order_to_pickup", "Days to pickup"], ["avg_billed_per_shipment_inr", "Billed per parcel"]];
const list = (v) => (Array.isArray(v) ? v : []);
const name = (c) => c ?? "Unknown courier";

export default function Couriers() {
  const ws = useWorkspace();
  const features = featuresFor(ws.counts, ws.model);
  const money = features.audit.status === "available" || features.cod.status === "available";
  const codOn = features.cod.status === "available";
  const { data, error, loading, reload } = useApi({
    delivery: "/api/metrics/delivery/?by=courier", rto: "/api/metrics/rto/?by=courier",
    ...(money ? { audit: "/api/audit/summary/" } : {}), ...(codOn ? { cod: "/api/metrics/cod/" } : {}),
  });
  const [metric, setMetric] = useState("rto_rate_pct");
  const [picked, setPicked] = useState(null);
  const [sort, setSort] = useState({ key: "shipments", dir: -1 });

  if (loading && !data) return <><PageHeader title="Couriers" /><Loading text="Loading your couriers…" /></>;
  if (error) return <><PageHeader title="Couriers" /><SectionError message={error} onRetry={reload} /></>;

  const rtoOf = Object.fromEntries(list(data.rto).map((r) => [r.courier, r]));
  const claimOf = Object.fromEntries(list(data.audit?.by_courier).map((r) => [r.courier, r]));
  const codOf = Object.fromEntries(list(data.cod).map((r) => [r.courier, r]));
  const rows = list(data.delivery).map((d) => ({
    ...d, rto: rtoOf[d.courier]?.rto ?? null, rto_rate_pct: rtoOf[d.courier]?.rto_rate_pct ?? null,
    rto_courier_cost_inr: rtoOf[d.courier]?.rto_courier_cost_inr ?? null, cod_share_pct: rtoOf[d.courier]?.cod_share_pct ?? null,
    claim_inr: money ? claimOf[d.courier]?.claim_inr ?? 0 : null, findings: claimOf[d.courier]?.findings ?? 0,
  }));
  if (!rows.length) return <><PageHeader title="Couriers" /><Panel><p className="text-graphite">No shipments with a courier on record yet.</p></Panel></>;

  const metrics = METRICS.filter((m) => m[4] !== "money" || money);
  const [key, , format, bad, , saying] = metrics.find((m) => m[0] === metric) || metrics[0];
  const chosen = rows.find((r) => r.courier === picked) || rows[0];
  const values = rows.map((r) => r[key]).filter((v) => v != null);
  const worst = values.length > 1 ? (bad === "high" ? Math.max(...values) : Math.min(...values)) : null;
  const worstRow = rows.find((r) => r[key] === worst);
  const kinds = list(data.audit?.by_courier_kind).filter((k) => k.courier === chosen.courier);
  const cod = codOf[chosen.courier];
  const worstOf = (k, end) => {
    const v = rows.map((r) => r[k]).filter((x) => x != null);
    return v.length > 1 ? (end === "high" ? Math.max(...v) : Math.min(...v)) : null;
  };

  return (
    <>
      <PageHeader title="Couriers" sub={`${count(rows.length)} couriers · ${count(rows.reduce((n, r) => n + r.shipments, 0))} parcels`} />

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
        {sorted(rows, { key: "shipments", dir: -1 }).map((c, i) => {
          const on = chosen.courier === c.courier;
          return (
            <motion.button key={name(c.courier)} type="button" onClick={() => setPicked(c.courier)} aria-pressed={on}
              initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.35, delay: i * 0.05 }}
              className={`card px-5 py-4 text-left transition hover:-translate-y-0.5 hover:border-brand ${on ? "border-brand bg-wash shadow-[0_0_0_3px_rgba(99,91,255,0.15)]" : ""}`}>
              <p className="font-semibold">{name(c.courier)}</p>
              <p className="num text-[13px] text-graphite">{count(c.shipments)} parcels</p>
              <div className="num mt-3 grid grid-cols-3 gap-2 text-sm">
                <div><p className={`figure text-xl ${c.rto_rate_pct != null && c.rto_rate_pct === worstOf("rto_rate_pct", "high") ? "text-loss" : ""}`}>{pct(c.rto_rate_pct)}</p><p className="text-xs text-graphite">returned</p></div>
                <div><p className={`figure text-xl ${c.on_time_pct != null && c.on_time_pct === worstOf("on_time_pct", "low") ? "text-loss" : ""}`}>{pct(c.on_time_pct)}</p><p className="text-xs text-graphite">on time</p></div>
                <div><p className="figure text-xl">{c.avg_delivery_days ?? DASH}</p><p className="text-xs text-graphite">days to deliver</p></div>
              </div>
            </motion.button>
          );
        })}
      </div>

      <div className="mt-4 grid gap-4 xl:grid-cols-[1.2fr_1fr]">
        <Panel title="Compare your couriers" note="Click a bar to open that courier">
          <div className="mb-4"><Chips options={metrics.map((m) => [m[0], m[1]])} value={key} onChange={setMetric} label="Measure to compare" /></div>
          <BarList key={key} rows={sorted(rows, { key, dir: -1 }).map((r) => ({ id: name(r.courier), label: name(r.courier), value: r[key] ?? 0, note: r[key] == null ? "not recorded" : null }))}
            format={format} tone="brand" picked={name(chosen.courier)} onPick={(r) => setPicked(rows.find((x) => name(x.courier) === r.id)?.courier ?? null)} />
          {worstRow && <p className="mt-4 rounded-lg bg-wash px-3.5 py-2.5 text-sm"><span className="font-semibold">{name(worstRow.courier)}</span> {saying}: <span className="num font-semibold">{format(worst)}</span>.</p>}
        </Panel>

        <Panel title={name(chosen.courier)} note="The courier you picked">
          <dl className="num grid grid-cols-2 gap-x-6 gap-y-3 text-sm">
            {[["Parcels returned", `${count(chosen.rto)} (${pct(chosen.rto_rate_pct)})`], ["Courier charges on returns", inr(chosen.rto_courier_cost_inr)], ["Share that was COD", pct(chosen.cod_share_pct)],
              ["Delivered", pct(chosen.delivered_rate_pct)], ["Order to pickup", days(chosen.avg_days_order_to_pickup)], ["Pickup to delivery", days(chosen.avg_delivery_days)]].map(([k, v]) => (
              <div key={k}><dt className="font-sans text-xs text-graphite">{k}</dt><dd className="font-medium">{v}</dd></div>
            ))}
          </dl>
          {money ? (
            <div className="mt-5 border-t border-rule pt-4">
              <div className="flex flex-wrap items-baseline justify-between gap-2">
                <h3 className="font-semibold">Owed to you by this courier</h3>
                <span className="figure text-2xl text-gain">{inr(chosen.claim_inr)}</span>
              </div>
              {kinds.length ? <div className="mt-2"><BarList key={name(chosen.courier)} rows={kinds.map((k) => ({ id: k.kind, label: k.label || k.kind, value: k.claim_inr, note: `${count(k.findings)} parcels` }))} format={inr} tone="gain" /></div>
                : <p className="mt-2 text-sm text-graphite">Nothing to claim from this courier.</p>}
              {cod && <p className="num mt-3 text-sm text-graphite">COD collected on {count(cod.cod_delivered_shipments)} delivered parcels: {inr(cod.cod_due_inr)} due, {inr(cod.cod_remitted_inr)} paid, <span className={cod.gap_inr > 0 ? "font-semibold text-loss" : ""}>{inr(cod.gap_inr)} missing</span>.</p>}
              {chosen.courier && <Link to={`/app/audit?courier=${encodeURIComponent(chosen.courier)}`} className="btn-quiet mt-4 py-2.5 text-sm">See every disputed charge</Link>}
            </div>
          ) : <FeatureAvailability {...features.audit} className="mt-5" />}
        </Panel>
      </div>

      <Panel className="mt-4" title="Every measure, side by side" note="Click a heading to sort. Red marks the weakest courier on that measure.">
        <div className="-mx-2 overflow-x-auto">
          <table className="num w-full min-w-[920px] text-sm">
            <thead><tr className="text-graphite">{COLS.map(([id, n], i) => <SortTh key={id} id={id} name={n} sort={sort} onSort={setSort} right={i > 0} />)}</tr></thead>
            <tbody>
              {sorted(rows, sort).map((c) => {
                const flag = (k, end) => (c[k] != null && c[k] === worstOf(k, end) ? "font-semibold text-loss" : "");
                return (
                  <motion.tr layout key={name(c.courier)} onClick={() => setPicked(c.courier)} className={`cursor-pointer border-b border-hair transition last:border-b-0 hover:bg-wash ${chosen.courier === c.courier ? "bg-wash" : ""}`}>
                    <td className="px-3 py-3.5 font-sans font-medium">{name(c.courier)}</td>
                    <td className="px-3 py-3.5 text-right">{count(c.shipments)}</td>
                    <td className={`px-3 py-3.5 text-right ${flag("rto_rate_pct", "high")}`}>{pct(c.rto_rate_pct)}</td>
                    <td className={`px-3 py-3.5 text-right ${flag("delivered_rate_pct", "low")}`}>{pct(c.delivered_rate_pct)}</td>
                    <td className={`px-3 py-3.5 text-right ${flag("on_time_pct", "low")}`}>{pct(c.on_time_pct)}</td>
                    <td className={`px-3 py-3.5 text-right ${flag("first_attempt_delivery_pct", "low")}`}>{pct(c.first_attempt_delivery_pct)}</td>
                    <td className={`px-3 py-3.5 text-right ${flag("avg_delivery_days", "high")}`}>{c.avg_delivery_days ?? DASH}</td>
                    <td className="px-3 py-3.5 text-right">{c.avg_days_order_to_pickup ?? DASH}</td>
                    <td className={`px-3 py-3.5 text-right ${flag("avg_billed_per_shipment_inr", "high")}`}>{inr(c.avg_billed_per_shipment_inr)}</td>
                  </motion.tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </Panel>
    </>
  );
}
