import { Link } from "react-router-dom";
import Logo from "../components/Logo";

// The demo's own frame. It never uses the merchant workspace, the API client or a login.
// The gold banner stays on screen while scrolling, so nobody mistakes these figures for their own.
const SECTIONS = [["overview", "Overview"], ["money", "Money"], ["trend", "Trend"], ["returns", "Returns"], ["couriers", "Couriers"], ["risk", "Risk"], ["economics", "Economics"], ["customers", "Customers"]];

export function DemoBanner() {
  return (
    <div role="note" className="sticky top-0 z-30 border-b-2 border-gold bg-caution-bg">
      <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-x-4 gap-y-2 px-5 py-2.5 sm:px-8">
        <p className="min-w-0 text-sm text-ink">
          <span className="font-semibold">Demo Workspace — Sample Data.</span>{" "}
          Every figure here comes from an illustrative sample store, not from a real merchant. Nothing here is saved.
        </p>
        <div className="flex shrink-0 items-center gap-2">
          <Link to="/" className="rounded-lg px-3 py-2 text-sm font-medium transition hover:bg-sheet">Back to home</Link>
          <Link to="/signup" className="btn px-4 py-2 text-sm">Use your own data</Link>
        </div>
      </div>
    </div>
  );
}

export default function DemoLayout({ children }) {
  return (
    <div className="min-h-screen bg-paper">
      <DemoBanner />
      <header className="border-b border-rule bg-sheet">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-3 px-5 py-3 sm:px-8">
          <div className="flex items-center gap-3">
            <Logo to="/" />
            <span className="rounded-full border border-gold px-2.5 py-0.5 font-mono text-[11px] uppercase tracking-wider text-ink">Demo</span>
          </div>
          <Link to="/login" className="rounded-lg px-4 py-2.5 text-[15px] font-medium transition hover:bg-wash">Log in</Link>
        </div>
        <nav aria-label="Demo sections" className="mx-auto flex max-w-6xl gap-2 overflow-x-auto px-5 pb-3 sm:px-8">
          {SECTIONS.map(([id, name]) => <a key={id} href={`#${id}`} className="chip whitespace-nowrap">{name}</a>)}
        </nav>
      </header>
      <main className="mx-auto max-w-6xl px-5 py-7 sm:px-8 lg:py-9">{children}</main>
    </div>
  );
}
