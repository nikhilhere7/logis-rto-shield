# M7a — Authentication, Frontend Shell, Landing Page and Dashboard

M7a gives RTO Shield a browser front end. Merchants can sign up, log in, and see a dashboard built from
the existing M2–M6 APIs. The public landing page explains the product using a clearly labelled sample
dataset. The other six app pages (risk checker, customers, couriers, RTO analytics, billing audit,
uploads, plus reports) are placeholders until M7b.

## 1. What changed

| Part | Where | What |
|---|---|---|
| Auth API | `backend/accounts/` | Sign up, log in, token refresh, "who am I". No models, no migrations. |
| Settings | `backend/config/settings.py` | JWT added in front of Session and Basic auth; CORS for the Vite dev server; signup/login throttles. |
| Frontend | `frontend/` | React 19 + Vite 8 + Tailwind CSS 4 + Motion 14 + React Router 7. |

## 2. Technology stack

| Concern | Choice |
|---|---|
| UI | React 19, function components and hooks |
| Build and dev server | Vite 8 with `@vitejs/plugin-react` |
| Styling | Tailwind CSS 4 via `@tailwindcss/vite`; the palette is declared in `@theme` in `src/index.css` |
| Animation | Motion 14 (`motion/react`); every animation respects `prefers-reduced-motion` |
| Routing | React Router 7 (`BrowserRouter`) |
| Charts | Hand-written SVG and CSS in `src/components/charts.jsx`. No chart library. |
| Fonts | Inter (interface), Source Serif 4 (headings and large figures), from Google Fonts |

No other runtime dependencies.

## 3. Frontend architecture

```
frontend/src/
├── main.jsx                 React root in StrictMode
├── App.jsx                  Routes: /, /login, /signup, /app (protected) and its children
├── index.css                @theme tokens, .figure/.num helpers, ticker, reduced-motion rules
├── lib/
│   ├── api.js               fetch wrapper: base URL, JSON, Bearer token, one refresh-and-retry, error text
│   ├── auth.jsx             AuthProvider, useAuth, RequireAuth
│   ├── useApi.js            Load several endpoints in parallel → { data, loading, error, reload }
│   └── format.js            count, inr, inrShort, pct, days, monthLabel (Indian number formatting)
├── components/
│   ├── Logo.jsx             Shield mark + "RTO Shield" wordmark (inline SVG)
│   ├── motion.jsx           Reveal (fade and rise), CountUp (animated figure)
│   ├── charts.jsx           LineChart, BarList, Ring, Heatmap, FactorBars
│   ├── AppShell.jsx         Sidebar / mobile nav, PageHeader, Panel
│   └── common/              Loading, ErrorState, EmptyState, MetricCard
├── data/sample.js           Sample dataset figures. Imported ONLY by Landing.jsx and Auth.jsx.
└── pages/
    ├── Landing.jsx          Public marketing page
    ├── Auth.jsx             Login and Signup (shared frame)
    ├── Dashboard.jsx        Real merchant data
    └── ComingSoon.jsx       M7b placeholders
```

### Design tokens

Every colour is a Tailwind v4 theme token, so classes such as `bg-chocolate`, `text-gain` and
`border-rule` exist. Each semantic colour has a single meaning:

| Token | Hex | Meaning |
|---|---|---|
| `chocolate` | `#382218` | Primary interface: buttons, active navigation, dark panels |
| `caramel` | `#b77b45` | Brand accent |
| `paper` / `sheet` / `beige` | `#f4efe4` / `#fbf8f1` / `#ece3d2` | Page, cards, soft surfaces |
| `ink` / `graphite` | `#2b1b14` / `#5a564e` | Body text / secondary text |
| `gain` | `#0e6b4f` | Money recovered or saved. Nothing else. |
| `loss` | `#b42318` | Money lost, very high risk. Nothing else. |
| `caution` | `#8a5a0b` | Medium and high risk |

`shadow-emboss`, `shadow-lift` and `inset-shadow-deboss` give cards and tracks a subtle raised or
pressed edge.

## 4. Authentication flow

### Backend endpoints

| Method | Path | Auth | Body | Response |
|---|---|---|---|---|
| POST | `/api/auth/signup/` | none, 10/hour per IP | `business_name, name, email, password` | 201 `{access, refresh, user}` |
| POST | `/api/auth/login/` | none, 30/hour per IP | `email` (or username), `password` | 200 `{access, refresh, user}`; 401 on bad credentials |
| POST | `/api/auth/refresh/` | none | `refresh` | 200 `{access}` |
| GET | `/api/auth/me/` | required | — | `{name, email, merchant}` |

`user` is always `{name, email, merchant}`. Password hashes and staff flags are never returned.

- **Sign up** creates the merchant and its first user in one transaction. Business names and emails are
  unique without regard to case. Passwords go through Django's validators, so `12345678` is rejected as
  "too common" and "entirely numeric".
- **Log in** accepts an email or a plain username in the same field. Accounts made in Django admin, such
  as `uploader`, can log in. The frontend labels the field "Email or username".
- **Access tokens** last 30 minutes and **refresh tokens** last 7 days.
- **Other clients:** API calls accept JWT first, then the Django session (admin in the same browser), then
  HTTP Basic (Postman). The frontend only ever sends `Bearer` tokens.

### Frontend

1. **Login and signup** call `open()` in `lib/api.js`, which sends no token. The response is saved to
   `localStorage` under `rto-shield-session` as `{access, refresh, user}`.
2. **Every other call** goes through `api()`, which attaches `Authorization: Bearer <access>`.
3. **On a 401,** `api()` asks `/api/auth/refresh/` for a new access token and retries the original
   request **once**. When several requests expire together (the dashboard loads eight), they share one
   refresh call.
4. **If the refresh fails** or the retry returns 401 again, the session is cleared and the browser goes
   to `/login`. There is no loop.
5. **Protected pages:** `RequireAuth` wraps `/app`. A visitor without a session is sent to `/login`, and
   after logging in they go back to the page they asked for (only `/app...` paths are accepted).
6. **Log out** clears the stored session and returns to the landing page.
7. **What is never exposed:** tokens are never logged, rendered or put in URLs.

## 5. Dashboard data sources

All figures come from the API. None are hardcoded. Field names were checked against the backend source.

| Dashboard element | Endpoint | Fields used |
|---|---|---|
| Header period and shipments | `/api/metrics/monthly/`, `/api/metrics/overview/` | `month` (first, last), `total_shipments` |
| Recoverable from couriers | `/api/audit/summary/` | `total_recoverable_inr`, `billing_findings + cod_findings`, `total_courier_billed_inr` |
| Spent on returned parcels | `/api/metrics/overview/` | `rto_courier_cost_inr`, `rto` |
| RTO rate (+ COD / Prepaid) | overview, `/api/metrics/rto/?by=payment_mode` | `rto_rate_pct`; per row `payment_mode`, `rto_rate_pct` |
| Delivered | overview | `delivered_rate_pct`, `delivered`, `total_shipments` |
| Orders | overview | `total_orders`, `cancelled_orders` |
| Delivered revenue | overview | `delivered_revenue_inr`, `rto_order_value_inr` |
| On-time delivery | overview | `on_time_pct`, `avg_delivery_days` |
| COD share | overview | `cod_share_pct` |
| RTO rate by month | `/api/metrics/monthly/` | `month`, `rto_rate_pct` (null leaves a gap) |
| Needs attention | audit summary, `/api/customers/segments/`, `/api/metrics/delivery/?by=courier` | `by_kind[kind=cod_not_remitted / weight_inflated]`, segment `Repeat returner`, lowest `on_time_pct` |
| Where the claim comes from | audit summary | `by_kind[].label`, `by_kind[].claim_inr` |
| RTO rate by zone | `/api/metrics/rto/?by=zone` | `zone`, `rto_rate_pct` (worst shown in red) |
| Customers by segment | `/api/customers/segments/` | `segment`, `customers` |
| Courier performance | `/api/metrics/delivery/?by=courier` + `/api/metrics/rto/?by=courier` | `courier`, `shipments`, `on_time_pct`, `first_attempt_delivery_pct`, `avg_delivery_days`, `avg_billed_per_shipment_inr`; RTO joined on `courier` |

### Differences from the original roadmap sketch

- Audit `by_kind` rows carry `label`, not `meaning`.
- `month` is `"YYYY-MM"`. The UI formats it as `Jan 24` or `Jan 2024`.
- Many rates can be `null`: monthly rates when no shipments have an outcome, and courier on-time and
  first-attempt rates when nothing is known. Every formatter shows `–` for these, never `NaN`.
- Staff users with no merchant get **403** from every metrics endpoint. The dashboard shows the backend's
  message and suggests logging in with a merchant account.

### Verified against the seeded merchant (`uploader`)

16,000 orders, 15,370 shipments, 81.8% delivered, 17.9% RTO (COD 34.7%, Prepaid 3.2%), ₹12,30,968
spent on returns, ₹2.09 Cr delivered revenue, 73.4% on time, 3.2 days average, ₹2,29,005 recoverable
from 1,773 findings. The worst courier by RTO is C3 at 22.8%.

## 6. Empty states

- **New merchant, no shipments** (`total_shipments == 0`): the dashboard shows "Welcome, *business
  name*" and an upload checklist (orders and shipments required; invoices and rate card, and COD
  statements, optional). It has a button to `/app/uploads`. It says plainly that uploading from the
  browser arrives in M7b. No metrics or charts are drawn.
- **Partial data:**
  - **No invoices:** "Recoverable" shows ₹0 with "Upload courier invoices to run the audit", and the
    claim chart shows a note instead of bars.
  - **Empty lists:** each panel shows a short sentence in place of the chart (no zones, no segments, no
    couriers).
  - **Nothing flagged:** the "Needs attention" panel says so.
- **Load failure:** an error panel with the reason and a "Try again" button.

## 7. Placeholder pages (M7b)

`/app/risk`, `/app/customers`, `/app/couriers`, `/app/rto`, `/app/audit`, `/app/uploads` and
`/app/reports` show the page title, one sentence about what the page will do, and that the detailed
interface is part of M7b. Where the backend API already exists, the page says so. Reports has no API
yet. These pages have no fake controls.

## 8. Responsive behaviour and accessibility

- **Desktop (≥1024px):** a sticky left sidebar with main and data navigation, the merchant's name, the
  user's email and Log out.
- **Phone width:** a single scrolling row of navigation links (all eight pages) with Log out at the top.
  Tables and the heatmap scroll inside their own panels. The page itself never scrolls sideways. This was
  checked at 390px.
- **Forms:** every input has a `<label>`, the right `autocomplete` value, and its error message linked by
  `aria-describedby`.
- **Keyboard:** focus outlines are visible, and there is a "Skip to content" link in the app.
- **Charts:** each chart has an `aria-label` description, and `CountUp` gives screen readers the final
  value.
- **Reduced motion:** figures appear at their final value, bars and lines appear fully drawn, the
  landing ticker stops, and smooth scrolling is off.

## 9. Running locally

```powershell
# terminal 1
cd "D:\claude workshop\logistics\logis\backend"
.venv\Scripts\python manage.py runserver

# terminal 2
cd "D:\claude workshop\logistics\logis\frontend"
Copy-Item .env.example .env      # first time only; VITE_API_URL=http://127.0.0.1:8000
npm install                      # first time only
npm run dev
```

Open http://localhost:5173.

If the frontend is served from a different address, add it to the backend's `CORS_ALLOWED_ORIGINS`
environment variable (comma-separated).

## 10. Build verification

```powershell
cd frontend
npm run build
```

Result at the end of M7a: 469 modules, no errors or warnings, about 480 kB of JavaScript (155 kB gzipped)
and 31 kB of CSS.

The backend suite is 61 tests: 55 from M0–M6 plus 6 in `accounts/test_accounts.py`.

## 11. Known limitations

- **Tokens are stored in `localStorage`.** This is the simplest approach and common for dashboards, but
  any script injected into the page (an XSS bug or a malicious dependency) could read them. The stronger
  design is to keep the refresh token in an http-only, `SameSite` cookie and the access token only in
  memory.
- **Log out does not revoke tokens.** Refresh tokens are not blacklisted, so a copied refresh token
  stays valid until it expires (7 days).
- **There is no email verification or password reset.** Anyone can register with any address. Sign-up
  is limited to 10 attempts an hour per IP and login to 30.
- **Rate limits are per process.** The counters live in Django's default in-memory cache, so they are
  not shared between server processes.
- **`SECRET_KEY` is still hardcoded** in `settings.py`, and it signs the JWTs. It must come from the
  environment before deployment.
- **Uploading from the browser is not built yet (M7b).** Data still arrives through the existing upload
  API.
- **Courier names can show as codes** (C1, C2, C3) when the uploaded shipment file used codes.
