import { AnimatePresence, motion, useReducedMotion, useScroll, useTransform } from "motion/react";
import { useRef, useState } from "react";
import { Link, Outlet } from "react-router-dom";
import { BarList, FactorBars, Heatmap, LineChart, Ring } from "../components/charts";
import Logo from "../components/Logo";
import { CountUp, EASE, Reveal } from "../components/motion";
import PixelField from "../components/PixelField";
import { SAMPLE } from "../data/sample";
import { count, inr, pct } from "../lib/format";

const wrap = "mx-auto w-full max-w-[1320px] px-5 sm:px-8 lg:px-12";
const h2 = "display text-3xl leading-[1.1] sm:text-4xl lg:text-5xl";
const BAND = { Low: "border border-rule text-graphite", Medium: "bg-caution-bg text-caution", High: "bg-caution-bg text-caution", "Very high": "bg-loss text-white" };

function Nav() {
  return (
    <header className="sticky top-0 z-30 border-b border-rule/70 bg-paper/85 backdrop-blur-md">
      <div className={`${wrap} flex flex-wrap items-center justify-between gap-x-6 gap-y-1 py-2.5`}>
        <Logo tagline />
        <nav className="order-3 flex w-full gap-6 overflow-x-auto whitespace-nowrap text-[15px] md:order-none md:w-auto md:gap-7">
          {[["#product", "Product"], ["#explore", "Explore the data"], ["#risk", "Risk checker"], ["#how", "How it works"]].map(([href, text]) => (
            <a key={href} href={href} className="py-2.5 text-graphite transition hover:text-ink">{text}</a>
          ))}
          <Link to="/demo" className="py-2.5 text-graphite transition hover:text-ink">Demo</Link>
        </nav>
        <div className="flex items-center gap-2">
          <Link to="/login" className="rounded-lg px-4 py-2.5 text-[15px] font-medium transition hover:bg-wash">Log in</Link>
          <Link to="/signup" className="btn px-5 py-2.5 text-[15px]">Sign up</Link>
        </div>
      </div>
    </header>
  );
}

function Hero() {
  const still = useReducedMotion();
  const rise = (delay) => ({ initial: still ? false : { opacity: 0, y: 22 }, animate: { opacity: 1, y: 0 }, transition: { duration: 0.6, delay, ease: EASE } });
  return (
    <section className="relative overflow-hidden">
      <PixelField />
      <div className={`${wrap} relative grid items-center gap-12 pb-16 pt-14 lg:grid-cols-[1.05fr_1fr] lg:gap-16 lg:pb-24 lg:pt-20`}>
        <div>
          <motion.p {...rise(0)} className="eyebrow">Billing audit · COD tracing · return risk</motion.p>
          <motion.h1 {...rise(0.08)} className="display mt-5 text-5xl leading-[1.02] sm:text-6xl xl:text-7xl">
            Find the money your couriers <span className="relative whitespace-nowrap text-brand">owe you
              <motion.span aria-hidden="true" className="absolute -bottom-1 left-0 h-[5px] w-full origin-left rounded-full bg-gold" initial={still ? false : { scaleX: 0 }} animate={{ scaleX: 1 }} transition={{ duration: 0.7, delay: 0.7, ease: EASE }} />
            </span>.
          </motion.h1>
          <motion.p {...rise(0.16)} className="mt-6 max-w-xl text-lg leading-relaxed text-graphite sm:text-xl">
            Upload your order, shipment and courier invoice files. logis checks every bill against your rate card, traces every rupee of COD cash, and tells you which new orders are likely to come back.
          </motion.p>
          <motion.div {...rise(0.24)} className="mt-9 flex flex-wrap gap-3">
            <Link to="/signup" className="btn px-6 py-3.5">Start with your files</Link>
            <a href="#explore" className="btn-quiet px-6 py-3.5">Explore sample data</a>
          </motion.div>
          <motion.p {...rise(0.32)} className="mt-5 text-sm text-graphite">Works with CSV and Excel exports. No integration needed to start.</motion.p>
        </div>

        <motion.div className="card p-6 shadow-[0_30px_60px_-30px_rgba(10,37,64,0.35)] sm:p-8" initial={still ? false : { opacity: 0, y: 30, rotate: 1.5 }} animate={{ opacity: 1, y: 0, rotate: 0 }}
          transition={{ duration: 0.8, delay: 0.25, ease: EASE }} whileHover={still ? undefined : { y: -4 }}>
          <div className="flex flex-wrap items-baseline justify-between gap-2 border-b border-rule pb-4">
            <span className="text-sm font-medium">Audit summary</span>
            <span className="font-mono text-xs text-graphite">sample seller · {count(SAMPLE.shipments)} shipments</span>
          </div>
          <p className="mt-5 text-sm text-graphite">Recoverable from couriers</p>
          <CountUp value={SAMPLE.recoverable} format={inr} duration={1.6} className="figure block text-5xl leading-tight text-gain sm:text-6xl" />
          <ul className="mt-4 text-[15px]">
            {SAMPLE.byKind.slice(0, 5).map((k, i) => (
              <motion.li key={k.label} className="flex justify-between gap-4 border-t border-hair py-2.5" initial={still ? false : { opacity: 0, x: 14 }} animate={{ opacity: 1, x: 0 }} transition={{ duration: 0.4, delay: 0.9 + i * 0.1, ease: EASE }}>
                <span>{k.label}</span><span className="num font-medium">{inr(k.value)}</span>
              </motion.li>
            ))}
          </ul>
        </motion.div>
      </div>
    </section>
  );
}

function Ticker() {
  const items = [...SAMPLE.facts, ...SAMPLE.facts];
  return (
    <div className="overflow-hidden bg-ink py-3.5 text-white" aria-label="Findings from the sample dataset">
      <div className="ticker flex w-max gap-10 whitespace-nowrap text-[15px]">
        {items.map((f, i) => <span key={i} aria-hidden={i >= SAMPLE.facts.length} className="flex items-center gap-10">{f}<span className="h-1.5 w-1.5 rounded-[2px] bg-gold" /></span>)}
      </div>
    </div>
  );
}

// Scroll through this section and the product window zooms from a thumbnail to full size,
// while the caption beside it changes. The section is tall; the content inside it stays pinned.
function Product() {
  const ref = useRef(null);
  const still = useReducedMotion();
  const { scrollYProgress: p } = useScroll({ target: ref, offset: ["start start", "end end"] });
  const scale = useTransform(p, [0, 0.55], [still ? 1 : 0.72, 1]);
  const radius = useTransform(p, [0, 0.55], [36, 16]);
  const tilt = useTransform(p, [0, 0.55], [still ? 0 : 7, 0]);
  const steps = [
    ["See the leak", "One screen for what couriers owe you, what returns cost you, and how both are moving."],
    ["See where it comes from", "Every total opens into the parcels behind it. Nothing is a number you have to take on trust."],
    ["Act on it", "Download a claim file per courier, and check new orders for risk before they leave."],
  ];
  const [o1, o2, o3] = [useTransform(p, [0, 0.25, 0.38], [1, 1, 0]), useTransform(p, [0.32, 0.45, 0.62, 0.72], [0, 1, 1, 0]), useTransform(p, [0.66, 0.8, 1], [0, 1, 1])];
  const fades = [o1, o2, o3];
  return (
    <section id="product" ref={ref} className="relative h-[260vh] scroll-mt-16 bg-wash">
      <div className="sticky top-0 flex h-screen flex-col justify-center overflow-hidden py-16">
        <div className={`${wrap} grid items-center gap-8 lg:grid-cols-[0.8fr_1.6fr]`}>
          <div className="relative h-44 sm:h-40 lg:h-64">
            <p className="eyebrow">The product</p>
            {steps.map(([head, text], i) => (
              <motion.div key={head} style={{ opacity: still ? (i === 0 ? 1 : 0) : fades[i] }} className="absolute inset-x-0 top-8">
                <h2 className="display text-3xl leading-tight sm:text-4xl lg:text-5xl">{head}</h2>
                <p className="mt-3 max-w-md text-graphite lg:text-lg">{text}</p>
              </motion.div>
            ))}
          </div>
          <motion.div style={{ scale, borderRadius: radius, rotateX: tilt, transformPerspective: 1400 }} className="min-w-0 origin-center overflow-hidden border border-rule bg-paper shadow-[0_40px_80px_-40px_rgba(10,37,64,0.5)]">
            <div className="flex items-center gap-1.5 border-b border-rule bg-sheet px-4 py-2.5">
              {["#e2e8f0", "#e2e8f0", "#e2e8f0"].map((c, i) => <span key={i} className="h-2.5 w-2.5 rounded-full" style={{ background: c }} />)}
              <span className="ml-3 font-mono text-xs text-graphite">logis / dashboard</span>
            </div>
            <div className="grid gap-3 p-4 sm:grid-cols-3 sm:p-5">
              {[["Recoverable", inr(229005), "text-gain"], ["Spent on returns", inr(1230968), "text-loss"], ["RTO rate", "17.9%", ""]].map(([l, v, c]) => (
                <div key={l} className="rounded-xl border border-rule bg-sheet px-4 py-3"><p className="text-xs text-graphite">{l}</p><p className={`figure text-2xl ${c}`}>{v}</p></div>
              ))}
              <div className="min-w-0 rounded-xl border border-rule bg-sheet p-4 sm:col-span-2">
                <p className="text-sm font-medium">RTO rate by month</p>
                <LineChart values={SAMPLE.monthlyRto} names={SAMPLE.monthNames} labels={SAMPLE.monthLabels} max={40} height={200} describe="Monthly RTO rate in the sample data" />
              </div>
              <div className="min-w-0 rounded-xl border border-rule bg-sheet p-4">
                <p className="mb-2 text-sm font-medium">Where the claim comes from</p>
                <BarList rows={SAMPLE.byKind.slice(0, 4).map((k) => ({ label: k.label, value: k.value }))} format={inr} tone="gain" />
              </div>
            </div>
          </motion.div>
        </div>
      </div>
    </section>
  );
}

// Pick a cut and the bars re-flow. Real figures from the sample.
function Explore() {
  const cuts = Object.keys(SAMPLE.cuts);
  const [cut, setCut] = useState(cuts[0]);
  return (
    <section id="explore" className={`${wrap} scroll-mt-20 py-16 lg:py-24`}>
      <Reveal>
        <p className="eyebrow">Explore the sample data</p>
        <h2 className={`${h2} mt-3 max-w-3xl`}>Two years of one seller's parcels. Poke at them.</h2>
        <p className="mt-4 max-w-2xl text-lg text-graphite">{count(SAMPLE.shipments)} shipments, three couriers, five delivery zones. These are sample figures, and your own will differ.</p>
      </Reveal>
      <div className="mt-10 grid gap-5 lg:grid-cols-2">
        <Reveal className="card p-6 sm:p-7">
          <h3 className="text-lg font-semibold">Who sends parcels back?</h3>
          <div className="mt-4 flex flex-wrap gap-2" role="tablist" aria-label="Cut the RTO rate by">
            {cuts.map((c) => <button key={c} type="button" role="tab" aria-selected={c === cut} onClick={() => setCut(c)} className={c === cut ? "chip-on" : "chip"}>{c}</button>)}
          </div>
          <div className="mt-5 min-h-[230px]"><BarList key={cut} rows={SAMPLE.cuts[cut]} format={(v) => pct(v)} flagMax tone="brand" /></div>
          <AnimatePresence mode="wait">
            <motion.p key={cut} initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }} transition={{ duration: 0.25 }} className="rounded-lg bg-wash px-3.5 py-2.5 text-sm">{SAMPLE.cutNotes[cut]}</motion.p>
          </AnimatePresence>
        </Reveal>
        <Reveal delay={0.08} className="card p-6 sm:p-7">
          <h3 className="text-lg font-semibold">Returns fell as customers came back</h3>
          <p className="mt-1 text-sm text-graphite">Monthly RTO rate. Move across the chart to read any month.</p>
          <div className="mt-6"><LineChart values={SAMPLE.monthlyRto} names={SAMPLE.monthNames} labels={SAMPLE.monthLabels} max={40} height={300}
            describe="Monthly RTO rate falling from 32.3 percent in January 2024 to 10.3 percent in December 2025" /></div>
        </Reveal>
        <Reveal className="card p-6 sm:p-7 lg:col-span-2">
          <div className="grid gap-8 lg:grid-cols-[0.7fr_1.3fr] lg:items-center">
            <div className="min-w-0">
              <h3 className="text-lg font-semibold">One courier was worst in every zone</h3>
              <p className="mt-2 text-graphite">RTO rate by courier and zone. Deeper colour means more parcels came back. Hover a cell to compare along its row and column.</p>
              <p className="mt-3 text-sm text-graphite">Comparing inside each zone removes the excuse that one courier simply got the harder routes.</p>
            </div>
            <Heatmap rows={SAMPLE.heat.map((h) => ({ label: h.courier, values: h.values }))} columns={SAMPLE.zones} columnLabel={(c) => `Zone ${c}`} format={(v) => pct(v)}
              describe="RTO rate by courier and zone. BlueRoute Couriers has the highest rate in all five zones." />
          </div>
        </Reveal>
      </div>
    </section>
  );
}

// Three real orders scored by the model. Switch between them and the score, reasons and advice change.
function Risk() {
  const [i, setI] = useState(0);
  const o = SAMPLE.orders[i];
  const tone = o.band === "Very high" ? "loss" : o.band === "Low" ? "gain" : "brand";
  return (
    <section id="risk" className="scroll-mt-16 border-y border-rule bg-wash">
      <div className={`${wrap} grid items-center gap-10 py-16 lg:grid-cols-[0.85fr_1.15fr] lg:gap-16 lg:py-24`}>
        <Reveal className="min-w-0">
          <p className="eyebrow">Order risk checker</p>
          <h2 className={`${h2} mt-3`}>Know before it ships</h2>
          <p className="mt-4 text-lg text-graphite">Three orders from the sample, scored by a model trained on that seller's own history. Pick one.</p>
          <div className="mt-6 flex flex-col gap-2.5" role="tablist" aria-label="Sample orders">
            {SAMPLE.orders.map((x, n) => (
              <button key={x.name} type="button" role="tab" aria-selected={n === i} onClick={() => setI(n)}
                className={`rounded-xl border px-4 py-3.5 text-left transition ${n === i ? "border-brand bg-sheet shadow-[0_0_0_3px_rgba(99,91,255,0.15)]" : "border-rule bg-sheet/60 hover:border-ink"}`}>
                <span className="block font-semibold">{x.name}</span>
                <span className="block text-sm text-graphite">{x.detail}</span>
              </button>
            ))}
          </div>
        </Reveal>
        <Reveal delay={0.1} className="card p-6 sm:p-8">
          <div className="flex flex-wrap items-center justify-between gap-5 border-b border-rule pb-6">
            <div className="flex items-center gap-5">
              <Ring value={o.risk} size={132} tone={tone}><CountUp key={o.name} value={o.risk} format={(n) => pct(n)} duration={0.9} className={`figure text-2xl ${tone === "loss" ? "text-loss" : tone === "gain" ? "text-gain" : ""}`} /></Ring>
              <div>
                <p className="text-sm text-graphite">Chance this order comes back</p>
                <span className={`mt-2 inline-block rounded-full px-3.5 py-1.5 text-sm font-medium ${BAND[o.band]}`}>{o.band} risk</span>
              </div>
            </div>
            <p className="text-sm text-graphite">Confidence <span className="font-semibold text-ink">{o.confidence}</span></p>
          </div>
          <AnimatePresence mode="wait">
            <motion.div key={o.name} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }} transition={{ duration: 0.25 }}>
              <div className="mt-5 rounded-xl bg-ink px-5 py-4 text-white">
                <p className="font-mono text-xs uppercase tracking-[0.14em] text-gold">Recommended action</p>
                <p className="mt-1.5 text-lg font-medium leading-snug">{o.action}</p>
              </div>
              <h3 className="mt-6 font-semibold">Why this score</h3>
              <FactorBars factors={o.factors} />
              <p className="mt-2 text-xs text-graphite">Bars compare this order with the seller's average order. Red raises the risk, teal lowers it.</p>
            </motion.div>
          </AnimatePresence>
        </Reveal>
      </div>
    </section>
  );
}

// Drag the slider: where would you stop offering COD? Real back-test numbers from the sample.
function Threshold() {
  const [n, setN] = useState(5);
  const [th, flagged, caught, good, net] = SAMPLE.thresholds[n];
  const best = SAMPLE.thresholds.reduce((a, t) => (t[4] > a[4] ? t : a));
  return (
    <section className={`${wrap} py-16 lg:py-24`}>
      <Reveal className="grid gap-10 lg:grid-cols-[1fr_1.1fr] lg:items-center lg:gap-16">
        <div className="min-w-0">
          <p className="eyebrow">The trade-off</p>
          <h2 className={`${h2} mt-3`}>Where would you draw the line?</h2>
          <p className="mt-4 text-lg text-graphite">Refuse COD to risky orders and you avoid returns, but some good customers walk away. Drag the slider to see what each cut-off would have done over ten weeks of the sample.</p>
          <p className="mt-4 text-sm text-graphite">Assumes a 30% margin and that 6 in 10 flagged buyers agree to pay online. In the product you set these yourself.</p>
        </div>
        <div className="card p-6 sm:p-8">
          <label htmlFor="cut" className="flex items-baseline justify-between gap-3">
            <span className="font-semibold">Refuse COD when the risk score is above</span>
            <span className="figure text-3xl text-brand">{th}%</span>
          </label>
          <input id="cut" type="range" min="0" max={SAMPLE.thresholds.length - 1} step="1" value={n} onChange={(e) => setN(+e.target.value)} className="mt-4 h-2 w-full cursor-pointer accent-brand" />
          <div className="mt-1 flex justify-between font-mono text-xs text-graphite"><span>10%</span><span>strict ← → relaxed</span><span>80%</span></div>
          <div className="mt-6 grid grid-cols-3 gap-3 text-center">
            {[["COD orders flagged", flagged, ""], ["returns avoided", caught, "text-gain"], ["good buyers flagged", good, "text-loss"]].map(([l, v, c]) => (
              <div key={l} className="rounded-xl bg-wash px-2 py-4"><motion.p key={v} initial={{ scale: 0.9, opacity: 0.4 }} animate={{ scale: 1, opacity: 1 }} className={`figure text-3xl ${c}`}>{count(v)}</motion.p><p className="mt-1 text-xs text-graphite">{l}</p></div>
            ))}
          </div>
          <div className={`mt-4 flex flex-wrap items-baseline justify-between gap-2 rounded-xl px-5 py-4 ${net >= 0 ? "bg-gain/10" : "bg-loss/10"}`}>
            <span className="font-medium">Net effect over ten weeks</span>
            <span className={`figure text-3xl ${net >= 0 ? "text-gain" : "text-loss"}`}>{net >= 0 ? "+" : "−"}{inr(Math.abs(net))}</span>
          </div>
          <p className="mt-3 text-sm text-graphite">{th === best[0] ? "This is the best cut-off for this seller." : `The best cut-off for this seller is ${best[0]}%, worth +${inr(best[4])}.`}</p>
        </div>
      </Reveal>
    </section>
  );
}

function How() {
  const steps = [
    ["Upload your files", "Orders, shipments, courier invoices, COD statements and your rate card. Column names are matched for you, and rows that cannot be read are reported with the reason."],
    ["Review the findings", "One line per disputed charge: what was billed, what it should have been, and why. Nothing is flagged unless it can be priced from your own data."],
    ["Send the claim", "Download a claim file for each courier, ready to send. Then check new orders for return risk before they leave the warehouse."],
  ];
  return (
    <section id="how" className="scroll-mt-16 border-t border-rule">
      <div className={`${wrap} py-16 lg:py-24`}>
        <Reveal><p className="eyebrow">How it works</p><h2 className={`${h2} mt-3`}>Three steps, no integration</h2></Reveal>
        <div className="mt-10 grid gap-5 lg:grid-cols-3">
          {steps.map(([title, text], i) => (
            <Reveal key={title} delay={i * 0.1} className="card group p-7 transition hover:-translate-y-1 hover:border-brand hover:shadow-[0_20px_40px_-24px_rgba(99,91,255,0.5)]">
              <span className="flex h-11 w-11 items-center justify-center rounded-xl bg-ink font-mono text-white transition group-hover:bg-brand">{i + 1}</span>
              <h3 className="mt-5 text-xl font-semibold">{title}</h3>
              <p className="mt-2 text-graphite">{text}</p>
            </Reveal>
          ))}
        </div>
        <Reveal className="relative mt-14 overflow-hidden rounded-3xl bg-ink px-7 py-12 text-white sm:px-12">
          <PixelField className="opacity-70" />
          <div className="relative flex flex-wrap items-center justify-between gap-6">
            <p className="display max-w-xl text-3xl leading-tight sm:text-4xl">See what your last three months of courier bills are hiding.</p>
            <Link to="/signup" className="btn px-7 py-4 text-base">Start with your files</Link>
          </div>
        </Reveal>
      </div>
    </section>
  );
}

export default function Landing() {
  return (
    <div id="top">
      <Nav />
      <main>
        <Hero />
        <Ticker />
        <Product />
        <Explore />
        <Risk />
        <Threshold />
        <How />
      </main>
      <footer className="border-t border-rule">
        <div className={`${wrap} flex flex-wrap justify-between gap-3 py-7 text-sm text-graphite`}>
          <span>logis — Logistics, worry-free.</span>
          <span>Figures on this page come from a sample dataset, not a real merchant.</span>
        </div>
      </footer>
      <Outlet />
    </div>
  );
}
