// The one place the frontend talks to the Django API.
// Tokens live in localStorage. They are never logged or shown.
const BASE = (import.meta.env.VITE_API_URL || "http://127.0.0.1:8000").replace(/\/+$/, "");
const KEY = "logis-session";

// A stored session is only trusted when it has both tokens (as strings) and a user object.
function valid(s) {
  return Boolean(
    s && typeof s === "object" && typeof s.access === "string" && s.access && typeof s.refresh === "string" && s.refresh && s.user && typeof s.user === "object",
  );
}

export const session = {
  read() {
    try {
      const s = JSON.parse(localStorage.getItem(KEY) || "null");
      return valid(s) ? s : null;
    } catch {
      return null; // malformed JSON or storage blocked
    }
  },
  save(s) {
    try {
      localStorage.setItem(KEY, JSON.stringify({ access: s.access, refresh: s.refresh, user: s.user }));
    } catch {
      /* storage full or blocked: the session won't survive a reload */
    }
  },
  clear() {
    try {
      localStorage.removeItem(KEY);
    } catch {
      /* nothing to clear */
    }
  },
};

async function send(path, { method = "GET", body, token } = {}) {
  const file = body instanceof FormData; // file uploads: the browser sets the multipart content type and boundary itself
  let res;
  try {
    res = await fetch(BASE + path, {
      method,
      headers: {
        Accept: "application/json",
        ...(body !== undefined && !file ? { "Content-Type": "application/json" } : {}),
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body: body === undefined ? undefined : file ? body : JSON.stringify(body),
    });
  } catch {
    return { ok: false, status: 0, data: { detail: "Can't reach the logis server. Check your connection and try again." } };
  }
  // Non-JSON bodies (an HTML error page, an empty 204) must not crash the caller.
  let data = null;
  if (res.status !== 204) {
    const text = await res.text().catch(() => "");
    if (text) {
      try {
        data = JSON.parse(text);
      } catch {
        data = res.ok ? text : { detail: `The server answered with an error (${res.status}). Try again.` };
      }
    }
  }
  return { ok: res.ok, status: res.status, data };
}

// Turn DRF's error shapes into one sentence a person can read.
//   {"detail": "..."} | {"field": ["...", ...]} | ["..."] | "text" | null
export function errorText(data, fallback = "Something went wrong. Try again.") {
  if (!data) return fallback;
  if (typeof data === "string") return data;
  if (typeof data.detail === "string") return data.detail;
  const first = Array.isArray(data) ? data[0] : Object.values(data)[0];
  if (Array.isArray(first)) return String(first[0] ?? fallback);
  if (first && typeof first === "object") return errorText(first, fallback);
  return first == null ? fallback : String(first);
}

export class ApiError extends Error {
  constructor(status, data) {
    super(errorText(data));
    this.status = status;
    this.data = data;
  }
}

// Calls that need no login: signup and login.
export async function open(path, body) {
  const r = await send(path, { method: "POST", body });
  if (!r.ok) throw new ApiError(r.status, r.data);
  return r.data;
}

// Several requests can expire at the same moment (the dashboard loads seven at once).
// They all wait for ONE shared refresh request instead of each spending the refresh token.
let refreshing = null;

function refreshAccess(refreshToken) {
  if (!refreshing) {
    refreshing = send("/api/auth/refresh/", { method: "POST", body: { refresh: refreshToken } })
      .then((r) => (r.ok && typeof r.data?.access === "string" ? r.data.access : null))
      .finally(() => {
        refreshing = null;
      });
  }
  return refreshing;
}

// The session is over: clear it and reopen the log in pop-up.
// /login is a real route here: it renders the landing page with the log in pop-up on top.
let leaving = false;

function endSession() {
  session.clear();
  if (!leaving && window.location.pathname !== "/login") {
    leaving = true;
    window.location.assign("/login");
  }
}

// Every authenticated call. On a 401 the refresh token is swapped for a new access token and the
// original request is retried exactly once. If the refresh fails or the retry is still 401, the session ends.
export async function api(path, options = {}) {
  const s = session.read();
  if (!s) {
    endSession();
    throw new ApiError(401, { detail: "Please log in." });
  }

  let r = await send(path, { ...options, token: s.access });

  if (r.status === 401) {
    const access = await refreshAccess(s.refresh);
    if (access) {
      const current = session.read();
      // Only store it if this is still the same session (the person may have logged out meanwhile).
      if (current?.refresh === s.refresh) session.save({ ...current, access });
      r = await send(path, { ...options, token: access });
    }
  }

  if (r.status === 401) {
    endSession();
    throw new ApiError(401, { detail: "Your session expired. Log in again." });
  }
  if (!r.ok) throw new ApiError(r.status, r.data);
  return r.data;
}
