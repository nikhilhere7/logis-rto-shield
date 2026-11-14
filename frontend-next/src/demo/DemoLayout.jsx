import { Link } from "react-router-dom";
import Logo from "../components/Logo";

// The demo's own frame. It never uses the merchant workspace, the API client or a login.
// The gold banner stays on screen while scrolling, so nobody mistakes these figures for their own.
const SECTIONS = [["overview", "Overview"], ["money", "Money"], ["trend", "Trend"], ["returns", "Returns"], ["couriers", "Couriers"], ["risk", "Risk"], ["economics", "Economics"], ["customers", "Customers"]];

// One sticky block: the gold banner, then the logo row with the section links. Both stay while scrolling.
export function DemoBanner() {
  return (
    <div role="note" className="border-b-2 border-gold bg-caution-bg">
      <div className="mx-auto flex max-w-6xl items-center justify-between gap-3 px-5 py-1.5 sm:px-8">
        <p className="min-w-0 whitespace-nowrap text-sm text-ink max-sm:overflow-hidden"><span className="font-semibold">Demo data.</span> <span className="hidden md:inline">A sample store, not yours. Nothing here is saved.</span><span className="md:hidden">Not your numbers.</span></p>
        <div className="flex shrink-0 items-center gap-1.5">
          <Link to="/" className="rounded-lg px-3 py-1.5 text-sm font-medium transition hover:bg-sheet max-sm:hidden">Back to home</Link>
          <Link to="/signup" className="btn px-3.5 py-1.5 text-sm">Use your own data</Link>
        </div>
      </div>
    </div>
  );
}

export default function DemoLayout({ children }) {
  return (
    <div className="min-h-screen bg-paper">
      <div className="sticky top-0 z-30">
        <DemoBanner />
        <header className="border-b border-rule bg-sheet/95 backdrop-blur">
          <div className="mx-auto flex max-w-6xl items-center gap-x-5 gap-y-1 px-5 py-2 max-lg:flex-wrap sm:px-8">
            <div className="flex items-center gap-3">
              <Logo to="/" />
              <span className="rounded-full border border-gold px-2.5 py-0.5 font-mono text-[11px] uppercase tracking-wider text-ink">Demo</span>
            </div>
            <Link to="/login" className="ml-auto rounded-lg px-4 py-2 text-[15px] font-medium transition hover:bg-wash lg:order-last lg:ml-0">Log in</Link>
            <nav aria-label="Demo sections" className="no-scrollbar flex min-w-0 gap-2 overflow-x-auto max-lg:w-full lg:flex-1">
              {SECTIONS.map(([id, name]) => <a key={id} href={`#${id}`} className="chip whitespace-nowrap">{name}</a>)}
            </nav>
          </div>
        </header>
      </div>
      <main className="mx-auto max-w-6xl px-5 py-7 sm:px-8 lg:py-9">{children}</main>
    </div>
  );
}
