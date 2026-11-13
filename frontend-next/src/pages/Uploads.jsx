import { AnimatePresence, motion } from "motion/react";
import { useEffect, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { PageHeader, Panel } from "../components/AppShell";
import { api } from "../lib/api";
import { uploadTypeFrom } from "../lib/features";
import { count } from "../lib/format";
import { useWorkspace } from "../lib/useWorkspace";

const TYPES = [
  ["orders", "Orders export", "Required", "One row per order: pincode, payment mode, value, customer."],
  ["shipments", "Shipment report", "Required", "AWB, courier, weight and delivery status. Upload orders first."],
  ["pincode_zones", "Pincode zones", "For the audit", "Which billing zone each pincode falls in."],
  ["rate_card", "Rate card", "For the audit", "Your agreed price per courier, zone and 500 g slab."],
  ["invoices", "Courier invoices", "For the audit", "What each courier billed, line by line."],
  ["remittances", "COD remittances", "For COD tracing", "The cash each courier paid back, per AWB."],
];
const NAMES = Object.fromEntries(TYPES.map((t) => [t[0], t[1]]));
const pretty = (s) => s.replace(/_inr$|_g$|_cm$|_ts$/, "").replaceAll("_", " ");
const RULES = {
  missing_required_value: "is empty", duplicate_in_file: "appears more than once", order_not_found: "is not in your uploaded orders",
  date_in_future: "is in the future", negative_amount: "is negative", no_customer_id_or_phone: "has no customer ID or phone",
  weight_not_positive: "is zero or negative", rate_not_positive: "is zero or negative", amount_not_positive: "is zero or negative",
};
const say = (e) => `${pretty(e.field)} ${RULES[e.rule] || e.rule.replaceAll("_", " ")}`;

function Steps({ at }) {
  return (
    <ol className="mb-6 flex flex-wrap gap-2 text-sm">
      {["Choose a file", "Match the columns", "Check the data", "Done"].map((s, i) => (
        <li key={s} className={`flex items-center gap-2 rounded-full border px-3.5 py-1.5 ${i === at ? "border-ink bg-ink font-medium text-white" : i < at ? "border-gain text-gain" : "border-rule text-graphite"}`}>
          <span className="font-mono text-xs">{i < at ? "✓" : i + 1}</span>{s}
        </li>
      ))}
    </ol>
  );
}

export default function Uploads() {
  // While choosing a file, the URL is the single source of truth for the dataset: ?type=shipments selects
  // the shipment report, an unknown or missing type selects orders, and picking a card rewrites ?type= in
  // place. Back, forward, reload and the sidebar link therefore always agree with what is selected.
  const [params, setParams] = useSearchParams();
  const urlKind = uploadTypeFrom(params.get("type"));
  const workspace = useWorkspace();
  const [kind, setKind] = useState(urlKind);
  const [batch, setBatch] = useState(null);       // the upload in progress, as the server last described it
  const [mapping, setMapping] = useState({});
  const [stage, setStage] = useState(0);          // 0 choose, 1 map, 2 check, 3 done
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [history, setHistory] = useState([]);
  const [historyError, setHistoryError] = useState("");
  const [over, setOver] = useState(false);
  const input = useRef(null);

  const loadHistory = () =>
    api("/api/ingestion/uploads/")
      .then((h) => { setHistory(Array.isArray(h) ? h : []); setHistoryError(""); })
      .catch((e) => setHistoryError(e.message));
  useEffect(() => { loadHistory(); }, []);
  // The URL changed (a link, back/forward): follow it, but never switch the dataset of an upload in progress.
  useEffect(() => { if (stage === 0) setKind(urlKind); }, [urlKind]); // eslint-disable-line react-hooks/exhaustive-deps
  const choose = (id) => {
    setKind(id);
    setParams((p) => { const next = new URLSearchParams(p); next.set("type", id); return next; }, { replace: true });
  };

  // Every step goes through run(): the error is shown and busy is cleared whether the step succeeds or fails.
  const run = async (work) => {
    setBusy(true);
    setError("");
    try { await work(); } catch (e) { setError(e?.message || "Something went wrong. Try again."); }
    setBusy(false);
  };
  const clearInput = () => { if (input.current) input.current.value = ""; };
  // Back to choosing: pick up whatever the URL says now (it may have changed during the upload).
  const reset = () => { setBatch(null); setStage(0); setError(""); setKind(urlKind); clearInput(); };

  // The file goes up as multipart FormData; api() leaves Content-Type to the browser so the boundary is set correctly.
  const send = (file) => file && !busy && run(async () => {
    try {
      const form = new FormData();
      form.append("dataset_type", kind);
      form.append("file", file);
      const b = await api("/api/ingestion/uploads/", { method: "POST", body: form });
      if (!b || !Array.isArray(b.required_fields) || !Array.isArray(b.columns_in_file) || !b.column_mapping) {
        throw new Error("The server sent an unexpected response. Try the upload again.");
      }
      setBatch(b);
      setMapping(b.column_mapping);
      setStage(1);
    } finally {
      clearInput(); // lets the same file be chosen again after a failure
    }
  });
  const validate = () => run(async () => {
    setBatch({ ...batch, ...(await api(`/api/ingestion/uploads/${batch.id}/validate/`, { method: "POST", body: { mapping } })) });
    setStage(2);
  });
  const commit = () => run(async () => {
    setBatch({ ...batch, ...(await api(`/api/ingestion/uploads/${batch.id}/commit/`, { method: "POST" })) });
    setStage(3);
    loadHistory();
    workspace.reload(); // new data may unlock features: refresh the counts the sidebar and dashboard read
  });

  const report = batch?.quality_report;
  const missing = batch ? (batch.required_fields || []).filter((f) => !mapping[f]) : [];

  return (
    <>
      <PageHeader title="Uploads" sub="Bring in your files. Nothing is saved until you have seen the check." />
      <div className="grid gap-4 xl:grid-cols-[1.6fr_1fr]">
        <Panel>
          <Steps at={stage} />
          {error && <p role="alert" className="mb-4 rounded-lg border border-loss px-4 py-3 text-sm text-loss">{error}</p>}
          <AnimatePresence mode="wait">
            <motion.div key={stage} initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }} transition={{ duration: 0.2 }}>
              {stage === 0 && (
                <>
                  <fieldset>
                    <legend className="mb-3 font-semibold">What is this file?</legend>
                    <div className="grid gap-2.5 sm:grid-cols-2">
                      {TYPES.map(([id, name, tag, text]) => (
                        <label key={id} className={`cursor-pointer rounded-xl border p-4 transition ${kind === id ? "border-brand bg-wash shadow-[0_0_0_3px_rgba(99,91,255,0.15)]" : "border-rule hover:border-ink"}`}>
                          <input type="radio" name="kind" value={id} checked={kind === id} onChange={() => choose(id)} className="sr-only" />
                          <span className="flex items-baseline justify-between gap-2"><span className="font-semibold">{name}</span><span className="font-mono text-[11px] uppercase tracking-wider text-graphite">{tag}</span></span>
                          <span className="mt-1 block text-sm text-graphite">{text}</span>
                        </label>
                      ))}
                    </div>
                  </fieldset>
                  <div onDragOver={(e) => { e.preventDefault(); setOver(true); }} onDragLeave={() => setOver(false)}
                    onDrop={(e) => { e.preventDefault(); setOver(false); send(e.dataTransfer.files[0]); }}
                    className={`mt-5 flex flex-col items-center gap-3 rounded-2xl border-2 border-dashed px-6 py-10 text-center transition ${over ? "border-brand bg-wash" : "border-rule"}`}>
                    <p className="font-semibold">Drop your {NAMES[kind].toLowerCase()} file here</p>
                    {/* Old .xls files need the xlrd library on the server, which is not installed yet. */}
                    <p className="text-sm text-graphite">CSV or Excel (.xlsx). Your own column names are fine.</p>
                    <input ref={input} id="file" type="file" accept=".csv,.xlsx" className="sr-only" onChange={(e) => send(e.target.files[0])} />
                    <label htmlFor="file" className={`btn cursor-pointer ${busy ? "pointer-events-none opacity-60" : ""}`}>{busy ? "Reading the file…" : "Choose a file"}</label>
                  </div>
                </>
              )}

              {stage === 1 && (
                <>
                  <p className="font-semibold">{batch.file} <span className="font-normal text-graphite">· {count(batch.rows)} rows</span></p>
                  <p className="mt-1 text-sm text-graphite">We matched your columns to ours. Fix any that look wrong.</p>
                  <div className="mt-4 overflow-x-auto rounded-xl border border-rule">
                    <table className="w-full min-w-[520px] text-sm">
                      <thead><tr className="bg-wash text-left text-graphite"><th className="px-4 py-2.5 font-medium">We need</th><th className="px-4 py-2.5 font-medium">Your column</th><th className="px-4 py-2.5 font-medium">First row</th></tr></thead>
                      <tbody>
                        {Object.keys(mapping).map((f) => {
                          const need = batch.required_fields.includes(f);
                          return (
                            <tr key={f} className="border-t border-hair">
                              <td className="px-4 py-2.5 capitalize">{pretty(f)} {need && <span className="ml-1 font-mono text-[11px] uppercase text-brand-deep">required</span>}</td>
                              <td className="px-4 py-2">
                                <label className="sr-only" htmlFor={`map-${f}`}>Column for {pretty(f)}</label>
                                <select id={`map-${f}`} value={mapping[f] || ""} onChange={(e) => setMapping({ ...mapping, [f]: e.target.value || null })}
                                  className={`h-10 w-full rounded-lg border bg-sheet px-2.5 ${need && !mapping[f] ? "border-loss" : "border-rule"}`}>
                                  <option value="">Not in this file</option>
                                  {batch.columns_in_file.map((c) => <option key={c} value={c}>{c}</option>)}
                                </select>
                              </td>
                              <td className="max-w-[180px] truncate px-4 py-2.5 text-graphite">{mapping[f] ? String(batch.preview?.[0]?.[mapping[f]] ?? "") : ""}</td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  </div>
                  {missing.length > 0 && <p className="mt-3 text-sm text-loss">Still needed: {missing.map(pretty).join(", ")}.</p>}
                  <div className="mt-5 flex flex-wrap gap-3">
                    <button type="button" className="btn disabled:opacity-60" disabled={busy || missing.length > 0} onClick={validate}>{busy ? "Checking…" : "Check the data"}</button>
                    <button type="button" className="btn-quiet" onClick={reset}>Start over</button>
                  </div>
                </>
              )}

              {stage === 2 && report && (
                <>
                  <div className="grid grid-cols-3 gap-3 text-center">
                    {[["rows in the file", report.total_rows, ""], ["ready to load", report.valid_rows, "text-gain"], ["rejected", report.rejected_rows, report.rejected_rows ? "text-loss" : ""]].map(([l, v, c]) => (
                      <div key={l} className="rounded-xl bg-wash px-2 py-4"><p className={`figure text-3xl ${c}`}>{count(v)}</p><p className="mt-1 text-xs text-graphite">{l}</p></div>
                    ))}
                  </div>
                  {[["Rejected rows", report.errors, "text-loss"], ["Kept, with a note", report.warnings, "text-caution"]].map(([title, list, colour]) => list.length > 0 && (
                    <div key={title} className="mt-5">
                      <h3 className="font-semibold">{title}</h3>
                      <ul className="mt-2 divide-y divide-hair rounded-xl border border-rule text-sm">
                        {list.map((e, i) => (
                          <li key={i} className="flex flex-wrap items-baseline justify-between gap-2 px-4 py-2.5">
                            <span className="capitalize">{say(e)}</span>
                            <span className="text-graphite"><span className={`num font-semibold ${colour}`}>{count(e.count)}</span> rows · e.g. row {e.sample_rows.slice(0, 3).join(", ")}</span>
                          </li>
                        ))}
                      </ul>
                    </div>
                  ))}
                  {!report.errors.length && !report.warnings.length && <p className="mt-5 rounded-lg bg-gain/10 px-4 py-3 text-sm text-gain">Every row passed.</p>}
                  <div className="mt-5 flex flex-wrap gap-3">
                    <button type="button" className="btn disabled:opacity-60" disabled={busy || !report.valid_rows} onClick={commit}>{busy ? "Loading…" : `Load ${count(report.valid_rows)} rows`}</button>
                    <button type="button" className="btn-quiet" onClick={() => setStage(1)}>Back to columns</button>
                    <button type="button" className="btn-quiet" onClick={reset}>Cancel</button>
                  </div>
                </>
              )}

              {stage === 3 && (
                <div className="py-4 text-center">
                  <motion.div initial={{ scale: 0 }} animate={{ scale: 1 }} transition={{ type: "spring", stiffness: 260, damping: 16 }} className="mx-auto flex h-16 w-16 items-center justify-center rounded-2xl bg-gain-fill text-3xl text-white">✓</motion.div>
                  <p className="display mt-4 text-2xl">{NAMES[batch.dataset_type]} loaded</p>
                  <p className="mt-1 text-graphite">{count(batch.load_result?.created)} new rows, {count(batch.load_result?.updated ?? batch.load_result?.skipped_already_loaded ?? 0)} already known.</p>
                  {batch.ledger && <p className="mt-1 text-sm text-graphite">Your ledger now holds {count(batch.ledger.rows)} parcels{batch.audit ? ` and the audit found ${count(batch.audit.findings)} charges to dispute` : ""}.</p>}
                  <button type="button" className="btn mt-5" onClick={reset}>Upload another file</button>
                </div>
              )}
            </motion.div>
          </AnimatePresence>
        </Panel>

        <Panel title="Upload history">
          {historyError ? (
            <div role="alert" className="text-sm text-loss">
              <p>Couldn't load your upload history. {historyError}</p>
              <button type="button" onClick={loadHistory} className="btn-quiet mt-3 px-4 py-2 text-sm text-ink">Try again</button>
            </div>
          ) : history.length === 0 ? <p className="text-sm text-graphite">Nothing uploaded yet. Start with your orders export.</p> : (
            <ul className="flex flex-col">
              {history.slice(0, 12).map((h) => (
                <li key={h.id} className="flex items-baseline justify-between gap-3 border-t border-hair py-3 text-sm first:border-t-0 first:pt-0">
                  <div className="min-w-0"><p className="truncate font-medium">{h.file}</p><p className="text-graphite">{NAMES[h.dataset_type] || h.dataset_type}</p></div>
                  <span className={`shrink-0 rounded-full px-2.5 py-1 text-xs font-medium ${h.status === "loaded" ? "bg-gain/10 text-gain" : h.status === "failed" ? "bg-loss/10 text-loss" : "bg-wash text-graphite"}`}>
                    {h.status === "loaded" ? `${count(h.quality_report?.valid_rows)} rows` : h.status}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </Panel>
      </div>
    </>
  );
}
