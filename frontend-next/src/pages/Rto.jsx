import { useState } from "react";
import { PageHeader, Panel } from "../components/AppShell";
import { BarList, LineChart } from "../components/charts";
import { Chips, Loading, Pager, SectionError, SortTh, sorted, Stat } from "../components/parts";
import { count, DASH, inr, inrShort, pct } from "../lib/format";
import { useApi } from "../lib/useApi";

// [id the API takes, name on screen, needs a floor on parcels]
const CUTS = [["payment_mode", "Payment"], ["first_order", "First order"], ["zone", "Zone"], ["courier", "Courier"], ["sales_channel", "Channel"], ["city_tier", "City tier"],
  ["order_hour", "Hour of day"], ["state", "State", true], ["city", "City", true], ["pincode", "Pincode", true]];
const FLOORS = [[30, "30 parcels or more"], [100, "100 parcels or more"], [1, "Every one"]];
const MEASURES = [["rto_rate_pct", "Return rate", (v) => pct(v)], ["rto", "Parcels returned", count], ["rto_courier_cost_inr", "Courier charges on returns", inr]];
const SERIES = [["rto_rate_pct", "Return rate", (v) => pct(v), "brand"], ["rto", "Parcels returned", (v) => count(v), "ink"], ["rto_courier_cost_inr", "Courier charges on returns", (v) => inrShort(v), "loss"]];
const COLS = [["label", "Group"], ["shipments", "Parcels"], ["rto", "Returned"], ["rto_rate_pct", "Return rate"], ["cod_share_pct", "COD share"], ["rto_courier_cost_inr", "Courier charges on returns"]];
const PAGE = 15;
const list = (v) => (Array.isArray(v) ? v : []);
const monthName = (m) => (/^\d{4}-\d{2}$/.test(m || "") ? new Date(m + "-01").toLocaleString("en-IN", { month: "short", year: "2-digit" }) : DASH);

function labelFor(by, v) {
  if (by === "first_order") return v ? "First order" : "Repeat order";
  if (by === "order_hour") return v == null ? "Not recorded" : `${String(v).padStart(2, "0")}:00`;
  if (by === "zone") return v ? `Zone ${v}` : "No zone on file";
  if (by === "city_tier") return v ? `Tier ${v}` : "Not recorded";
  if (by === "payment_mode") return v === "COD" ? "Cash on delivery" : String(v || "Not recorded");
  return String(v || "Not recorded");
}

// Pick a way to cut the returns, a measure and a floor; the chart and the table follow.
function Explorer() {
  const [by, setBy] = useState("payment_mode");
  const [floor, setFloor] = useState(30);
  const [measure, setMeasure] = useState("rto_rate_pct");
  const [sort, setSort] = useState({ key: "rto_rate_pct", dir: -1 });
  const [offset, setOffset] = useState(0);
  const floored = Boolean(CUTS.find((c) => c[0] === by)?.[2]);
  const { data, error, loading, reload } = useApi({ rows: `/api/metrics/rto/?by=${by}${floored ? `&min_shipments=${floor}` : ""}` });
  // Right after the grouping changes, `data` still holds the previous grouping's rows for a moment.
  // They are only drawn once they carry the field for the grouping now selected.
  const mine = Array.isArray(data?.rows) && (!data.rows.length || by in data.rows[0]);
  const ok = !loading && mine;
  const rows = (ok ? data.rows : []).map((r) => ({ ...r, id: String(r[by]), label: labelFor(by, r[by]) }));
  const [key, name, format] = MEASURES.find((m) => m[0] === measure);
  const top = sorted(rows, { key, dir: -1 }).slice(0, 10);
  const table = sorted(rows, sort);
  const lead = top[0];
  const change = (fn) => (v) => { fn(v); setOffset(0); };

  return (
    <Panel title="Who sends parcels back?" note="Choose how to group your parcels">
      <Chips options={CUTS.map(([id, n]) => [id, n])} value={by} onChange={change(setBy)} label="Group parcels by" />
      <div className="mt-3 flex flex-wrap items-center gap-x-6 gap-y-3">
        <Chips options={MEASURES.map(([id, n]) => [id, n])} value={measure} onChange={(m) => { setMeasure(m); setSort({ key: m, dir: -1 }); setOffset(0); }} label="Measure" />
        {floored && (
          <label className="flex items-center gap-2 text-sm text-graphite">Only groups with
            <select className="field h-9 w-auto py-0 text-sm" value={floor} onChange={(e) => change(setFloor)(Number(e.target.value))}>{FLOORS.map(([n, text]) => <option key={n} value={n}>{text}</option>)}</select>
          </label>
        )}
      </div>

      <div className="mt-5 min-h-[260px]">
        {error ? <SectionError message={error} onRetry={reload} />
          : loading || (data && Array.isArray(data.rows) && !mine) ? <Loading />
          : !ok ? <SectionError message="The server sent an unexpected response." onRetry={reload} />
          : !rows.length ? <p className="text-sm text-graphite">No group has that many parcels. Lower the floor to see more.</p>
          : (
            <>
              <BarList key={`${by}-${key}`} rows={top.map((r) => ({ id: r.id, label: r.label, value: r[key] ?? 0, note: `${count(r.shipments)} parcels · ${count(r.rto)} returned` }))} format={format} flagMax tone="brand" />
              {lead && <p className="mt-4 rounded-lg bg-wash px-3.5 py-2.5 text-sm"><span className="font-semibold">{lead.label}</span> is highest on {name.toLowerCase()}: <span className="num font-semibold">{format(lead[key])}</span>, from {count(lead.shipments)} parcels.{rows.length > 10 ? ` Showing the top 10 of ${count(rows.length)}.` : ""}</p>}
            </>
          )}
      </div>

      {ok && rows.length > 0 && (
        <>
          <h3 className="mt-7 font-semibold">All {count(rows.length)} groups</h3>
          <div className="-mx-2 mt-1 overflow-x-auto">
            <table className="num w-full min-w-[680px] text-sm">
              <thead><tr className="text-graphite">{COLS.map(([id, n], i) => <SortTh key={id} id={id} name={n} sort={sort} onSort={change(setSort)} right={i > 0} />)}</tr></thead>
              <tbody>
                {table.slice(offset, offset + PAGE).map((r) => (
                  <tr key={r.id} className="border-b border-hair last:border-b-0">
                    <td className="px-3 py-3 font-sans font-medium">{r.label}</td>
                    <td className="px-3 py-3 text-right">{count(r.shipments)}</td>
                    <td className="px-3 py-3 text-right">{count(r.rto)}</td>
                    <td className="px-3 py-3 text-right font-semibold">{pct(r.rto_rate_pct)}</td>
                    <td className="px-3 py-3 text-right">{pct(r.cod_share_pct)}</td>
                    <td className="px-3 py-3 text-right">{inr(r.rto_courier_cost_inr)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <Pager offset={offset} limit={PAGE} total={table.length} shown={table.slice(offset, offset + PAGE).length} onChange={setOffset} />
        </>
      )}
    </Panel>
  );
}

export default function Rto() {
  const { data, error, loading, reload } = useApi({ overview: "/api/metrics/overview/", monthly: "/api/metrics/monthly/", byMode: "/api/metrics/rto/?by=payment_mode" });
  const [series, setSeries] = useState("rto_rate_pct");
  if (loading && !data) return <><PageHeader title="RTO analytics" /><Loading text="Loading your returns…" /></>;
  if (error) return <><PageHeader title="RTO analytics" /><SectionError message={error} onRetry={reload} /></>;

  const o = data.overview ?? {};
  const months = list(data.monthly).filter((m) => m.shipments > 0);
  const mode = Object.fromEntries(list(data.byMode).map((m) => [m.payment_mode, m]));
  const [key, name, format, tone] = SERIES.find((s) => s[0] === series);
  const labels = months.length > 1 ? [...new Set([0, Math.floor((months.length - 1) / 2), months.length - 1])].map((i) => [i, monthName(months[i].month)]) : [];
  const first = months[0], last = months[months.length - 1];
  const perParcel = o.rto ? o.rto_courier_cost_inr / o.rto : null;

  return (
    <>
      <PageHeader title="RTO analytics" sub={months.length ? `${monthName(first.month)} to ${monthName(last.month)} · ${count(o.total_shipments)} parcels` : null} />

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <Stat label="Return rate" value={o.rto_rate_pct} format={(n) => pct(n)} note={`${count(o.rto)} of ${count(o.total_shipments)} parcels came back`} />
        <Stat label="Cash on delivery" value={mode.COD?.rto_rate_pct} format={(n) => pct(n)} note={`Prepaid: ${pct(mode.Prepaid?.rto_rate_pct)}`} tone="loss" delay={0.04} />
        <Stat label="Courier charges on returns" value={o.rto_courier_cost_inr} format={inr} note={perParcel == null ? null : `${inr(perParcel)} per returned parcel`} tone="loss" delay={0.08} />
        <Stat label="Value of orders that came back" value={o.rto_order_value_inr} format={inrShort} note="Sales you shipped and did not keep" delay={0.12} />
      </div>

      <div className="pb-4 pt-12"><p className="eyebrow">Trend</p><h2 className="display mt-1.5 text-2xl sm:text-3xl">Are returns getting better or worse?</h2></div>
      <Panel>
        <div className="mb-4"><Chips options={SERIES.map(([id, n]) => [id, n])} value={series} onChange={setSeries} label="Series to chart" /></div>
        {months.length > 1 ? (
          <>
            <LineChart key={key} values={months.map((m) => m[key] ?? 0)} names={months.map((m) => monthName(m.month))} labels={labels} format={format} tone={tone} height={300} describe={`${name} by month`} />
            {key === "rto_rate_pct" && first.rto_rate_pct != null && last.rto_rate_pct != null && (
              <p className="mt-3 rounded-lg bg-wash px-3.5 py-2.5 text-sm">The return rate was <span className="num font-semibold">{pct(first.rto_rate_pct)}</span> in {monthName(first.month)} and <span className="num font-semibold">{pct(last.rto_rate_pct)}</span> in {monthName(last.month)}.</p>
            )}
          </>
        ) : <p className="text-sm text-graphite">Not enough months of data to draw a trend yet.</p>}
      </Panel>

      <div className="pb-4 pt-12"><p className="eyebrow">Breakdown</p><h2 className="display mt-1.5 text-2xl sm:text-3xl">Where returns come from</h2></div>
      <Explorer />
    </>
  );
}
