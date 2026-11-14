import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import { useEffect, useRef, useState } from "react";
import { NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import { useAuth } from "../lib/auth";
import { featuresFor } from "../lib/features";
import { useWorkspace, WorkspaceProvider } from "../lib/useWorkspace";
import { Mark } from "./Logo";

// ---------------------------------------------------------------- icons (inline, no icon library)
const PATHS = {
  dashboard: "M4 4h7v7H4zM13 4h7v4h-7zM13 10h7v10h-7zM4 13h7v7H4z",
  risk: "M12 3l7 3v5c0 4.5-3 8.3-7 10-4-1.7-7-5.5-7-10V6l7-3zM12 8v4M12 15.5v.5",
  customers: "M9 11a3.5 3.5 0 1 0 0-7 3.5 3.5 0 0 0 0 7zM2.5 20c.6-3.3 3.3-5.5 6.5-5.5s5.9 2.2 6.5 5.5M16 4.3a3.5 3.5 0 0 1 0 6.4M18 14.8c1.9.7 3.2 2.6 3.5 5.2",
  couriers: "M3 6h11v10H3zM14 9h4l3 3.5V16h-7M7 19a2 2 0 1 0 0-4 2 2 0 0 0 0 4zM17.5 19a2 2 0 1 0 0-4 2 2 0 0 0 0 4z",
  rto: "M4 12a8 8 0 1 0 2.4-5.7M4 4v4h4",
  audit: "M6 3h12v18l-3-2-3 2-3-2-3 2zM9 8h6M9 12h6M9 16h3",
  uploads: "M12 15V4M7.5 8.5L12 4l4.5 4.5M4 15v4h16v-4",
  reports: "M7 3h7l5 5v13H7zM14 3v5h5M10 13h6M10 17h6",
  logout: "M14 4h5v16h-5M10 8l-4 4 4 4M6 12h10",
  menu: "M4 7h16M4 12h16M4 17h16",
  collapse: "M15 6l-6 6 6 6",
};

function Icon({ name, className = "h-5 w-5" }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" className={`shrink-0 ${className}`}>
      <path d={PATHS[name]} />
    </svg>
  );
}

// [name, path, icon, feature]: the feature decides the small muted tag (e.g. "Needs shipments"). Every item stays visible.
const MAIN = [["Dashboard", "/app", "dashboard"], ["Risk checker", "/app/risk", "risk", "risk"], ["Customers", "/app/customers", "customers", "customers"], ["Couriers", "/app/couriers", "couriers", "couriers"], ["RTO analytics", "/app/rto", "rto", "rto"], ["Billing audit", "/app/audit", "audit", "audit"]];
const DATA = [["Uploads", "/app/uploads", "uploads"], ["Reports", "/app/reports", "reports", "reports"]];

const EASE = [0.22, 1, 0.36, 1];
const WIDE = 240, RAIL = 68;          // sidebar width in px: expanded, collapsed
const STORE = "logis-sidebar";        // remembers the choice in this browser only; a convenience, never required

function readCollapsed() {
  try { return localStorage.getItem(STORE) === "collapsed"; } catch { return false; }
}

// ---------------------------------------------------------------- one navigation item
// The active background is a single shared element (layoutId) that glides between items.
function NavItem({ name, to, icon, tag, collapsed, group, onPick }) {
  const still = useReducedMotion();
  const showLabel = !collapsed;
  return (
    <NavLink to={to} end={to === "/app"} onClick={onPick} aria-label={collapsed ? (tag ? `${name} (${tag})` : name) : undefined}
      className={({ isActive }) => `group relative flex h-11 items-center rounded-lg px-3 text-[15px] outline-none transition-colors focus-visible:ring-2 focus-visible:ring-brand ${isActive ? "font-medium text-white" : "text-graphite hover:bg-wash hover:text-ink"}`}>
      {({ isActive }) => (
        <>
          {isActive && (
            <motion.span layoutId={`nav-active-${group}`} aria-hidden="true" className="absolute inset-0 rounded-lg bg-ink"
              transition={still ? { duration: 0 } : { duration: 0.3, ease: EASE }} />
          )}
          <span className="relative z-10 flex min-w-0 flex-1 items-center gap-3 overflow-hidden">
            <span className="relative">
              <Icon name={icon} />
              {collapsed && tag && <span aria-hidden="true" className={`absolute -right-1 -top-1 h-2 w-2 rounded-full ${isActive ? "bg-gold" : "bg-graphite/50"}`} />}
            </span>
            <AnimatePresence initial={false}>
              {showLabel && (
                <motion.span key="label" className="flex min-w-0 flex-1 items-center justify-between gap-2 whitespace-nowrap"
                  initial={still ? false : { opacity: 0, x: -6 }} animate={{ opacity: 1, x: 0 }} exit={still ? { opacity: 0 } : { opacity: 0, x: -6 }}
                  transition={{ duration: still ? 0 : 0.18, ease: EASE, delay: still ? 0 : 0.08 }}>
                  <span className="truncate">{name}</span>
                  {tag && <span className={`shrink-0 rounded-full px-2 py-0.5 text-[11px] font-normal ${isActive ? "bg-white/15 text-white" : "bg-wash text-graphite"}`}>{tag}</span>}
                </motion.span>
              )}
            </AnimatePresence>
          </span>
          {collapsed && <Tooltip>{name}{tag ? ` · ${tag}` : ""}</Tooltip>}
        </>
      )}
    </NavLink>
  );
}

// Shown beside an icon in the collapsed rail, on hover and on keyboard focus.
function Tooltip({ children }) {
  return (
    <span role="tooltip" className="pointer-events-none absolute left-full top-1/2 z-40 ml-3 -translate-y-1/2 -translate-x-1 whitespace-nowrap rounded-md bg-ink px-2.5 py-1.5 text-xs font-medium text-white opacity-0 shadow-lg transition duration-150 group-hover:translate-x-0 group-hover:opacity-100 group-focus-visible:translate-x-0 group-focus-visible:opacity-100">
      {children}
    </span>
  );
}

function Avatar({ initials }) {
  return <span aria-hidden="true" className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-brand text-sm font-medium text-white">{initials}</span>;
}

function Wordmark() {
  return <span className="display whitespace-nowrap text-xl leading-none">logis</span>;
}

// Phones and tablets (below lg): the account button in the top bar opens the merchant's identity and the
// same Log out action.
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

// Both navigation groups. Used by the desktop sidebar (expanded or as a rail) and by the phone drawer.
function NavGroups({ tagOf, collapsed, group, onPick }) {
  const items = (list) => list.map(([name, to, icon, feature]) => (
    <NavItem key={to} name={name} to={to} icon={icon} tag={tagOf(feature)} collapsed={collapsed} group={group} onPick={onPick} />
  ));
  return (
    <>
      <nav aria-label="Main" className="flex flex-col gap-1">{items(MAIN)}</nav>
      <nav aria-label="Data" className="flex flex-col gap-1 border-t border-rule pt-4">{items(DATA)}</nav>
    </>
  );
}

function AccountRow({ user, initials, collapsed, onSignOut }) {
  return (
    <div className={`mt-auto flex items-center gap-3 border-t border-rule pt-4 ${collapsed ? "flex-col px-0" : "px-2"}`}>
      <span className="group relative">
        <Avatar initials={initials} />
        {collapsed && <Tooltip>{user?.merchant}</Tooltip>}
      </span>
      {collapsed ? (
        <button type="button" onClick={onSignOut} aria-label="Log out" className="group relative flex h-10 w-10 items-center justify-center rounded-lg text-graphite transition hover:bg-wash hover:text-ink focus-visible:ring-2 focus-visible:ring-brand">
          <Icon name="logout" />
          <Tooltip>Log out</Tooltip>
        </button>
      ) : (
        <div className="min-w-0 text-sm">
          <p className="truncate font-medium">{user?.merchant}</p>
          <button type="button" className="text-graphite underline-offset-4 hover:text-ink hover:underline" onClick={onSignOut}>Log out</button>
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
  const still = useReducedMotion();
  const { pathname } = useLocation();
  // Tags only appear once the real status is known; while loading or after an error, items show no tag.
  const features = ws.status === "ready" ? featuresFor(ws.counts, ws.model) : null;
  const tagOf = (feature) => (feature && features?.[feature]?.tag) || null;
  const initials = (user?.merchant || "?").split(/\s+/).map((w) => w[0]).slice(0, 2).join("").toUpperCase();
  // The one way to log out, used by the sidebar, the rail and the phone account menu alike.
  const signOut = () => { logout(); navigate("/"); };

  // Desktop: expanded or collapsed to an icon rail. Toggled by the logo.
  const [collapsed, setCollapsed] = useState(readCollapsed);
  const toggle = () => setCollapsed((c) => {
    try { localStorage.setItem(STORE, c ? "expanded" : "collapsed"); } catch { /* storage blocked: still works for this visit */ }
    return !c;
  });

  // Phones and tablets: a drawer that slides in over the page.
  const [drawer, setDrawer] = useState(false);
  useEffect(() => setDrawer(false), [pathname]);
  useEffect(() => {
    if (!drawer) return undefined;
    const esc = (e) => e.key === "Escape" && setDrawer(false);
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";           // the page behind does not scroll while the drawer is open
    document.addEventListener("keydown", esc);
    return () => { document.body.style.overflow = prev; document.removeEventListener("keydown", esc); };
  }, [drawer]);
  // Widening the window to desktop closes the drawer, so the page never stays scroll-locked.
  useEffect(() => {
    const wide = window.matchMedia("(min-width: 1024px)");
    const close = () => wide.matches && setDrawer(false);
    wide.addEventListener("change", close);
    return () => wide.removeEventListener("change", close);
  }, []);

  const slide = still ? { duration: 0 } : { duration: 0.3, ease: EASE };

  return (
    <div className="flex min-h-screen flex-col lg:flex-row">
      {/* ---------------- desktop sidebar (lg and up) */}
      <motion.aside initial={false} animate={{ width: collapsed ? RAIL : WIDE }} transition={slide}
        className="sticky top-0 z-20 hidden h-screen shrink-0 flex-col gap-6 border-r border-rule bg-sheet px-3 py-6 lg:flex">
        <button type="button" onClick={toggle} aria-expanded={!collapsed} aria-controls="app-sidebar-nav"
          aria-label={collapsed ? "Expand the sidebar" : "Collapse the sidebar"}
          className="group relative flex min-h-11 items-center gap-2.5 rounded-lg px-[7px] text-left outline-none transition hover:bg-wash focus-visible:ring-2 focus-visible:ring-brand">
          <Mark />
          <AnimatePresence initial={false}>
            {!collapsed && (
              <motion.span key="word" className="flex flex-1 items-center justify-between overflow-hidden"
                initial={still ? false : { opacity: 0, x: -6 }} animate={{ opacity: 1, x: 0 }} exit={still ? { opacity: 0 } : { opacity: 0, x: -6 }}
                transition={{ duration: still ? 0 : 0.18, ease: EASE, delay: still ? 0 : 0.08 }}>
                <Wordmark />
                <span className="text-graphite opacity-0 transition group-hover:opacity-100 group-focus-visible:opacity-100"><Icon name="collapse" className="h-4 w-4" /></span>
              </motion.span>
            )}
          </AnimatePresence>
          {collapsed && <Tooltip>Expand the sidebar</Tooltip>}
        </button>
        <div id="app-sidebar-nav" className="flex flex-1 flex-col gap-4">
          <NavGroups tagOf={tagOf} collapsed={collapsed} group="rail" />
          <AccountRow user={user} initials={initials} collapsed={collapsed} onSignOut={signOut} />
        </div>
      </motion.aside>

      {/* ---------------- phone and tablet top bar (below lg) */}
      <header className="sticky top-0 z-30 flex items-center justify-between gap-3 border-b border-rule bg-sheet/95 px-4 py-2 backdrop-blur lg:hidden">
        <button type="button" onClick={() => setDrawer(true)} aria-expanded={drawer} aria-controls="app-drawer" aria-label="Open navigation"
          className="flex min-h-11 items-center gap-2.5 rounded-lg px-1.5 outline-none transition hover:bg-wash focus-visible:ring-2 focus-visible:ring-brand">
          <Mark />
          <Wordmark />
          <span className="text-graphite"><Icon name="menu" className="h-5 w-5" /></span>
        </button>
        <AccountMenu user={user} initials={initials} onSignOut={signOut} />
      </header>

      <AnimatePresence>
        {drawer && (
          <div className="fixed inset-0 z-50 lg:hidden">
            <motion.div aria-hidden="true" className="absolute inset-0 bg-ink/40 backdrop-blur-[1px]" onClick={() => setDrawer(false)}
              initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} transition={still ? { duration: 0 } : { duration: 0.2 }} />
            <motion.aside id="app-drawer" role="dialog" aria-modal="true" aria-label="Navigation"
              className="absolute inset-y-0 left-0 flex w-[280px] max-w-[85vw] flex-col gap-6 overflow-y-auto bg-sheet px-3 py-5 shadow-2xl"
              initial={{ x: "-100%" }} animate={{ x: 0 }} exit={{ x: "-100%" }} transition={slide}>
              <button type="button" onClick={() => setDrawer(false)} aria-label="Close navigation"
                className="flex min-h-11 items-center gap-2.5 rounded-lg px-[7px] text-left outline-none transition hover:bg-wash focus-visible:ring-2 focus-visible:ring-brand">
                <Mark />
                <Wordmark />
                <span className="ml-auto text-graphite"><Icon name="collapse" className="h-4 w-4" /></span>
              </button>
              <div className="flex flex-1 flex-col gap-4">
                <NavGroups tagOf={tagOf} collapsed={false} group="drawer" onPick={() => setDrawer(false)} />
                <AccountRow user={user} initials={initials} collapsed={false} onSignOut={signOut} />
              </div>
            </motion.aside>
          </div>
        )}
      </AnimatePresence>

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
