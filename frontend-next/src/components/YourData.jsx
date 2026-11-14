import { AnimatePresence, motion } from "motion/react";
import { useState } from "react";
import { Panel } from "./AppShell";
import { api } from "../lib/api";
import { count } from "../lib/format";

// [kind, name, workspace count key, unit, what else goes with it]
export const DATA = [
  ["orders", "Orders", "orders", "orders",
    "Every order goes, with its items, its shipments and their tracking, and all your customers and products. Courier invoices and COD payments stay but lose their parcel. The trained risk model is switched off until you train it again."],
  ["shipments", "Shipments", "shipments", "shipments",
    "Orders and customers stay. Tracking goes with the shipments. Courier invoices and COD payments stay but can no longer be matched to a parcel. The trained risk model is switched off until you train it again."],
  ["invoices", "Courier invoices", "invoice_lines", "lines", "The billing audit loses these lines and the overcharges found in them."],
  ["remittances", "COD remittances", "remittances", "lines", "COD reconciliation no longer counts these payments as received."],
  ["rate_card", "Rate card", "rate_cards", "rows", "The billing audit pauses until a new one is uploaded."],
  ["pincode_zones", "Pincode zones", "pincode_zones", "pincodes", "Zones and city tiers disappear from the analysis."],
];

// What is in the workspace now, with a way to remove one kind of data or start again from nothing.
// Removing asks twice: once to open the confirm row, once to say yes. Starting over needs the word "remove" typed.
export default function YourData({ counts, onChanged }) {
  const [asking, setAsking] = useState(null);      // a kind, or "all"
  const [typed, setTyped] = useState("");
  const [busy, setBusy] = useState(false);
  const [said, setSaid] = useState(null);          // { ok, text }
  const held = DATA.filter(([, , key]) => counts?.[key] > 0);

  const remove = async (kinds) => {
    setBusy(true);
    setSaid(null);
    try {
      const r = await api("/api/ingestion/data/remove/", { method: "POST", body: { kinds, confirm: "remove" } });
      const gone = Object.values(r.removed || {}).reduce((a, b) => a + b, 0);
      setSaid({ ok: true, text: kinds === "all" ? "Everything was removed. Your workspace is empty again."
        : `Removed ${count(gone)} rows.${r.risk_model_switched_off ? " The risk model was switched off; train it again on the Risk checker page once new data is in." : ""}` });
      setAsking(null);
      setTyped("");
      onChanged();
    } catch (e) {
      setSaid({ ok: false, text: e.message });
    }
    setBusy(false);
  };

  return (
    <Panel title="Your data" note="What is in your workspace now">
      {!held.length ? <p className="text-sm text-graphite">Nothing loaded yet.</p> : (
        <ul className="flex flex-col">
          {held.map(([kind, name, key, unit, note]) => (
            <li key={kind} className="border-t border-hair py-3 text-sm first:border-t-0 first:pt-0">
              <div className="flex items-center justify-between gap-3">
                <p className="min-w-0"><span className="font-medium">{name}</span> <span className="num text-graphite">· {count(counts[key])} {unit}</span></p>
                <button type="button" onClick={() => setAsking(asking === kind ? null : kind)} aria-expanded={asking === kind}
                  className="shrink-0 rounded-lg px-2.5 py-1 text-[13px] font-medium text-graphite transition hover:bg-wash hover:text-ink">Remove</button>
              </div>
              <AnimatePresence>
                {asking === kind && (
                  <motion.div initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: "auto" }} exit={{ opacity: 0, height: 0 }} className="overflow-hidden">
                    <div className="mt-2 rounded-lg bg-wash px-3 py-2.5">
                      <p>Remove all {count(counts[key])} {unit}? {note}</p>
                      <p className="mt-1 text-graphite">The upload history for this kind of file goes too, and the ledger and billing audit are rebuilt from what is left. This cannot be undone.</p>
                      <div className="mt-2 flex gap-2">
                        <button type="button" disabled={busy} onClick={() => remove([kind])} className="rounded-lg bg-loss px-3 py-1.5 text-[13px] font-medium text-white disabled:opacity-60">{busy ? "Removing…" : "Yes, remove"}</button>
                        <button type="button" onClick={() => setAsking(null)} className="rounded-lg px-3 py-1.5 text-[13px] font-medium hover:bg-sheet">Keep it</button>
                      </div>
                    </div>
                  </motion.div>
                )}
              </AnimatePresence>
            </li>
          ))}
        </ul>
      )}

      {said && <p role="status" className={`mt-3 rounded-lg px-3.5 py-2.5 text-sm ${said.ok ? "bg-gain/10 text-gain" : "border border-loss text-loss"}`}>{said.text}</p>}

      {held.length > 0 && (
        <div className="mt-4 border-t border-rule pt-4">
          {asking !== "all" ? (
            <button type="button" onClick={() => setAsking("all")} className="text-sm font-medium text-loss underline underline-offset-4">Empty my workspace and start again</button>
          ) : (
            <form onSubmit={(e) => { e.preventDefault(); if (typed.trim().toLowerCase() === "remove") remove("all"); }} className="text-sm">
              <p>This removes every file, every row, the upload history and the trained risk model. Your login and account stay. It cannot be undone.</p>
              <label htmlFor="start-over" className="mt-2 block text-graphite">Type <span className="font-mono text-ink">remove</span> to confirm</label>
              <input id="start-over" className="field mt-1" autoComplete="off" value={typed} onChange={(e) => setTyped(e.target.value)} />
              <div className="mt-2 flex gap-2">
                <button type="submit" disabled={busy || typed.trim().toLowerCase() !== "remove"} className="rounded-lg bg-loss px-3 py-2 text-[13px] font-medium text-white disabled:opacity-40">{busy ? "Removing…" : "Remove everything"}</button>
                <button type="button" onClick={() => { setAsking(null); setTyped(""); }} className="rounded-lg px-3 py-2 text-[13px] font-medium hover:bg-wash">Cancel</button>
              </div>
            </form>
          )}
        </div>
      )}
    </Panel>
  );
}
