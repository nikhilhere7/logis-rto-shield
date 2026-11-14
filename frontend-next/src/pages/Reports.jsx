import { motion } from "motion/react";
import { useState } from "react";
import { Link } from "react-router-dom";
import { PageHeader, Panel } from "../components/AppShell";
import { StatusPill } from "../components/FeatureAvailability";
import { Loading, SectionError } from "../components/parts";
import { download } from "../lib/api";
import { useApi } from "../lib/useApi";

// What each report is good for. The titles, descriptions and availability come from the server.
const USE = {
  summary: "Send it to a partner or investor who wants the whole picture in two pages.",
  returns: "Use it to decide where to stop offering cash on delivery.",
  couriers: "Take it into your next rate negotiation with a courier.",
  audit: "Attach it to the claim you send each courier, with the claim file from the Billing audit page.",
  customers: "Use it to pick who gets prepaid-only and who gets your best offers.",
};
const list = (v) => (Array.isArray(v) ? v : []);
const clock = () => new Date().toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit" });

function ReportCard({ report, index }) {
  const [state, setState] = useState({ status: "idle" });   // idle | busy | done | error
  const save = async () => {
    setState({ status: "busy" });
    try {
      await download(`/api/reports/${report.id}.pdf`);   // the server names the file: merchant, report and date
      setState({ status: "done", at: clock() });
    } catch (e) {
      setState({ status: "error", message: e.message });
    }
  };
  return (
    <motion.div initial={{ opacity: 0, y: 14 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.4, delay: index * 0.06 }} className="min-w-0">
      <Panel className="flex h-full flex-col">
        <div className="flex flex-wrap items-start justify-between gap-2">
          <h2 className="display text-xl">{report.title}</h2>
          <StatusPill status={report.available ? "available" : "needs-data"}>{report.available ? "Ready" : "Needs data"}</StatusPill>
        </div>
        <p className="mt-2 text-sm text-graphite">{report.description}</p>
        {USE[report.id] && <p className="mt-2 text-sm">{USE[report.id]}</p>}
        <div className="mt-auto pt-5">
          {report.available ? (
            <div className="flex flex-wrap items-center gap-3">
              <button type="button" onClick={save} disabled={state.status === "busy"} className="btn py-2.5 text-sm disabled:opacity-60">
                {state.status === "busy" ? "Building the PDF…" : state.status === "done" ? "Download again" : "Download PDF"}
              </button>
              {state.status === "done" && <p role="status" className="text-sm text-gain">Downloaded at {state.at}</p>}
            </div>
          ) : (
            <div className="rounded-xl bg-wash px-4 py-3 text-sm">
              <p className="text-graphite">{report.reason}</p>
              <Link to="/app/uploads" className="mt-1 inline-block font-medium text-brand-deep underline underline-offset-4">Go to uploads</Link>
            </div>
          )}
          {state.status === "error" && <p role="alert" className="mt-3 rounded-lg border border-loss px-3.5 py-2.5 text-sm text-loss">Couldn't build this report. {state.message}</p>}
        </div>
      </Panel>
    </motion.div>
  );
}

export default function Reports() {
  const { data, error, loading, reload } = useApi({ reports: "/api/reports/" });
  const reports = list(data?.reports);
  const ready = reports.filter((r) => r.available).length;
  return (
    <>
      <PageHeader title="Reports" sub={data ? `${ready} of ${reports.length} reports are ready to download` : null} />
      {error ? <SectionError message={error} onRetry={reload} /> : loading && !data ? <Loading text="Checking which reports you can build…" /> : (
        <>
          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
            {reports.map((r, i) => <ReportCard key={r.id} report={r} index={i} />)}
          </div>
          <p className="mt-6 max-w-2xl text-sm text-graphite">
            Each PDF is built when you press the button, from the data in your workspace at that moment, and covers everything you have uploaded.
            Nothing is stored on the server, and customer phone numbers never appear.
          </p>
        </>
      )}
    </>
  );
}
