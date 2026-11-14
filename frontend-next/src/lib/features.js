// What a merchant can use right now, decided only from the counts and model state that
// GET /api/workspace/status/ returns. This file is the single source of truth for those rules:
// pages, the sidebar and onboarding all read from featuresFor(). A metric being zero never decides it.

// The ingestion engine's real dataset types (backend ingestion SPECS). Nothing else is offered.
export const UPLOAD_TYPES = ["orders", "shipments", "pincode_zones", "rate_card", "invoices", "remittances"];
export const uploadLink = (type) => `/app/uploads?type=${type}`;
export const DEFAULT_UPLOAD_TYPE = "orders";
// ?type= value -> the dataset to select. Exact ids only; anything else (or nothing) means orders.
export const uploadTypeFrom = (value) => (UPLOAD_TYPES.includes(value) ? value : DEFAULT_UPLOAD_TYPE);

const has = (n) => Number(n) > 0;

function needs(title, description, actionLabel, type, tag) {
  return { status: "needs-data", title, description, actionLabel, to: type ? uploadLink(type) : null, tag };
}

function available(title, extra = {}) {
  return { status: "available", title, ...extra };
}

function sentenceList(items) {
  return items.length < 2 ? items.join("") : `${items.slice(0, -1).join(", ")} and ${items[items.length - 1]}`;
}

// How risk scores are produced. Rules are always available; only "ready" means a trained model.
export function riskMode(model) {
  const state = ["ready", "none", "insufficient_data", "stale"].includes(model?.state) ? model.state : "none";
  const reason = model?.reason || "";
  const modes = {
    ready: { headline: "Scored by your trained model", explanation: reason },
    none: { headline: "Scored by rules", explanation: reason },
    insufficient_data: {
      headline: "Scored by rules: not enough history to train a model yet",
      explanation: `${reason} Until then, orders are scored with transparent rules, not a trained model.`.trim(),
    },
    stale: { headline: "Scored by rules: the model needs retraining", explanation: reason },
  };
  return { state, usesRules: state !== "ready", trainedAt: state === "ready" ? model?.trained_at ?? null : null, ...modes[state] };
}

export function featuresFor(counts = {}, model = null) {
  const c = counts || {};
  const outcomes = has(c.shipments_with_outcome);
  const shipmentsWithoutOutcome = has(c.shipments) && !outcomes;

  const auditMissing = [
    [c.invoice_lines, "courier invoices", "invoices"],
    [c.rate_cards, "a rate card", "rate_card"],
    [c.shipments, "shipments", "shipments"],
  ].filter(([n]) => !has(n));

  const cod = !has(c.shipments)
    ? needs("COD reconciliation", "Import shipments and your COD remittance statements to check the cash each courier collected against what it paid back.", "Import shipments", "shipments")
    : !has(c.cod_shipments)
      ? needs("COD reconciliation", "None of your imported shipments are cash on delivery, so there is no COD cash to reconcile yet.", null, null)
      : !has(c.remittances)
        ? needs("COD reconciliation", "Import your COD remittance statements to check the cash each courier paid back for delivered COD parcels.", "Import COD remittances", "remittances")
        : available("COD reconciliation");

  const mode = riskMode(model);

  return {
    orders: has(c.orders)
      ? available("Orders overview")
      : needs("Orders overview", "Import your orders export to see order volume, value and customers.", "Import orders", "orders", "Needs orders"),
    customers: has(c.customers)
      ? available("Customers")
      : needs("Customers", "Customers appear as soon as your orders export is imported.", "Import orders", "orders", "Needs orders"),
    rto: outcomes
      ? available("RTO analytics")
      : needs("RTO analytics", shipmentsWithoutOutcome
        ? "Your shipments are loaded, but none has a final outcome (delivered or returned) yet. Return rates appear once outcomes are in."
        : "Import your shipment report to see which parcels were delivered and which came back.", "Import shipments", "shipments", "Needs shipments"),
    couriers: outcomes
      ? available("Couriers")
      : needs("Couriers", shipmentsWithoutOutcome
        ? "Your shipments are loaded, but none has a final outcome yet. Courier performance appears once deliveries and returns are recorded."
        : "Import your shipment report to compare how each courier delivers.", "Import shipments", "shipments", "Needs shipments"),
    audit: auditMissing.length
      ? needs("Billing audit", `Import ${sentenceList(auditMissing.map(([, name]) => name))} to check what your couriers billed.`,
        `Import ${auditMissing[0][1].replace(/^a /, "")}`, auditMissing[0][2], "Needs files")
      : available("Billing audit", {
        note: has(c.pincode_zones) ? null
          : "Pincode zones are not imported, so weight, zone and fee charges can't be priced yet. Duplicate bills and bills for parcels you never shipped are still caught.",
        noteAction: has(c.pincode_zones) ? null : { label: "Import pincode zones", to: uploadLink("pincode_zones") },
      }),
    cod,
    risk: available("Order risk checker", { tag: mode.usesRules ? "Rules" : null, mode }),
    // The Reports page asks the server which of the five reports this workspace can build; it only needs some data to open.
    reports: has(c.orders) || has(c.shipments)
      ? available("Reports")
      : needs("Reports", "Reports are built from your own data. Import your orders to start.", "Import orders", "orders", "Needs orders"),
  };
}

// Onboarding progress. Core steps are orders and shipment outcomes; everything else is optional.
export function stagesFor(counts = {}) {
  const c = counts || {};
  const done = [has(c.orders), has(c.shipments_with_outcome)];
  const next = done.indexOf(false);
  const status = (i) => (done[i] ? "completed" : i === next ? "next" : "pending");
  return {
    coreDone: done.filter(Boolean).length,
    coreTotal: done.length,
    started: status(0),
    deliveries: status(1),
    zones: has(c.pincode_zones),
    deeper: { invoices: has(c.invoice_lines), rateCard: has(c.rate_cards), remittances: has(c.remittances) },
  };
}
