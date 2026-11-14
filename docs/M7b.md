# M7b: the five workspace pages, plus demo fixes

Read this whole file before doing anything.

## Rules

- Copy the 15 files in `_incoming_m7b/frontend-next/` over the same paths in `frontend-next/`. Copy them
  byte for byte. Do not reformat, rename, restyle, "improve" or merge them by hand.
- 7 files are new and 8 replace existing files. The 8 were edited from the current versions in
  `frontend-next/`, so nothing of yours is lost. If any of those 8 has changed since 14 Nov 2026 19:15 IST,
  stop and show me the diff instead of overwriting.
- No backend changes. No new packages. Do not run `npm install`.
- Do not touch `frontend/`, `frontend-m7a-backup/`, `_incoming/` or `backend/`.
- If a step fails, stop and show me the exact error. Do not work around it.
- Do not commit or push. I will do that after checking.

## Files

New:
- `src/components/parts.jsx`            shared pieces: errors, stat tiles, chips, sortable headings, pager
- `src/components/ThresholdSlider.jsx`  the COD cut-off slider, used by the demo and the risk page
- `src/pages/Risk.jsx`                  order risk checker
- `src/pages/Customers.jsx`             customer intelligence
- `src/pages/Couriers.jsx`              courier analytics
- `src/pages/Rto.jsx`                   RTO analytics
- `src/pages/Audit.jsx`                 billing audit and COD reconciliation

Replaced:
- `src/App.jsx`                          routes the five pages
- `src/components/FeatureAvailability.jsx`  FeaturePage now renders the page itself; adds FeatureNotes
- `src/pages/ComingSoon.jsx`             only Reports uses it now
- `src/lib/format.js`                    adds `signedInr` and `day`
- `src/index.css`                        adds `.field` and `.no-scrollbar`
- `src/demo/DemoLayout.jsx`              one sticky block: slim banner plus section links
- `src/demo/DemoDashboard.jsx`           slider instead of the table, legend, duplicate card removed
- `src/data/sample.js`                   "Address parts 0" reads "Address detail: almost none"

## Steps

1. Copy the files.
2. In `frontend-next/` run `npm run build`. It must finish with no errors. The chunk-size warning is fine.
3. Run `node src/lib/features.test.mjs`. It must pass.
4. Run these and paste the output in your report:
   - `grep -rl "lib/api\|useApi\|useWorkspace" src/demo src/components/parts.jsx src/components/ThresholdSlider.jsx`
     Expected: no output.
   - `grep -rl "data/sample" src`
     Expected: only `src/pages/Landing.jsx` and `src/demo/DemoDashboard.jsx`.
5. Save this file as `docs/M7b.md`.

## What each page calls (all endpoints already exist)

| Page | Endpoints |
|---|---|
| Risk | POST `/api/risk/score/`, POST `/api/ml/train/`, GET `/api/ml/model/`, GET `/api/ml/economics/` |
| Customers | GET `/api/customers/`, `/api/customers/segments/`, `/api/customers/lookup/` |
| Couriers | GET `/api/metrics/delivery/?by=courier`, `/api/metrics/rto/?by=courier`, `/api/audit/summary/`, `/api/metrics/cod/` |
| RTO | GET `/api/metrics/overview/`, `/api/metrics/monthly/`, `/api/metrics/rto/?by=...` |
| Audit | GET `/api/audit/summary/`, `/api/audit/findings/`, `/api/audit/disputes.csv`, `/api/metrics/cod/`, POST `/api/audit/run/` |

## Checks for me to do by hand (list them in your report, do not tick them yourself)

With the full-data merchant:
1. Risk: score a COD order, then a prepaid one. The ring, reasons and action change. Two results appear under "Checked this visit".
2. Risk: type letters in Order value. A red message appears under the field, no crash.
3. Risk: change the margin to 50 and press Recalculate. The slider's numbers change.
4. Customers: click a segment card, search a name, open a customer, go to the next page.
5. Couriers: pick "Owed to you", click a courier, press "See every disputed charge". The audit opens filtered to that courier.
6. Audit: click a kind, click a row, download the claim file and open it in Excel.
7. RTO: switch to Pincode and to "Courier charges on returns". The table sorts and pages.
8. Dashboard still looks as before.

With a brand-new merchant:
9. Customers, Couriers, RTO and Billing audit each show their "Needs data" panel, not zeros.
10. Risk works and says "Scored by rules". "Train the model" answers that there is not enough history.

Demo and phone:
11. `/demo`: slim gold banner and section links stay while scrolling; Economics is a slider; no "Strongest risk factors" card.
12. Phone width (390 px): no sideways scroll on any of the five pages or the demo.

## Report format

1. Files copied (count new, count replaced).
2. Build output, test output, the two grep outputs.
3. Anything that differed from this document.
4. The 12 manual checks, unticked.

Suggested commit message, for me to use later:
`M7b: risk checker, customers, couriers, RTO analytics and billing audit pages; demo fixes`
