import { createContext, createElement, useCallback, useContext, useEffect, useState } from "react";
import { api } from "./api";

// One GET /api/workspace/status/ per app load, shared by every page and the sidebar.
// State is { status: "loading" } | { status: "error", message, retry } | { status: "ready", counts, model, reload }.
// A failed request is an error, never "no data", and nothing ever falls back to sample figures.
const WorkspaceContext = createContext(null);

const COUNT_KEYS = ["orders", "customers", "shipments", "shipments_with_outcome", "cod_shipments",
  "pincode_zones", "rate_cards", "invoice_lines", "remittances"];

function wellFormed(d) {
  return Boolean(d && d.counts && d.model && typeof d.model.state === "string"
    && COUNT_KEYS.every((k) => Number.isFinite(Number(d.counts[k]))));
}

export function WorkspaceProvider({ children }) {
  const [attempt, setAttempt] = useState(0);
  const [state, setState] = useState({ status: "loading" });

  useEffect(() => {
    let alive = true;
    // A refresh after an upload keeps the current figures on screen until the new ones arrive.
    setState((s) => (s.status === "ready" ? s : { status: "loading" }));
    api("/api/workspace/status/")
      .then((d) => {
        if (!wellFormed(d)) throw new Error("The server sent an unexpected response.");
        if (alive) setState({ status: "ready", counts: d.counts, model: d.model });
      })
      .catch((e) => alive && setState({ status: "error", message: e?.message || "Something went wrong. Try again." }));
    return () => {
      alive = false;
    };
  }, [attempt]);

  const reload = useCallback(() => setAttempt((n) => n + 1), []);
  const value = state.status === "error" ? { ...state, retry: reload, reload } : { ...state, reload };
  return createElement(WorkspaceContext.Provider, { value }, children);
}

export function useWorkspace() {
  return useContext(WorkspaceContext) ?? { status: "loading", reload: () => {} };
}
