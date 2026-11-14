import { AnimatePresence, motion } from "motion/react";
import { useState } from "react";
import { PageHeader, Panel } from "../components/AppShell";
import { BarList, FactorBars, Ring } from "../components/charts";
import { StatusPill } from "../components/FeatureAvailability";
import { CountUp } from "../components/motion";
import { BandPill, FactorLegend, Loading, SectionError } from "../components/parts";
import ThresholdSlider from "../components/ThresholdSlider";
import { api } from "../lib/api";
import { riskMode } from "../lib/features";
import { count, day, pct } from "../lib/format";
import { useApi } from "../lib/useApi";
import { useWorkspace } from "../lib/useWorkspace";

const EMPTY = { order_value: "", payment_mode: "COD", pincode: "", address: "", customer_id: "", phone: "", sales_channel: "" };
const TONE = { Low: "gain", Medium: "brand", High: "loss", "Very high": "loss" };
const list = (v) => (Array.isArray(v) ? v : []);

// The API names a factor and its value; a few values read better with a word after them.
function factorRows(factors) {
  const top = Math.max(...factors.map((f) => Number(f.strength) || 0), 0) || 1;
  return factors.map((f) => ({
    label: f.factor === "Address parts" ? "Address detail" : f.factor,
    value: f.factor === "Address parts" ? `${f.value} ${f.value === "1" ? "part" : "parts"}` : f.value,
    effect: f.effect,
    size: Math.max(6, Math.round((100 * (Number(f.strength) || 0)) / top)),
  }));
}

function Field({ id, label, hint, error, children }) {
  return (
    <div>
      <label htmlFor={id} className="mb-1.5 block text-sm font-medium">{label}{hint && <span className="ml-1.5 font-normal text-graphite">{hint}</span>}</label>
      {children}
      {error && <p className="mt-1 text-[13px] text-loss">{error}</p>}
    </div>
  );
}

// How orders are scored right now, and the button that trains or retrains the model.
function ModelNote({ mode, onTrained }) {
  const [busy, setBusy] = useState(false);
  const [said, setSaid] = useState(null);    // { ok, text }
  const train = async () => {
    setBusy(true);
    setSaid(null);
    try {
      const run = await api("/api/ml/train/", { method: "POST" });
      setSaid(run.status === "trained"
        ? { ok: true, text: `Model trained on ${count(run.rows)} parcels with a known outcome.` }
        : { ok: false, text: run.reason || "There is not enough history to train a model yet." });
      onTrained();
    } catch (e) {
      setSaid({ ok: false, text: e.message });
    }
    setBusy(false);
  };
  return (
    <Panel className="mb-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="min-w-0 flex-1">
          <p className="flex flex-wrap items-center gap-2.5"><span className="font-semibold">{mode.headline}</span><StatusPill status="available">{mode.usesRules ? "Rules" : "Trained model"}</StatusPill></p>
          {mode.explanation && <p className="mt-1.5 text-sm text-graphite">{mode.explanation}</p>}
          {mode.usesRules && <p className="mt-1.5 text-sm text-graphite">Rule-based scores come from fixed rules. They are not predictions from a trained model.</p>}
          {mode.trainedAt && <p className="mt-1.5 text-sm text-graphite">Last trained {day(mode.trainedAt)}.</p>}
        </div>
        <button type="button" onClick={train} disabled={busy} className={`${mode.usesRules ? "btn" : "btn-quiet"} py-2.5 text-sm disabled:opacity-60`}>
          {busy ? "Training…" : mode.usesRules ? "Train the model" : "Retrain"}
        </button>
      </div>
      {said && <p role="status" className={`mt-3 rounded-lg px-3.5 py-2.5 text-sm ${said.ok ? "bg-gain/10 text-gain" : "bg-wash text-ink"}`}>{said.text}</p>}
    </Panel>
  );
}

function Result({ r }) {
  const tone = TONE[r.risk_category] || "brand";
  const factors = factorRows(list(r.contributing_factors));
  const c = r.customer || {}, d = r.destination || {}, conf = r.confidence || {};
  return (
    <motion.div key={r.key} initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.35 }}>
      <div className="flex flex-wrap items-center gap-5">
        <Ring value={r.risk_pct} size={132} tone={tone}>
          <CountUp key={r.key} value={r.risk_pct} format={(n) => pct(n)} duration={0.9} className={`figure text-2xl ${tone === "loss" ? "text-loss" : tone === "gain" ? "text-gain" : ""}`} />
        </Ring>
        <div className="min-w-0 flex-1">
          <p className="text-[13px] text-graphite">Chance this order comes back</p>
          <p className="mt-1 flex flex-wrap items-center gap-2"><BandPill band={r.risk_category} /><span className="text-sm text-graphite">Confidence: {conf.level}</span></p>
          <p className="mt-2 font-medium">{r.recommended_action}</p>
          {r.policy_note && <p className="mt-1.5 text-sm text-caution">{r.policy_note}</p>}
        </div>
      </div>

      <h3 className="mt-6 font-semibold">Why this score</h3>
      {factors.length ? <><div className="mt-2"><FactorBars factors={factors} /></div><FactorLegend /></>
        : <p className="mt-2 text-sm text-graphite">Nothing about this order stands out. It looks like an ordinary order for this store.</p>}

      <div className="mt-6 grid gap-3 sm:grid-cols-2">
        <div className="rounded-xl bg-wash px-4 py-3.5 text-sm">
          <p className="font-semibold">Customer</p>
          <p className="mt-1 text-graphite">{c.known
            ? `${count(c.previous_orders)} earlier orders: ${count(c.delivered)} delivered, ${count(c.returned)} returned.`
            : "Not seen before. Add a customer ID or phone number to use their history."}</p>
        </div>
        <div className="rounded-xl bg-wash px-4 py-3.5 text-sm">
          <p className="font-semibold">Destination</p>
          <p className="mt-1 text-graphite">{[d.pincode, d.city, d.zone ? `Zone ${d.zone}` : null].filter(Boolean).join(" · ")}</p>
          <p className="text-graphite">{d.parcels_sent_before ? `${count(d.parcels_sent_before)} parcels sent here before, ${pct(d.past_rto_rate_pct)} came back.` : "No parcels sent to this pincode before."}</p>
        </div>
      </div>
      <p className="mt-4 text-xs text-graphite">
        {String(r.scored_by).startsWith("model") ? "Scored by your trained model." : "Scored by rules, not by a trained model."}{" "}
        Confidence is {String(conf.level).toLowerCase()} because the store has sent {count(conf.pincode_parcels_seen)} parcels to this pincode and has {count(conf.customer_orders_seen)} earlier orders from this customer.
      </p>
    </motion.div>
  );
}

// What the trained model was tested on, and what a COD cut-off would have done. Only shown for a ready model.
function ModelCheck() {
  const [applied, setApplied] = useState({ margin: 30, keep: 60 });
  const [draft, setDraft] = useState(applied);
  const model = useApi({ m: "/api/ml/model/" });
  const eco = useApi({ e: `/api/ml/economics/?margin_pct=${applied.margin}&keep_rate=${applied.keep / 100}` });
  const m = model.data?.m, e = eco.data?.e;
  const rows = list(e?.table).map((t) => ({ threshold: Math.round(100 * t.threshold), flagged: t.orders_flagged, caught: t.rto_caught, good: t.good_orders_flagged, net: t.net_inr }));
  const test = m?.split?.test;
  const valid = (v, lo, hi) => Number.isFinite(Number(v)) && Number(v) >= lo && Number(v) <= hi;
  const ok = valid(draft.margin, 0, 100) && valid(draft.keep, 0, 100);
  return (
    <>
      <div className="pb-4 pt-12"><p className="eyebrow">Your model</p><h2 className="display mt-1.5 text-2xl sm:text-3xl">How far to trust it</h2></div>
      <div className="grid gap-4 xl:grid-cols-2">
        <Panel title="Tested on orders it had never seen" note={test ? `${count(test.rows)} parcels, ${day(test.from)} to ${day(test.to)}` : null}>
          {model.error ? <SectionError message={model.error} onRetry={model.reload} /> : model.loading ? <Loading /> : (
            <>
              <div className="grid grid-cols-2 gap-3">
                <div className="rounded-xl bg-wash px-4 py-3.5"><p className="figure text-3xl">{pct(m.top_10pct_of_orders_hold_pct_of_rto)}</p><p className="mt-1 text-xs text-graphite">of all returns sat in the riskiest 10% of orders</p></div>
                <div className="rounded-xl bg-wash px-4 py-3.5"><p className="figure text-3xl">{pct(100 * (m.test_after_calibration?.auc ?? NaN), 0)}</p><p className="mt-1 text-xs text-graphite">of the time, a returned order was scored above a delivered one</p></div>
              </div>
              <h3 className="mt-6 text-sm font-semibold">Does a score mean what it says?</h3>
              <p className="text-[13px] text-graphite">For each score band: what the model predicted, against how many really came back.</p>
              <div className="-mx-2 mt-2 overflow-x-auto">
                <table className="num w-full min-w-[420px] text-sm">
                  <thead><tr className="text-graphite">{["Score band", "Orders", "Predicted", "Came back"].map((h, i) => <th key={h} className={`border-b border-rule px-3 py-2 font-medium ${i ? "text-right" : "text-left"}`}>{h}</th>)}</tr></thead>
                  <tbody>
                    {list(m.bands).map((b) => (
                      <tr key={b.score_band} className="border-b border-hair last:border-b-0">
                        <td className="px-3 py-2.5 font-sans">{b.score_band}</td>
                        <td className="px-3 py-2.5 text-right">{count(b.orders)}</td>
                        <td className="px-3 py-2.5 text-right">{pct(100 * b.avg_predicted)}</td>
                        <td className="px-3 py-2.5 text-right font-semibold">{pct(100 * b.actual_rto_rate)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          )}
        </Panel>
        <Panel title="What the model looks at" note="Share of the model's total weight">
          {model.error ? <SectionError message={model.error} onRetry={model.reload} /> : model.loading ? <Loading />
            : <BarList rows={list(m.top_features).slice(0, 8).map((f) => ({ id: f.feature, label: f.label === "Address parts" ? "Address detail" : f.label, value: f.share_pct }))} format={(v) => pct(v)} tone="brand" />}
        </Panel>
      </div>

      <Panel className="mt-4" title="Where to stop offering COD" note="Refusing COD to risky orders avoids returns, but some good customers walk away. This uses the same unseen orders as above.">
        <div className="grid gap-8 lg:grid-cols-[1fr_1.4fr]">
          <form className="flex flex-col gap-4" onSubmit={(ev) => { ev.preventDefault(); if (ok) setApplied({ margin: Number(draft.margin), keep: Number(draft.keep) }); }}>
            <Field id="margin" label="Your margin on an order" hint="percent">
              <input id="margin" className="field num" inputMode="decimal" value={draft.margin} onChange={(ev) => setDraft({ ...draft, margin: ev.target.value })} />
            </Field>
            <Field id="keep" label="Flagged buyers who agree to pay online" hint="percent">
              <input id="keep" className="field num" inputMode="decimal" value={draft.keep} onChange={(ev) => setDraft({ ...draft, keep: ev.target.value })} />
            </Field>
            {!ok && <p className="text-[13px] text-loss">Both must be numbers between 0 and 100.</p>}
            <button type="submit" disabled={!ok} className="btn-quiet self-start py-2.5 text-sm disabled:opacity-40">Recalculate</button>
            {e && <p className="text-[13px] text-graphite">A returned parcel costs this store {`₹${Math.round(e.assumptions?.rto_cost_inr ?? 0)}`} in courier charges on average. {count(e.cod_orders_in_test)} COD orders were tested and {count(e.cod_rto_in_test)} of them came back.</p>}
          </form>
          <div className="min-w-0">
            {eco.error ? <SectionError message={eco.error} onRetry={eco.reload} /> : eco.loading ? <Loading /> : !rows.length ? <p className="text-sm text-graphite">No COD orders in the test period to work this out from.</p>
              : <ThresholdSlider key={`${applied.margin}-${applied.keep}`} rows={rows} period="the test period" id="cod-cut" />}
          </div>
        </div>
      </Panel>
    </>
  );
}

export default function Risk() {
  const ws = useWorkspace();
  const mode = riskMode(ws.model);
  const [form, setForm] = useState(EMPTY);
  const [errors, setErrors] = useState({});
  const [busy, setBusy] = useState(false);
  const [history, setHistory] = useState([]);     // this visit only; nothing is stored
  const [shown, setShown] = useState(null);
  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value });

  const submit = async (e) => {
    e.preventDefault();
    setBusy(true);
    setErrors({});
    // Empty optional fields are left out, so the API applies its own defaults.
    const body = Object.fromEntries(Object.entries(form).filter(([, v]) => String(v).trim() !== ""));
    try {
      const r = await api("/api/risk/score/", { method: "POST", body });
      const entry = { ...r, key: Date.now(), summary: `₹${form.order_value} · ${form.payment_mode} · ${form.pincode}` };
      setHistory((h) => [entry, ...h].slice(0, 8));
      setShown(entry);
    } catch (err) {
      const d = err.data && typeof err.data === "object" && !Array.isArray(err.data) ? err.data : {};
      const flat = Object.fromEntries(Object.entries(d).map(([k, v]) => [k, Array.isArray(v) ? String(v[0]) : String(v)]));
      setErrors(Object.keys(flat).some((k) => k in EMPTY) ? flat : { form: err.message });
    }
    setBusy(false);
  };

  return (
    <>
      <PageHeader title="Order risk checker" sub="Check an order before it ships. Nothing you enter here is saved." />
      <ModelNote mode={mode} onTrained={ws.reload} />

      <div className="grid gap-4 xl:grid-cols-[1fr_1.25fr]">
        <Panel title="The order">
          <form onSubmit={submit} className="flex flex-col gap-4" noValidate>
            <div className="grid gap-4 sm:grid-cols-2">
              <Field id="order_value" label="Order value" hint="₹" error={errors.order_value}>
                <input id="order_value" className="field num" inputMode="decimal" required value={form.order_value} onChange={set("order_value")} />
              </Field>
              <Field id="pincode" label="Delivery pincode" error={errors.pincode}>
                <input id="pincode" className="field num" inputMode="numeric" maxLength={6} required value={form.pincode} onChange={set("pincode")} />
              </Field>
            </div>
            <div>
              <p className="mb-1.5 text-sm font-medium">Payment</p>
              <div className="flex gap-2" role="radiogroup" aria-label="Payment">
                {["COD", "Prepaid"].map((p) => (
                  <button key={p} type="button" role="radio" aria-checked={form.payment_mode === p} onClick={() => setForm({ ...form, payment_mode: p })} className={form.payment_mode === p ? "chip-on" : "chip"}>{p === "COD" ? "Cash on delivery" : "Prepaid"}</button>
                ))}
              </div>
              {errors.payment_mode && <p className="mt-1 text-[13px] text-loss">{errors.payment_mode}</p>}
            </div>
            <Field id="address" label="Delivery address" hint="optional, but it sharpens the score" error={errors.address}>
              <textarea id="address" rows={2} className="field h-auto py-2.5" value={form.address} onChange={set("address")} />
            </Field>
            <div className="grid gap-4 sm:grid-cols-2">
              <Field id="customer_id" label="Customer ID" hint="optional" error={errors.customer_id}>
                <input id="customer_id" className="field" value={form.customer_id} onChange={set("customer_id")} />
              </Field>
              <Field id="phone" label="Customer phone" hint="optional" error={errors.phone}>
                <input id="phone" className="field num" inputMode="tel" autoComplete="off" value={form.phone} onChange={set("phone")} />
              </Field>
            </div>
            <Field id="sales_channel" label="Sales channel" hint="optional" error={errors.sales_channel}>
              <select id="sales_channel" className="field" value={form.sales_channel} onChange={set("sales_channel")}>
                <option value="">Not sure</option>
                {["Website", "WhatsApp", "Instagram Shop"].map((c) => <option key={c}>{c}</option>)}
              </select>
            </Field>
            <p className="text-[13px] text-graphite">The phone number is only used to find this customer's history. It is never stored.</p>
            {errors.form && <p role="alert" className="rounded-lg border border-loss px-4 py-2.5 text-sm text-loss">{errors.form}</p>}
            <div className="flex flex-wrap gap-3">
              <button type="submit" disabled={busy} className="btn py-2.5 disabled:opacity-60">{busy ? "Checking…" : "Check this order"}</button>
              <button type="button" onClick={() => { setForm(EMPTY); setErrors({}); }} className="btn-quiet py-2.5">Clear</button>
            </div>
          </form>
        </Panel>

        <div className="flex min-w-0 flex-col gap-4">
          <Panel className="flex-1">
            <AnimatePresence mode="wait">
              {shown ? <Result r={shown} />
                : <motion.p key="empty" initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="py-10 text-center text-graphite">Fill in the order and press Check. The score, the reasons behind it and what to do next appear here.</motion.p>}
            </AnimatePresence>
          </Panel>
          {history.length > 1 && (
            <Panel title="Checked this visit" note="Click one to see it again">
              <div className="flex flex-col gap-1.5">
                {history.map((h) => (
                  <button key={h.key} type="button" onClick={() => setShown(h)} aria-pressed={shown?.key === h.key}
                    className={`flex items-center justify-between gap-3 rounded-lg px-3 py-2 text-left text-sm transition hover:bg-wash ${shown?.key === h.key ? "bg-wash" : ""}`}>
                    <span className="num min-w-0 truncate">{h.summary}</span>
                    <span className="flex shrink-0 items-center gap-2"><span className="num font-medium">{pct(h.risk_pct)}</span><BandPill band={h.risk_category} /></span>
                  </button>
                ))}
              </div>
            </Panel>
          )}
        </div>
      </div>

      {mode.state === "ready" && <ModelCheck />}
    </>
  );
}
