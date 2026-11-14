import { AnimatePresence, motion } from "motion/react";
import { Fragment, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { PageHeader, Panel } from "../components/AppShell";
import FeatureAvailability, { FeatureNotes } from "../components/FeatureAvailability";
import { Loading, Pager, SectionError, Stat } from "../components/parts";
import { api } from "../lib/api";
import { featuresFor } from "../lib/features";
import { count, inr, pct } from "../lib/format";
import { useApi } from "../lib/useApi";
import { useWorkspace } from "../lib/useWorkspace";

const LIMIT = 25;
const list = (v) => (Array.isArray(v) ? v : []);

// The claim file is a CSV behind the login, so it is fetched with the token and handed to the browser as a download.
async function downloadClaims() {
  const text = await api("/api/audit/disputes.csv");
  const url = URL.createObjectURL(new Blob(["﻿", typeof text === "string" ? text : ""], { type: "text/csv;charset=utf-8" }));
  const a = document.createElement("a");
  a.href = url;
  a.download = "logis_dispute_claims.csv";
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

// Delivered COD parcels per courier: what was collected for the merchant against what was paid over.
function CodTable() {
  const { data, error, loading, reload } = useApi({ cod: "/api/metrics/cod/" });
  const rows = list(data?.cod);
  return (
    <Panel title="COD cash, courier by courier" note="Delivered cash-on-delivery parcels only">
      {error ? <SectionError message={error} onRetry={reload} /> : loading && !data ? <Loading /> : !rows.length ? <p className="text-sm text-graphite">No delivered COD parcels yet.</p> : (
        <div className="-mx-2 overflow-x-auto">
          <table className="num w-full min-w-[680px] text-sm">
            <thead><tr className="text-graphite">{["Courier", "COD parcels delivered", "Collected for you", "Paid to you", "Missing", "Never paid", "Paid short"].map((h, i) => <th key={h} className={`border-b border-rule px-3 py-2.5 font-medium ${i ? "text-right" : "text-left"}`}>{h}</th>)}</tr></thead>
            <tbody>
              {rows.map((c) => (
                <tr key={c.courier} className="border-b border-hair last:border-b-0">
                  <td className="px-3 py-3 font-sans font-medium">{c.courier}</td>
                  <td className="px-3 py-3 text-right">{count(c.cod_delivered_shipments)}</td>
                  <td className="px-3 py-3 text-right">{inr(c.cod_due_inr)}</td>
                  <td className="px-3 py-3 text-right">{inr(c.cod_remitted_inr)}</td>
                  <td className={`px-3 py-3 text-right font-semibold ${c.gap_inr > 0 ? "text-loss" : ""}`}>{inr(c.gap_inr)}</td>
                  <td className="px-3 py-3 text-right">{count(c.not_remitted)}</td>
                  <td className="px-3 py-3 text-right">{count(c.short_paid)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Panel>
  );
}

// Remounted (by its key) after the audit is run again, so it always shows the newest findings.
function Findings({ summary }) {
  const [params, setParams] = useSearchParams();
  const couriers = list(summary.by_courier).map((c) => c.courier);
  const kinds = list(summary.by_kind);
  const courier = couriers.includes(params.get("courier")) ? params.get("courier") : "";
  const kind = kinds.some((k) => k.kind === params.get("kind")) ? params.get("kind") : "";
  const [offset, setOffset] = useState(0);
  const [open, setOpen] = useState(null);
  // The filters live in the address bar, so a link from the Couriers page lands on the right courier.
  const filter = (name, value) => {
    const next = new URLSearchParams(params);
    if (value) next.set(name, value); else next.delete(name);
    setParams(next, { replace: true });
    setOffset(0);
    setOpen(null);
  };

  const query = `?limit=${LIMIT}&offset=${offset}${kind ? `&kind=${encodeURIComponent(kind)}` : ""}${courier ? `&courier=${encodeURIComponent(courier)}` : ""}`;
  const { data, error, loading, reload } = useApi({ rows: `/api/audit/findings/${query}` });
  const rows = Array.isArray(data?.rows) ? data.rows : null;
  // The findings API returns a bare list, so the total for the current filters comes from the summary.
  const cells = list(summary.by_courier_kind).filter((c) => (!kind || c.kind === kind) && (!courier || c.courier === courier));
  const total = cells.reduce((n, c) => n + c.findings, 0), claim = cells.reduce((n, c) => n + c.claim_inr, 0);
  const countOf = (k) => list(summary.by_courier_kind).filter((c) => c.kind === k && (!courier || c.courier === courier)).reduce((n, c) => n + c.findings, 0);

  return (
    <Panel title="Every disputed charge" note="Largest claim first. Click a row for the invoice details.">
      <div className="flex flex-wrap gap-2" role="tablist" aria-label="Kind of charge">
        <button type="button" role="tab" aria-selected={!kind} onClick={() => filter("kind", "")} className={!kind ? "chip-on" : "chip"}>All kinds</button>
        {kinds.map((k) => (
          <button key={k.kind} type="button" role="tab" aria-selected={kind === k.kind} onClick={() => filter("kind", k.kind)} className={kind === k.kind ? "chip-on" : "chip"}>
            {k.label || k.kind} <span className="num opacity-70">{count(countOf(k.kind))}</span>
          </button>
        ))}
      </div>
      <div className="mt-3 flex flex-wrap items-center justify-between gap-3">
        <label className="flex items-center gap-2 text-sm text-graphite">Courier
          <select className="field h-10 w-auto py-0 text-sm text-ink" value={courier} onChange={(e) => filter("courier", e.target.value)}>
            <option value="">All couriers</option>
            {couriers.map((c) => <option key={c} value={c}>{c}</option>)}
          </select>
        </label>
        <p className="num text-sm"><span className="font-semibold">{count(total)}</span> charges, <span className="font-semibold text-gain">{inr(claim)}</span> to claim</p>
      </div>

      <div className="-mx-2 mt-4 overflow-x-auto">
        <table className="num w-full min-w-[820px] text-sm">
          <thead><tr className="text-left text-graphite">{["Courier", "AWB", "What is wrong", "Billed", "Should be", "Claim"].map((h, i) => <th key={h} className={`border-b border-rule px-3 py-2.5 font-medium ${i > 2 ? "text-right" : ""}`}>{h}</th>)}</tr></thead>
          <tbody>
            {(rows || []).map((f) => {
              const on = open === f.id;
              return (
                <Fragment key={f.id}>
                  <tr tabIndex={0} role="button" aria-expanded={on} onClick={() => setOpen(on ? null : f.id)}
                    onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); setOpen(on ? null : f.id); } }}
                    className={`cursor-pointer border-b border-hair outline-none transition hover:bg-wash focus-visible:bg-wash ${on ? "bg-wash" : ""}`}>
                    <td className="px-3 py-3 font-sans">{f.courier_name}</td>
                    <td className="px-3 py-3 font-mono text-xs">{f.awb_number}</td>
                    <td className="px-3 py-3 font-sans"><span className="font-medium">{f.label}</span><span className="block text-xs text-graphite">{f.detail}</span></td>
                    <td className="px-3 py-3 text-right">{inr(f.billed_inr)}</td>
                    <td className="px-3 py-3 text-right">{inr(f.expected_inr)}</td>
                    <td className="px-3 py-3 text-right font-semibold text-gain">{inr(f.claim_inr)}</td>
                  </tr>
                  <AnimatePresence>
                    {on && (
                      <motion.tr initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} className="border-b border-hair bg-wash">
                        <td colSpan="6" className="px-3 pb-4 pt-1 font-sans text-sm text-graphite">
                          {f.invoice_id || f.line_ref
                            ? <>Invoice <span className="font-mono text-xs text-ink">{f.invoice_id || "not given"}</span>, line <span className="font-mono text-xs text-ink">{f.line_ref || "not given"}</span>. </>
                            : "This is cash the courier collected, so there is no invoice line. "}
                          The courier {f.invoice_id || f.line_ref ? "billed" : "paid"} {inr(f.billed_inr)} where {inr(f.expected_inr)} was due, a difference of {inr(f.claim_inr)}.
                        </td>
                      </motion.tr>
                    )}
                  </AnimatePresence>
                </Fragment>
              );
            })}
            {loading && !rows && <tr><td colSpan="6" className="px-3 py-6 text-graphite" role="status">Loading…</td></tr>}
            {error && <SectionError message={error} onRetry={reload} colSpan="6" />}
            {!loading && !error && data && !rows && <SectionError message="The server sent an unexpected response." onRetry={reload} colSpan="6" />}
            {rows && !rows.length && <tr><td colSpan="6" className="px-3 py-6 text-graphite">No charges match these filters.</td></tr>}
          </tbody>
        </table>
      </div>
      {rows && <Pager offset={offset} limit={LIMIT} total={total} shown={rows.length} onChange={(o) => { setOffset(o); setOpen(null); }} />}
    </Panel>
  );
}

export default function Audit() {
  const ws = useWorkspace();
  const features = featuresFor(ws.counts, ws.model);
  const { data, error, loading, reload } = useApi({ summary: "/api/audit/summary/" });
  const [grace, setGrace] = useState("21");
  const [run, setRun] = useState({ busy: false, said: null, version: 0 });
  const [saving, setSaving] = useState(null);     // null | "busy" | error text

  const graceOk = /^\d{1,3}$/.test(grace.trim());
  const rerun = async (e) => {
    e.preventDefault();
    if (!graceOk) return;
    setRun((r) => ({ ...r, busy: true, said: null }));
    try {
      const r = await api(`/api/audit/run/?cod_grace_days=${Number(grace)}`, { method: "POST" });
      setRun((x) => ({ busy: false, version: x.version + 1, said: { ok: true, text: `Checked ${count(r.lines_checked)} invoice lines and ${count(r.cod_delivered_parcels)} delivered COD parcels. ${count(r.findings)} charges to dispute, worth ${inr(r.claim_total_inr)}.` } }));
      reload();
    } catch (err) {
      setRun((x) => ({ ...x, busy: false, said: { ok: false, text: err.message } }));
    }
  };
  const save = async () => {
    setSaving("busy");
    try { await downloadClaims(); setSaving(null); } catch (err) { setSaving(err.message); }
  };

  if (loading && !data) return <><PageHeader title="Billing audit" /><Loading text="Loading your audit…" /></>;
  if (error) return <><PageHeader title="Billing audit" /><SectionError message={error} onRetry={reload} /></>;
  const s = data.summary ?? {};

  return (
    <>
      <PageHeader title="Billing audit" sub={`${inr(s.total_courier_billed_inr)} billed by your couriers, checked line by line`}>
        <button type="button" onClick={save} disabled={saving === "busy" || !s.findings} className="btn py-2.5 text-sm disabled:opacity-50">{saving === "busy" ? "Preparing…" : "Download the claim file"}</button>
      </PageHeader>
      {saving && saving !== "busy" && <p role="alert" className="mb-4 rounded-lg border border-loss px-4 py-2.5 text-sm text-loss">Couldn't download the file. {saving}</p>}
      <FeatureNotes feature="audit" />

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <Stat label="Recoverable from couriers" value={s.total_recoverable_inr} format={inr} note={`${count(s.findings)} charges to dispute`} tone="gain" />
        <Stat label="Overcharged on invoices" value={s.billing_overcharge_inr} format={inr} note={`${count(s.billing_findings)} lines · ${pct(s.overcharge_pct_of_billed)} of everything billed`} delay={0.04} />
        <Stat label="COD cash not paid to you" value={s.cod_missing_inr} format={inr} note={`${count(s.cod_findings)} delivered parcels`} delay={0.08} />
        <Stat label="Biggest single courier" value={list(s.by_courier)[0]?.claim_inr ?? 0} format={inr} note={list(s.by_courier)[0]?.courier || "Nothing to claim"} delay={0.12} />
      </div>

      <div className="mt-4">{s.findings ? <Findings key={run.version} summary={s} /> : <Panel title="Nothing to dispute"><p className="text-sm text-graphite">Every invoice line and every COD payment checked out against your own data.</p></Panel>}</div>

      <div className="mt-4">{features.cod.status === "available" ? <CodTable key={run.version} /> : <FeatureAvailability {...features.cod} />}</div>

      <Panel className="mt-4" title="Run the audit again" note="The audit already runs after every upload. Run it by hand to change how long a courier gets to pay COD.">
        <form onSubmit={rerun} className="flex flex-wrap items-end gap-3">
          <div>
            <label htmlFor="grace" className="mb-1.5 block text-sm font-medium">Days a courier has to pay COD</label>
            <input id="grace" className="field num w-32" inputMode="numeric" value={grace} onChange={(e) => setGrace(e.target.value)} />
          </div>
          <button type="submit" disabled={run.busy || !graceOk} className="btn-quiet py-2.5 text-sm disabled:opacity-50">{run.busy ? "Checking every line…" : "Run the audit"}</button>
        </form>
        {!graceOk && <p className="mt-2 text-[13px] text-loss">Enter a whole number of days.</p>}
        {run.said && <p role="status" className={`mt-3 rounded-lg px-3.5 py-2.5 text-sm ${run.said.ok ? "bg-gain/10 text-gain" : "border border-loss text-loss"}`}>{run.said.text}</p>}
      </Panel>
    </>
  );
}
