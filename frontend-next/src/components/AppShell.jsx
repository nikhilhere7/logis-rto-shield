import { useEffect, useRef, useState } from "react";
import { NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import { useAuth } from "../lib/auth";
import { featuresFor } from "../lib/features";
import { useWorkspace, WorkspaceProvider } from "../lib/useWorkspace";
import Logo from "./Logo";

// [name, path, feature] — the feature decides the small muted tag (e.g. "Needs shipments"). Every item stays visible.
const MAIN = [["Dashboard", "/app"], ["Risk checker", "/app/risk", "risk"], ["Customers", "/app/customers", "customers"], ["Couriers", "/app/couriers", "couriers"], ["RTO analytics", "/app/rto", "rto"], ["Billing audit", "/app/audit", "audit"]];
const DATA = [["Uploads", "/app/uploads"], ["Reports", "/app/reports", "reports"]];

const item = ({ isActive }) =>
  `flex items-center justify-between gap-2 whitespace-nowrap rounded-md px-3.5 py-2.5 text-[15px] transition ${isActive ? "bg-ink font-medium text-white" : "text-graphite hover:bg-wash hover:text-ink"}`;

function NavItem({ name, to, tag }) {
  return (
    <NavLink to={to} end={to === "/app"} className={item}>
      {({ isActive }) => (
        <>
          {name}
          {tag && <span className={`rounded-full px-2 py-0.5 text-[11px] font-normal ${isActive ? "bg-white/15 text-white" : "bg-wash text-graphite"}`}>{tag}</span>}
        </>
      )}
    </NavLink>
  );
}

function Avatar({ initials }) {
  return <span aria-hidden="true" className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-brand text-sm font-medium text-white">{initials}</span>;
}

// Phones and tablets (below lg): the sidebar's account row is hidden there, so the header gets a small
// account button that opens the merchant's identity and the same Log out action.
function AccountMenu({ user, initials, onSignOut }) {
  const [open, setOpen] = useState(false);
  const box = useRef(null);
  const { pathname } = useLocation();
  useEffect(() => setOpen(false), [pathname]);
  useEffect(() => {
    if (!open) return undefined;
    const away = (e) => { if (box.current && !box.current.contains(e.target)) setOpen(false); };
    const esc = (e) => e.key === "Escape" && setOpen(false);
    document.addEventListener("pointerdown", away);
    document.addEventListener("keydown", esc);
    return () => { document.removeEventListener("pointerdown", away); document.removeEventListener("keydown", esc); };
  }, [open]);
  return (
    <div ref={box} className="relative lg:hidden">
      <button type="button" aria-expanded={open} aria-controls="account-menu" onClick={() => setOpen((o) => !o)}
        className="flex min-h-11 items-center gap-2 rounded-full pl-1 pr-1 transition hover:bg-wash">
        <span className="sr-only">Account: {user?.merchant || "your workspace"}</span>
        <Avatar initials={initials} />
      </button>
      {open && (
        <div id="account-menu" className="card absolute right-0 top-full z-30 mt-2 w-64 max-w-[calc(100vw-2rem)] p-4 shadow-[0_16px_32px_-20px_rgba(10,37,64,0.45)]">
          <p className="truncate font-medium">{user?.merchant}</p>
          {(user?.name || user?.email) && <p className="mt-0.5 truncate text-sm text-graphite">{user?.name}{user?.name && user?.email ? " · " : ""}{user?.email}</p>}
          <button type="button" onClick={onSignOut} className="btn-quiet mt-4 w-full py-2.5 text-sm">Log out</button>
        </div>
      )}
    </div>
  );
}

export default function AppShell() {
  return (
    <WorkspaceProvider>
      <Shell />
    </WorkspaceProvider>
  );
}

function Shell() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const ws = useWorkspace();
  // Tags only appear once the real status is known; while loading or after an error, items show no tag.
  const features = ws.status === "ready" ? featuresFor(ws.counts, ws.model) : null;
  const tagOf = (feature) => (feature && features?.[feature]?.tag) || null;
  const initials = (user?.merchant || "?").split(/\s+/).map((w) => w[0]).slice(0, 2).join("").toUpperCase();
  // The one way to log out, used by the desktop sidebar and the phone/tablet account menu alike.
  const signOut = () => { logout(); navigate("/"); };
  return (
    <div className="flex min-h-screen flex-col lg:flex-row">
      <aside className="flex shrink-0 flex-col gap-4 border-b border-rule bg-sheet px-4 py-4 lg:sticky lg:top-0 lg:h-screen lg:w-60 lg:gap-6 lg:border-b-0 lg:border-r lg:py-6">
        <div className="flex items-center justify-between gap-3 px-2">
          <Logo to="/app" />
          <AccountMenu user={user} initials={initials} onSignOut={signOut} />
        </div>
        <nav aria-label="Main" className="flex gap-1 overflow-x-auto lg:flex-col lg:overflow-visible">
          {MAIN.map(([name, to, feature]) => <NavItem key={to} name={name} to={to} tag={tagOf(feature)} />)}
        </nav>
        {/* Below lg it is a second scrolling row, like Main; from lg it is the sidebar's lower group as before. */}
        <nav aria-label="Data" className="-mt-2 flex gap-1 overflow-x-auto lg:mt-0 lg:flex-col lg:overflow-visible lg:border-t lg:border-rule lg:pt-4">
          {DATA.map(([name, to, feature]) => <NavItem key={to} name={name} to={to} tag={tagOf(feature)} />)}
        </nav>
        <div className="mt-auto hidden items-center gap-3 border-t border-rule px-2 pt-4 lg:flex">
          <Avatar initials={initials} />
          <div className="min-w-0 text-sm">
            <p className="truncate font-medium">{user?.merchant}</p>
            <button type="button" className="text-graphite underline-offset-4 hover:text-ink hover:underline" onClick={signOut}>Log out</button>
          </div>
        </div>
      </aside>
      <main className="min-w-0 flex-1 px-5 py-7 sm:px-8 lg:px-10 lg:py-9"><Outlet /></main>
    </div>
  );
}

export function PageHeader({ title, sub, children }) {
  return (
    <div className="mb-7 flex flex-wrap items-end justify-between gap-4">
      <div>
        <h1 className="display text-3xl leading-tight sm:text-4xl">{title}</h1>
        {sub && <p className="mt-1.5 text-sm text-graphite">{sub}</p>}
      </div>
      {children}
    </div>
  );
}

export function Panel({ title, note, action, children, className = "" }) {
  return (
    <section className={`card p-5 sm:p-6 ${className}`}>
      {(title || action) && (
        <div className="mb-4 flex flex-wrap items-baseline justify-between gap-2">
          <div><h2 className="font-semibold">{title}</h2>{note && <p className="text-[13px] text-graphite">{note}</p>}</div>
          {action}
        </div>
      )}
      {children}
    </section>
  );
}
