# logis

**Find the money your couriers owe you.** logis is a web app for Indian online sellers. It audits courier bills against the agreed rate card, tracks every rupee of cash-on-delivery money, and predicts which new orders are likely to be returned before they ship.

**Live app:** https://logis-rto.netlify.app
**Demo with sample data, no sign-up:** https://logis-rto.netlify.app/demo

> The API runs on a free server that sleeps when idle. If the site has been quiet, the first login can take up to a minute while it wakes up.

![Landing page](docs/screenshots/landing.png)

## The problem

Small Indian e-commerce sellers lose money in three places they rarely check:

- **Returns (RTO).** When a customer refuses a cash-on-delivery parcel, it comes back and the seller pays the courier both ways. Across Indian e-commerce, COD orders come back far more often than prepaid ones.
- **Courier bills.** Invoices arrive as spreadsheets with thousands of lines. Billed weights, zones and duplicate lines go unchecked because nobody has time to check them by hand.
- **COD cash.** Couriers collect the cash at the door and pay it over later in batches. A parcel paid short, or never paid, is easy to miss.

The seller already has every file needed to find these losses. logis joins them together and does the checking.

## What it does

| Module | What the seller gets |
|---|---|
| Uploads | Drag in CSV or Excel exports. Columns are matched automatically, every row is checked, and bad rows are reported with the reason. |
| Dashboard | Money owed, returns and courier performance on one screen. Every total opens into the parcels behind it. |
| Billing audit | Each invoice line priced again from the rate card. Overcharges are listed with the reason, and a claim file per courier can be downloaded. |
| COD reconciliation | Every delivered COD parcel matched to the remittance that paid for it. Unpaid and short-paid parcels are flagged. |
| RTO analytics | Return rate by month, payment mode, zone, courier, channel, city tier, hour and pincode. |
| Risk checker | Score a new order before it ships: probability of return, the reasons, a recommended action and a confidence level. |
| Customers | Customers grouped by behaviour (loyal, repeat returner and others), with a full record for each one. |
| Reports | Five PDF reports, each with an introduction, the analysis and a conclusion written from the seller's own numbers. |

![Dashboard](docs/screenshots/dashboard.png)

## Results on the sample store

The demo uses a synthetic store, "Pune Threads": 16,000 orders from January 2024 to December 2025, 15,370 shipments across three couriers and five delivery zones, 15,447 invoice lines and 4,623 COD remittance lines. The data generator planted known billing errors and COD gaps so the audit could be tested against an answer key.

| Finding | Number |
|---|---|
| Return rate | 17.9% (2,754 parcels) |
| COD against prepaid return rate | 34.7% against 3.2% |
| Recoverable from couriers | ₹2,29,005 across 1,773 disputed charges |
| Of which, invoice overcharges | ₹1,61,752, which is 4.1% of everything billed |
| Of which, COD cash not paid over | ₹67,253 on 89 delivered parcels |
| Audit accuracy | All 1,684 planted billing errors and all 89 COD gaps found; totals match the answer key to within 3 paise |
| Loyal customers | 19.1% of customers bring 46.3% of delivered revenue |
| Return-risk model | 42.6% of all returns sit in the riskiest 10% of orders |

## How it works

```mermaid
flowchart LR
    A[CSV and Excel uploads] --> B[Ingestion: match columns, validate, load]
    B --> C[(PostgreSQL)]
    C --> D[Shipment ledger: one row per parcel]
    D --> E[Billing and COD audit]
    D --> F[Metrics API]
    D --> G[Return-risk model]
    E --> H[React app]
    F --> H
    G --> H
    E --> I[PDF reports]
    F --> I
```

- **Multi-tenant from the start.** Every business table carries the merchant it belongs to, and every query is filtered by it. One seller can never see another's data, and tests check this.
- **The ledger.** Orders, shipments, invoices and remittances are joined into one row per parcel. It is rebuilt after every upload, so every page reads the same numbers.
- **Privacy.** Customer phone numbers are stored only as salted SHA-256 hashes. Raw numbers are never saved or shown.

### Billing audit

For each invoice line the correct charge is worked out from the seller's rate card:

- **Chargeable weight:** the higher of actual weight and volumetric weight (L × B × H / 5000), rounded up to 500 g steps.
- **Freight:** the rate card price for that weight in the parcel's zone, plus a COD fee if the parcel was COD, plus the return charge if it came back.
- **Total:** everything plus 18% GST.

A line is disputed only when it is more than ₹1 above the correct charge and the reason can be named. The reasons are inflated weight, wrong zone, duplicate line, return charge on a delivered parcel, COD fee on a prepaid parcel, or other overcharge. A delivered COD parcel with no remittance 21 days after delivery counts as unpaid.

### Return-risk model

The model answers one question: will this order come back?

- **Only order-time information.** Features are things known when the order is placed: payment mode, order value, hour, zone, city tier, sales channel, how detailed the address is, and the customer's and pincode's history so far.
- **No peeking at the future.** History features are built with an as-of join that only looks at parcels finished before the order was placed. Data is split by date (70% train, 15% validation, 15% test), never at random.
- **Two models compared.** Logistic regression and LightGBM were both trained. LightGBM would be used only if it beat logistic regression by 0.005 AUC on the validation set. It didn't, so the simpler and easier-to-explain model was kept.
- **Calibrated.** Scores are calibrated on the validation set, so a score of 30% means about 30 in 100 such orders come back.
- **One code path.** The same feature function is used for training and for live scoring, so the two can't drift apart.
- **Explained.** Each score lists its strongest reasons, worked out from the model's coefficients.

| Model | Test AUC | Test Brier score |
|---|---|---|
| Logistic regression (used) | 0.842 | 0.079 |
| LightGBM | 0.825 | 0.082 |

The test set is the last 2,298 parcels (24 Oct to 31 Dec 2025), which the model never saw during training.

**Turning a score into a decision.** The Risk checker includes a cost model. Refusing COD to risky orders avoids returns, but some good buyers walk away. With a 30% margin, an average return cost of ₹442 and 6 in 10 flagged buyers agreeing to pay online, the best cut-off on the test period was 35%. That would have avoided 100 returns, flagged 95 good buyers, and come out ₹25,522 ahead. The seller can change the margin and see the best cut-off move.

![Risk checker](docs/screenshots/risk.png)

### Reports

Five PDF reports are built on demand with ReportLab, with charts drawn in Matplotlib: Business summary, Returns report, Courier scorecard, Billing audit and claims, and Customer report. Each one opens with an introduction to the data behind it and ends with findings and next steps written from that seller's numbers. A finding only appears when the data supports it.

![A report page](docs/screenshots/report.png)

## Tech stack

| Layer | Tools |
|---|---|
| Backend | Python 3.13, Django 6, Django REST Framework, JWT login |
| Data and ML | pandas, NumPy, scikit-learn, LightGBM |
| Reports | ReportLab, Matplotlib |
| Database | PostgreSQL (Supabase in production) |
| File storage | Supabase Storage through its S3 API |
| Frontend | React 19, Vite, Tailwind CSS 4, React Router, Motion, Anime.js |
| Hosting | Render (API), Netlify (frontend) |
| Tests | pytest and pytest-django, 85 tests |

## Repository layout

```
backend/
  core/        tenants, users and the business tables
  ingestion/   upload, column matching, validation, loading, removing data
  ledger/      one row per parcel, and the metrics API
  audit/       billing and COD audit, claim file
  ml/          features, training, calibration, scoring
  customers/   customer segments and profiles
  accounts/    sign-up and login
  reports/     the five PDF reports
frontend-next/ the React app
docs/          module specs and screenshots
```

## Run it locally

You need Python 3.13, Node 20.19 or newer, and PostgreSQL.

**Backend**

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate          # on macOS or Linux: source .venv/bin/activate
pip install -r requirements.txt
```

Create `backend/.env`:

```
SECRET_KEY=any-long-random-string
DEBUG=True
DATABASE_URL=postgres://postgres:password@localhost:5432/logis
PHONE_HASH_SALT=any-random-string
```

Then:

```bash
python manage.py migrate
python manage.py runserver
pytest -q
```

**Frontend**

```bash
cd frontend-next
npm ci
echo VITE_API_URL=http://127.0.0.1:8000 > .env
npm run dev
```

The app opens at http://localhost:5174. Sign up, then upload your files on the Uploads page.

The sample data files are not in this repository, because no merchant data goes into Git. The live demo uses them.


## Author

Nikhil Mahale, final-year Computer Engineering student, D. Y. Patil College of Engineering, Pune.
[GitHub](https://github.com/nikhilhere7) · [LinkedIn](https://www.linkedin.com/in/nikhil-mahale-293987271)
