import { AnimatePresence, motion } from "motion/react";
import { useEffect, useState } from "react";
import { PageHeader, Panel } from "../components/AppShell";
import { Loading, Pager, SectionError } from "../components/parts";
import { api } from "../lib/api";
import { count, day, inr, inrShort, pct } from "../lib/format";
import { useApi } from "../lib/useApi";

const LIMIT = 25;
const SORTS = [["orders", "Most orders"], ["value", "Highest delivered value"], ["returned", "Most parcels returned"], ["rto_rate", "Highest return rate"], ["recent", "Most recent order"]];
const SEGMENT_TONE = { "Repeat returner": "text-loss", "Returned first order": "text-loss", Loyal: "text-gain" };
// The API sends the shipment's final status as text; anything with "RTO" in it is a return.
const returned = (o) => /rto/i.test(o || "");
const outcomeTone = (o) => (returned(o) ? "text-loss" : o === "Delivered" ? "text-gain" : "text-graphite");
const list = (v) => (Array.isArray(v) ? v : []);

// One customer's full record, opened from the table or from a phone look-up.
function Profile({ p, onClose }) {
  const pay = p.payment_behaviour || {};
  return (
    <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }} transition={{ duration: 0.3 }}>
      <Panel>
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0">
            <h2 className="display text-2xl">{p.name || p.customer_id}</h2>
            <p className="mt-0.5 text-sm text-graphite">{[p.customer_id, p.pincode, p.last_order ? `last order ${day(p.last_order)}` : null].filter(Boolean).join(" · ")}</p>
          </div>
          <button type="button" onClick={onClose} className="btn-quiet px-4 py-2 text-sm">Close</button>
        </div>
        <div className="mt-4 rounded-xl bg-wash px-4 py-3.5 text-sm">
          <p><span className={`font-semibold ${SEGMENT_TONE[p.segment] || ""}`}>{p.segment}.</span> <span className="text-graphite">{p.segment_meaning}.</span></p>
          <p className="mt-1 font-medium">{p.advice}</p>
        </div>
        <div className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-4">
          {[["Orders", count(p.orders), `${count(p.cancelled_orders)} cancelled`], ["Parcels delivered", count(p.delivered), inr(p.delivered_value_inr)],
            ["Parcels returned", count(p.returned), inr(p.returned_value_inr)], ["Return rate", pct(p.rto_rate_pct), p.payment_preference]].map(([label, value, note]) => (
            <div key={label} className="rounded-xl border border-rule px-4 py-3"><p className="text-xs text-graphite">{label}</p><p className="figure mt-0.5 text-2xl">{value}</p><p className="text-xs text-graphite">{note}</p></div>
          ))}
        </div>
        <h3 className="mt-6 font-semibold">How they pay, and what comes back</h3>
        <div className="mt-2 grid gap-3 sm:grid-cols-2">
          {[["Cash on delivery", pay.COD], ["Prepaid", pay.Prepaid]].map(([name, m]) => (
            <div key={name} className="rounded-xl bg-wash px-4 py-3 text-sm">
              <p className="font-medium">{name}</p>
              <p className="num text-graphite">{m?.parcels ? `${count(m.parcels)} parcels, ${count(m.returned)} returned (${pct(m.rto_rate_pct)})` : "No parcels"}</p>
            </div>
          ))}
        </div>
        <h3 className="mt-6 font-semibold">Recent orders</h3>
        <div className="-mx-2 mt-1 overflow-x-auto">
          <table className="num w-full min-w-[560px] text-sm">
            <thead><tr className="text-left text-graphite">{["Date", "Order", "Value", "Paid by", "Outcome", "Courier"].map((h, i) => <th key={h} className={`border-b border-rule px-3 py-2 font-medium ${i === 2 ? "text-right" : ""}`}>{h}</th>)}</tr></thead>
            <tbody>
              {list(p.recent_orders).map((o) => (
                <tr key={o.order_id} className="border-b border-hair last:border-b-0">
                  <td className="px-3 py-2.5">{day(o.date)}</td>
                  <td className="px-3 py-2.5 font-mono text-xs">{o.order_id}</td>
                  <td className="px-3 py-2.5 text-right">{inr(o.order_value_inr)}</td>
                  <td className="px-3 py-2.5 font-sans">{o.payment_mode}</td>
                  <td className={`px-3 py-2.5 font-sans font-medium ${outcomeTone(o.outcome)}`}>{returned(o.outcome) ? "Returned" : o.outcome}{o.ndr_reason ? <span className="block text-xs font-normal text-graphite">{o.ndr_reason}</span> : null}</td>
                  <td className="px-3 py-2.5 font-sans text-graphite">{o.courier}</td>
                </tr>
              ))}
              {!list(p.recent_orders).length && <tr><td colSpan="6" className="px-3 py-5 text-graphite">No orders on record.</td></tr>}
            </tbody>
          </table>
        </div>
      </Panel>
    </motion.div>
  );
}

export default function Customers() {
  const [segment, setSegment] = useState("");
  const [sort, setSort] = useState("orders");
  const [typed, setTyped] = useState("");
  const [search, setSearch] = useState("");
  const [offset, setOffset] = useState(0);
  const [phone, setPhone] = useState("");
  const [open, setOpen] = useState({ status: "closed" });   // closed | loading | error | ready

  // The search box waits for a pause in typing before it asks the server.
  useEffect(() => {
    const t = setTimeout(() => { setSearch(typed.trim()); setOffset(0); }, 350);
    return () => clearTimeout(t);
  }, [typed]);

  const segments = useApi({ s: "/api/customers/segments/" });
  const query = `?limit=${LIMIT}&offset=${offset}&sort=${sort}${segment ? `&segment=${encodeURIComponent(segment)}` : ""}${search ? `&search=${encodeURIComponent(search)}` : ""}`;
  const page = useApi({ p: `/api/customers/${query}` });
  const rows = Array.isArray(page.data?.p?.results) ? page.data.p.results : null;
  const total = page.data?.p?.count ?? null;
  const segs = list(segments.data?.s);
  const everyone = segs.reduce((n, s) => n + s.customers, 0);

  const show = async (params) => {
    setOpen({ status: "loading" });
    try {
      setOpen({ status: "ready", profile: await api(`/api/customers/lookup/?${params}`) });
    } catch (e) {
      setOpen({ status: "error", message: e.status === 404 ? "No customer of yours matches that." : e.message });
    }
  };
  const pick = (next) => { setSegment(next); setOffset(0); };

  return (
    <>
      <PageHeader title="Customers" sub={segments.data ? `${count(everyone)} customers who have placed an order` : null} />

      {segments.error ? <SectionError message={segments.error} onRetry={segments.reload} /> : segments.loading ? <Loading /> : (
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
          {segs.map((s, i) => {
            const on = segment === s.segment;
            return (
              <motion.button key={s.segment} type="button" onClick={() => pick(on ? "" : s.segment)} aria-pressed={on}
                initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.35, delay: i * 0.04 }}
                className={`card px-5 py-4 text-left transition hover:-translate-y-0.5 hover:border-brand ${on ? "border-brand bg-wash shadow-[0_0_0_3px_rgba(99,91,255,0.15)]" : ""}`}>
                <p className="flex items-baseline justify-between gap-2"><span className={`font-semibold ${SEGMENT_TONE[s.segment] || ""}`}>{s.segment}</span><span className="figure text-2xl">{count(s.customers)}</span></p>
                <p className="mt-1 text-[13px] text-graphite">{s.meaning}</p>
                <p className="num mt-2 text-[13px]">{s.rto_rate_pct == null ? "No outcomes yet" : `${pct(s.rto_rate_pct)} returned · ${pct(s.revenue_share_pct)} of revenue (${inrShort(s.delivered_value_inr)})`}</p>
              </motion.button>
            );
          })}
        </div>
      )}

      <div className="mt-6" aria-live="polite">
        <AnimatePresence mode="wait">
          {open.status === "loading" && <Panel key="l"><Loading text="Opening the customer…" /></Panel>}
          {open.status === "error" && <Panel key="e"><p className="text-sm">{open.message}</p><button type="button" onClick={() => setOpen({ status: "closed" })} className="btn-quiet mt-3 px-4 py-2 text-sm">Close</button></Panel>}
          {open.status === "ready" && <Profile key={open.profile.customer_id} p={open.profile} onClose={() => setOpen({ status: "closed" })} />}
        </AnimatePresence>
      </div>

      <Panel className="mt-4" title={segment || "All customers"} note="Click a customer to open their record"
        action={segment ? <button type="button" onClick={() => pick("")} className="text-sm font-medium text-brand-deep underline underline-offset-4">Show all segments</button> : null}>
        <div className="mb-4 grid gap-3 lg:grid-cols-[1.4fr_1fr_1.2fr]">
          <div>
            <label htmlFor="search" className="sr-only">Search by name, customer ID or pincode</label>
            <input id="search" type="search" className="field" placeholder="Search by name, customer ID or pincode" value={typed} onChange={(e) => setTyped(e.target.value)} />
          </div>
          <div>
            <label htmlFor="sort" className="sr-only">Sort by</label>
            <select id="sort" className="field" value={sort} onChange={(e) => { setSort(e.target.value); setOffset(0); }}>{SORTS.map(([id, name]) => <option key={id} value={id}>{name}</option>)}</select>
          </div>
          <form className="flex gap-2" onSubmit={(e) => { e.preventDefault(); if (phone.trim()) show(`phone=${encodeURIComponent(phone.trim())}`); }}>
            <label htmlFor="phone" className="sr-only">Find a customer by phone number</label>
            <input id="phone" className="field num" inputMode="tel" autoComplete="off" placeholder="Find by phone number" value={phone} onChange={(e) => setPhone(e.target.value)} />
            <button type="submit" className="btn-quiet shrink-0 px-4 py-2 text-sm">Find</button>
          </form>
        </div>
        <div className="-mx-2 overflow-x-auto">
          <table className="num w-full min-w-[760px] text-sm">
            <thead><tr className="text-left text-graphite">{["Customer", "Segment", "Pays by", "Orders", "Returned", "Return rate", "Delivered value", "Last order"].map((h, i) => <th key={h} className={`border-b border-rule px-3 py-2.5 font-medium ${i > 2 ? "text-right" : ""}`}>{h}</th>)}</tr></thead>
            <tbody>
              {(rows || []).map((c) => (
                <tr key={c.customer_id} tabIndex={0} role="button" aria-label={`Open ${c.name || c.customer_id}`}
                  onClick={() => show(`customer_id=${encodeURIComponent(c.customer_id)}`)}
                  onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); show(`customer_id=${encodeURIComponent(c.customer_id)}`); } }}
                  className="cursor-pointer border-b border-hair outline-none transition last:border-b-0 hover:bg-wash focus-visible:bg-wash">
                  <td className="px-3 py-3 font-sans"><span className="font-medium">{c.name || c.customer_id}</span><span className="block text-xs text-graphite">{c.customer_id} · {c.pincode}</span></td>
                  <td className={`px-3 py-3 font-sans ${SEGMENT_TONE[c.segment] || ""}`}>{c.segment}</td>
                  <td className="px-3 py-3 font-sans">{c.payment_preference}</td>
                  <td className="px-3 py-3 text-right">{count(c.orders)}</td>
                  <td className={`px-3 py-3 text-right ${c.returned ? "font-semibold text-loss" : ""}`}>{count(c.returned)}</td>
                  <td className="px-3 py-3 text-right">{pct(c.rto_rate_pct)}</td>
                  <td className="px-3 py-3 text-right">{inr(c.delivered_value_inr)}</td>
                  <td className="px-3 py-3 text-right">{day(c.last_order)}</td>
                </tr>
              ))}
              {page.loading && <tr><td colSpan="8" className="px-3 py-6 text-graphite" role="status">Loading…</td></tr>}
              {page.error && <SectionError message={page.error} onRetry={page.reload} colSpan="8" />}
              {rows && !page.loading && !rows.length && <tr><td colSpan="8" className="px-3 py-6 text-graphite">No customers match.</td></tr>}
            </tbody>
          </table>
        </div>
        {rows && <Pager offset={offset} limit={LIMIT} total={total} shown={rows.length} onChange={setOffset} />}
        <p className="mt-4 text-xs text-graphite">Phone numbers are never stored or shown. A number you type is only used to find the matching customer.</p>
      </Panel>
    </>
  );
}
