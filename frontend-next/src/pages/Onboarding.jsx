import { Link } from "react-router-dom";
import { PageHeader } from "../components/AppShell";
import { StatusPill } from "../components/FeatureAvailability";
import { Reveal } from "../components/motion";
import { riskMode, stagesFor, uploadLink } from "../lib/features";

// Chips for each stage. Only one stage is "Next step" at a time; nothing here blocks anything.
const CHIP = {
  completed: ["Completed", "available"],
  next: ["Next step", "needs-data"],
  pending: ["Not started", "coming-soon"],
  optional: ["Optional", "coming-soon"],
};

function Chip({ state }) {
  const [label, status] = CHIP[state];
  return <StatusPill status={status}>{label}</StatusPill>;
}

function Item({ done, children }) {
  return (
    <li className="flex items-start gap-2.5 text-sm">
      <span aria-hidden="true" className={`mt-0.5 flex h-4 w-4 shrink-0 items-center justify-center rounded-full font-mono text-[10px] ${done ? "bg-gain-fill text-white" : "border border-rule"}`}>{done ? "✓" : ""}</span>
      <span className={done ? "text-ink" : "text-graphite"}>{children}{done && <span className="sr-only"> (done)</span>}</span>
    </li>
  );
}

function Stage({ step, title, state, text, children, delay }) {
  return (
    <Reveal delay={delay}>
      <section className={`card flex h-full flex-col p-5 sm:p-6 ${state === "next" ? "border-brand shadow-[0_0_0_3px_rgba(99,91,255,0.12)]" : ""}`}>
        <div className="flex flex-wrap items-center justify-between gap-2">
          <p className="eyebrow">Stage {step}</p>
          <Chip state={state} />
        </div>
        <h2 className="display mt-2 text-xl">{title}</h2>
        <p className="mt-1.5 text-sm text-graphite">{text}</p>
        <div className="mt-4 flex flex-1 flex-col gap-4">{children}</div>
      </section>
    </Reveal>
  );
}

export default function Onboarding({ counts, model }) {
  const s = stagesFor(counts);
  const mode = riskMode(model);
  return (
    <>
      <PageHeader title="Let's get your logistics under control."
        sub="Your workspace is ready. Import your orders to start seeing your deliveries and returns." />
      <p className="mb-5 text-sm text-graphite"><span className="num font-semibold text-ink">{s.coreDone} of {s.coreTotal}</span> core steps done</p>

      <div className="grid gap-4 lg:grid-cols-3">
        <Stage step="1" title="Get started" state={s.started} delay={0}
          text="Orders are the first and most important file. They unlock order volume, value and your customers.">
          <ul className="flex flex-col gap-2">
            <Item done={Number(counts?.orders) > 0}>Orders export</Item>
            <Item done={s.zones}>Pincode zones <span className="text-graphite">(optional)</span></Item>
          </ul>
          <div className="mt-auto flex flex-wrap gap-3">
            <Link to={uploadLink("orders")} className="btn py-2.5 text-sm">Import orders</Link>
            <Link to={uploadLink("pincode_zones")} className="btn-quiet py-2.5 text-sm">Add pincode zones</Link>
          </div>
        </Stage>

        <Stage step="2" title="Understand deliveries" state={s.deliveries} delay={0.06}
          text="Your shipment report shows which parcels were delivered and which came back. It unlocks RTO analytics and courier performance.">
          <ul className="flex flex-col gap-2">
            <Item done={Number(counts?.shipments_with_outcome) > 0}>Shipment report with delivery outcomes</Item>
          </ul>
          <div className="mt-auto"><Link to={uploadLink("shipments")} className="btn-quiet py-2.5 text-sm">Import shipments</Link></div>
        </Stage>

        <Stage step="3" title="Go deeper" state="optional" delay={0.12}
          text="Check what couriers billed, trace COD cash, and score new orders before you ship them.">
          <ul className="flex flex-col gap-2">
            <Item done={s.deeper.rateCard && s.deeper.invoices}>Rate card and courier invoices, for the billing audit</Item>
            <Item done={s.deeper.remittances}>COD remittances, for COD reconciliation</Item>
            <Item done={mode.state === "ready"}>Risk model: {mode.usesRules ? "orders are scored with rules until there is enough history" : "trained"}</Item>
          </ul>
          <div className="mt-auto flex flex-wrap gap-3">
            <Link to={uploadLink("rate_card")} className="btn-quiet py-2.5 text-sm">Rate card</Link>
            <Link to={uploadLink("invoices")} className="btn-quiet py-2.5 text-sm">Invoices</Link>
            <Link to={uploadLink("remittances")} className="btn-quiet py-2.5 text-sm">COD remittances</Link>
          </div>
        </Stage>
      </div>

      <section className="card mt-4 flex flex-wrap items-center justify-between gap-3 px-5 py-4">
        <p className="text-sm"><span className="font-semibold">Want to see a full workspace first?</span> <span className="text-graphite">Explore a sample store. Its figures stay in the demo and never mix with yours.</span></p>
        <Link to="/demo" className="btn-quiet py-2.5 text-sm">Open the demo</Link>
      </section>
    </>
  );
}
