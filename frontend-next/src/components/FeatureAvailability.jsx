import { Link } from "react-router-dom";
import { featuresFor } from "../lib/features";
import { useWorkspace } from "../lib/useWorkspace";
import { PageHeader, Panel } from "./AppShell";

// Calm labels for everything that is not a failure. Red is kept for "unavailable" (the API failed).
const LOOK = {
  available: ["Available", "bg-gain/10 text-gain"],
  "needs-data": ["Needs data", "bg-wash text-brand-deep"],
  "needs-model": ["Not ready yet", "bg-wash text-graphite"],
  "coming-soon": ["Coming soon", "bg-wash text-graphite"],
  unavailable: ["Couldn't load", "bg-loss/10 text-loss"],
};

export function StatusPill({ status, children }) {
  const [label, look] = LOOK[status] || LOOK["needs-data"];
  return <span className={`shrink-0 rounded-full px-2.5 py-1 text-xs font-medium ${look}`}>{children || label}</span>;
}

export default function FeatureAvailability({ status, title, description, actionLabel, to, onRetry, className = "" }) {
  const failed = status === "unavailable";
  return (
    <section role={failed ? "alert" : undefined} className={`card p-5 sm:p-6 ${failed ? "border-loss" : ""} ${className}`}>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="font-semibold">{title}</h2>
        <StatusPill status={status} />
      </div>
      {description && <p className={`mt-2 text-sm ${failed ? "text-loss" : "text-graphite"}`}>{description}</p>}
      {(to && actionLabel) || onRetry ? (
        <div className="mt-4 flex flex-wrap gap-3">
          {to && actionLabel && <Link to={to} className="btn py-2.5 text-sm">{actionLabel}</Link>}
          {onRetry && <button type="button" onClick={onRetry} className="btn-quiet py-2.5 text-sm">Try again</button>}
        </div>
      ) : null}
    </section>
  );
}

// The workspace status could not be read. Shows a retry, never sample figures and never onboarding.
export function WorkspaceError({ message, onRetry }) {
  return (
    <FeatureAvailability status="unavailable" title="Couldn't load your workspace" className="max-w-xl"
      description={`${message || "Something went wrong."} Your data is safe; this page just couldn't reach it.`} onRetry={onRetry} />
  );
}

// How the risk checker currently scores orders. Rule-based scores are never called model predictions.
export function RiskModeNote({ mode }) {
  if (!mode) return null;
  return (
    <Panel>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="font-semibold">{mode.headline}</h2>
        <StatusPill status="available">{mode.usesRules ? "Rules" : "Trained model"}</StatusPill>
      </div>
      {mode.explanation && <p className="mt-2 text-sm text-graphite">{mode.explanation}</p>}
      {mode.usesRules && <p className="mt-2 text-sm text-graphite">Rule-based scores are guidance from fixed rules. They are not predictions from a trained model.</p>}
    </Panel>
  );
}

// A sidebar page: its placeholder when the feature is available, its FeatureAvailability panel when not.
export function FeaturePage({ feature, title, children }) {
  const ws = useWorkspace();
  if (ws.status === "loading") return <p className="text-graphite" role="status">Loading your workspace…</p>;
  if (ws.status === "error") return <WorkspaceError message={ws.message} onRetry={ws.retry} />;
  const f = featuresFor(ws.counts, ws.model)[feature];
  if (f.status === "available") {
    return (
      <>
        <PageHeader title={title} />
        <div className="flex max-w-xl flex-col gap-4">
          {f.mode && <RiskModeNote mode={f.mode} />}
          {f.note && (
            <Panel title="Some checks are limited">
              <p className="text-sm text-graphite">{f.note}</p>
              {f.noteAction && <Link to={f.noteAction.to} className="btn-quiet mt-4 py-2.5 text-sm">{f.noteAction.label}</Link>}
            </Panel>
          )}
          {children}
        </div>
      </>
    );
  }
  return (
    <>
      <PageHeader title={title} />
      <FeatureAvailability {...f} title={f.title} className="max-w-xl" />
    </>
  );
}
