import { useCallback, useEffect, useState } from "react";
import { api } from "./api";

// Load several endpoints at once: useApi({ overview: "/api/metrics/overview/", ... })
// Returns { data, error, loading, reload }. error is a readable message (string) or null.
// loading is cleared on success AND on failure. The paths object is compared by value.
export function useApi(paths) {
  const key = JSON.stringify(paths);
  const [attempt, setAttempt] = useState(0);
  const [state, setState] = useState({ data: null, error: null, loading: true });

  useEffect(() => {
    let alive = true;
    const entries = Object.entries(JSON.parse(key));
    setState((s) => ({ ...s, loading: true, error: null }));
    Promise.all(entries.map(([, path]) => api(path)))
      .then((values) => alive && setState({ data: Object.fromEntries(entries.map(([name], i) => [name, values[i]])), error: null, loading: false }))
      .catch((e) => alive && setState({ data: null, error: e?.message || "Something went wrong. Try again.", loading: false }));
    return () => {
      alive = false;
    };
  }, [key, attempt]);

  const reload = useCallback(() => setAttempt((n) => n + 1), []);
  return { ...state, reload };
}
