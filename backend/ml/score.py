"""Order Risk Checker: score orders that have not shipped yet.

Features are built exactly as in training (features.time_aware_history + features.derive), from the
merchant's history as it stood at each order's own order_ts. Nothing that happened after that moment
is used: not later orders, not outcomes learned later, not the scored order itself.
"""
import re

import numpy as np
import pandas as pd
from django.utils import timezone

from core.models import Customer, Order, PincodeZone, Shipment
from ingestion.validators import hash_phone
from ledger.build import frame
from ledger.models import ShipmentLedger

from .features import CATEGORICAL, IST, LABELS, TARGET, UNRESOLVED_AFTER, _utc, derive, design_matrix, \
    time_aware_history
from .train import RISK_BANDS, active_model, label_for, load_artifact, model_feature_compatible

BAND_NAMES = ["Low", "Medium", "High", "Very high"]
ACTIONS = {            # (band, is COD) -> what the merchant should do
    ("Low", True): "Ship as usual.",
    ("Low", False): "Ship as usual.",
    ("Medium", True): "Confirm the order on WhatsApp or by phone before dispatch.",
    ("Medium", False): "Ship as usual.",
    ("High", True): "Offer a prepaid discount or take a partial advance before dispatch.",
    ("High", False): "Confirm the delivery address before dispatch.",
    ("Very high", True): "Do not ship as COD. Ask the customer to pay online first.",
    ("Very high", False): "Call the customer to confirm the address and that they still want the order.",
}
ADDRESS_ACTION = " Ask for a complete address with house number and landmark."
COD_NOT_SERVICEABLE = "COD is not serviceable at this pincode. Ask the customer to pay online."
MIN_STRENGTH = 0.15    # factors weaker than this are noise to a merchant, so they are not shown
TOP_FACTORS = 5

PAYMENT_MODES = {"cod": "COD", "cash on delivery": "COD", "prepaid": "Prepaid", "paid": "Prepaid",
                 "online": "Prepaid", "upi": "Prepaid", "card": "Prepaid"}
SALES_CHANNELS = {c.lower(): c for c in ["Website", "WhatsApp", "Instagram Shop"]}
MOBILE = re.compile(r"[6-9]\d{9}")      # same rule ingestion uses before hashing a phone

_cache = {}            # {RiskModel id: Scorer}, one trained model kept loaded per process


# ---------------------------------------------------------------- inputs
def clean_order(o):
    """Normalise one order the way ingestion normalises uploads. Unknown channels pass through as-is
    (an unseen category scores as all zeros); an invalid phone is simply not used for matching."""
    o = dict(o)
    o["payment_mode"] = PAYMENT_MODES.get(str(o.get("payment_mode", "")).strip().lower(), o.get("payment_mode"))
    o["pincode"] = re.sub(r"\s", "", str(o.get("pincode", "")))
    channel = str(o.get("sales_channel") or "").strip()
    o["sales_channel"] = SALES_CHANNELS.get(channel.lower(), channel)
    digits = re.sub(r"\D", "", str(o.get("phone") or ""))[-10:]
    o["phone"] = digits if MOBILE.fullmatch(digits) else ""
    o["customer_id"] = str(o.get("customer_id") or "").strip()
    o["order_id"] = str(o.get("order_id") or "").strip()
    o["address"] = o.get("address") or ""
    o["order_ts"] = o.get("order_ts") or timezone.now()
    return o


def _customers(merchant, orders):
    """Each order's Customer pk (or None): by the merchant's own customer ID, else by hashed phone.
    Ingestion keys phone-only customers as "PH-" + the first 16 characters of the hash."""
    hashes = [hash_phone(o["phone"]) if o["phone"] else None for o in orders]
    ids = {o["customer_id"] for o in orders if o["customer_id"]}
    keys = ids | {"PH-" + h[:16] for h in hashes if h}
    found = Customer.objects.for_merchant(merchant).filter(external_id__in=keys) | \
        Customer.objects.for_merchant(merchant).filter(phone_hash__in=[h for h in hashes if h])
    by_key, by_hash = {}, {}
    for c in found:
        by_key[c.external_id] = c.id
        if c.phone_hash:
            by_hash[c.phone_hash] = c.id
    out = []
    for o, h in zip(orders, hashes):
        pk = by_key.get(o["customer_id"]) if o["customer_id"] else None
        if pk is None and h:
            pk = by_hash.get(h) or by_key.get("PH-" + h[:16])
        out.append(pk)
    return out


# ---------------------------------------------------------------- history as it stood at each order
def resolved_history(merchant):
    """Every non-lost parcel of this merchant with the moment its outcome became known: the same rule
    training_frame() uses (delivered, else return started, else 10 days after pickup)."""
    led = frame(ShipmentLedger.objects.for_merchant(merchant).exclude(is_lost=True),
                "shipment_id", "customer_id", "pincode", "order_ts", "is_rto", "delivered_ts", "pickup_ts")
    if led.empty:
        return pd.DataFrame(columns=["customer_id", "pincode", "order_ts", "resolved_ts", TARGET])
    rto = frame(Shipment.objects.for_merchant(merchant).filter(id__in=list(led["shipment_id"])),
                "id", "rto_initiated_ts").rename(columns={"id": "shipment_id"})
    led = led.merge(rto, on="shipment_id", how="left", validate="one_to_one")
    led["resolved_ts"] = (_utc(led["delivered_ts"]).fillna(_utc(led["rto_initiated_ts"]))
                          .fillna(_utc(led["pickup_ts"]) + UNRESOLVED_AFTER))
    led["order_ts"] = _utc(led["order_ts"])
    led[TARGET] = led[TARGET].astype(int)
    led["customer_id"] = led["customer_id"].astype(object)
    return led[["customer_id", "pincode", "order_ts", "resolved_ts", TARGET]]


def _prior_orders(merchant, d):
    """Orders this customer placed strictly before each order (cancelled ones too, as in training),
    never counting the scored order itself if it was already uploaded."""
    pks = [int(c) for c in d["customer_pk"].dropna().unique()]
    placed = pd.DataFrame(list(Order.objects.for_merchant(merchant).filter(customer_id__in=pks)
                               .values("customer_id", "external_id", "order_ts")),
                          columns=["customer_id", "external_id", "order_ts"])
    placed["order_ts"] = _utc(placed["order_ts"])
    counts = []
    for pk, ts, oid in zip(d["customer_pk"], d["order_ts"], d["order_id"]):
        if pk is None:
            counts.append(0)
            continue
        mine = placed[(placed.customer_id == pk) & (placed.order_ts < ts)]
        counts.append(int((mine.external_id != oid).sum()) if oid else len(mine))
    return counts


def build_features(merchant, orders):
    """orders: list of dicts (order_value, payment_mode, pincode required). One feature row per order,
    in the same order, with the same columns training uses plus the history behind them."""
    orders = [clean_order(o) for o in orders]
    d = pd.DataFrame(orders)
    d["customer_pk"] = pd.Series(_customers(merchant, orders), dtype=object)
    d["order_ts"] = _utc(d["order_ts"])
    d["order_value"] = d["order_value"].astype(float)
    when = d["order_ts"].dt.tz_convert(IST)
    d["order_hour"] = when.dt.hour
    d["is_weekend"] = (when.dt.day_of_week >= 5).astype(int)
    d["prior_orders"] = _prior_orders(merchant, d)

    zones = {z.pincode: z for z in PincodeZone.objects.for_merchant(merchant).filter(pincode__in=list(d.pincode))}
    d["zone"] = [zones[p].zone if p in zones else "" for p in d.pincode]
    d["city"] = [zones[p].city if p in zones else "" for p in d.pincode]
    d["city_tier"] = [zones[p].city_tier if p in zones else None for p in d.pincode]   # derive() fills 2
    d["cod_serviceable"] = [zones[p].cod_serviceable if p in zones else True for p in d.pincode]

    # the scored orders sit alongside the merchant's resolved parcels; time_aware_history then gives each
    # one exactly what a training row gets: outcomes known strictly before its own order_ts
    history = resolved_history(merchant)
    live = pd.DataFrame({"customer_id": d["customer_pk"], "pincode": d["pincode"], "order_ts": d["order_ts"],
                         "resolved_ts": pd.Series(pd.NaT, index=d.index, dtype="datetime64[ns, UTC]"),
                         TARGET: 0, "_live": True})
    both = pd.concat([history.assign(_live=False), live], ignore_index=True)
    known = time_aware_history(both)
    known = known[known["_live"].astype(bool)].reset_index(drop=True)
    for c in ["base_rto_rate", "cust_prior_rto", "cust_prior_delivered", "pin_prior_parcels", "pin_prior_rto_rate"]:
        d[c] = known[c].values
    return derive(d)          # the same function training uses


# ---------------------------------------------------------------- the model, when there is a current one
def scorer_for(merchant):
    """(Scorer, risk bands) for a current trained model, else (None, RISK_BANDS). A model trained on an
    older feature set is never loaded or scored; the merchant gets rule-based scores until retraining."""
    run = active_model(merchant)
    if run is None or not model_feature_compatible(run):
        return None, dict(RISK_BANDS)
    if run.id not in _cache:
        _cache.clear()
        _cache[run.id] = load_artifact(run)["scorer"]
    return _cache[run.id], run.metrics.get("risk_bands", dict(RISK_BANDS))


# ---------------------------------------------------------------- rule-based score for merchants with no model
RULES = [   # (label, test on a feature row, points in log-odds)
    ("Cash on delivery", lambda r: r.is_cod == 1, 1.9),
    ("First-time customer paying COD", lambda r: r.is_cod == 1 and r.is_first_order == 1, 0.7),
    ("Customer has returned parcels before", lambda r: r.cust_prior_rto >= 1, 0.8),
    ("Customer has accepted parcels before", lambda r: r.cust_prior_delivered >= 2, -0.9),
    ("Address has no house or flat number", lambda r: r.addr_has_number == 0, 0.5),
    ("Very short address", lambda r: r.addr_len < 20, 0.7),
    ("COD order placed late at night", lambda r: r.is_cod == 1 and r.is_late_night == 1, 0.5),
    ("High-value COD order", lambda r: r.is_cod == 1 and r.order_value > 2500, 0.4),
    ("Pincode has a poor delivery record", lambda r: r.pin_prior_parcels >= 30 and r.pin_prior_rto_rate > 0.30, 0.6),
]
RULES_BASE = -3.0


def rule_score(row):
    hits = [(label, pts) for label, test, pts in RULES if test(row)]
    z = RULES_BASE + sum(p for _, p in hits)
    factors = [{"factor": label, "value": "Yes", "effect": "raises risk" if pts > 0 else "lowers risk",
                "strength": round(abs(pts), 2)} for label, pts in sorted(hits, key=lambda h: -abs(h[1]))[:TOP_FACTORS]]
    return float(1 / (1 + np.exp(-z))), factors


# ---------------------------------------------------------------- turning numbers into words
def show(feature, row):
    v = row[feature]
    if feature == "is_cod":
        return "COD" if v else "Prepaid"
    if feature in ("cod_first_order", "is_late_night", "is_weekend", "addr_has_number", "addr_has_landmark",
                   "addr_is_lowercase"):
        return "Yes" if v else "No"
    if feature == "cust_rto_rate":
        return f"{int(row.cust_prior_rto)} returned of {int(row.cust_prior_rto + row.cust_prior_delivered)}"
    if feature == "repeat_orders":
        return str(int(row.prior_orders))
    if feature == "pin_prior_rto_rate":
        return f"{100 * v:.0f}%"
    if feature == "order_value":
        return f"Rs {v:,.0f}"
    if feature == "order_hour":
        return f"{int(v):02d}:00"
    return str(int(v))


def model_factors(contrib, row, top=TOP_FACTORS):
    """The strongest pushes on this order's risk, in words. One-hot columns ("zone=E") are only
    mentioned for the zone / channel this order actually has."""
    out = []
    for col in contrib.abs().sort_values(ascending=False).index:
        if abs(contrib[col]) < MIN_STRENGTH:
            break
        if "=" in col:
            base, value = col.split("=", 1)
            if base not in CATEGORICAL or row[base] != value:
                continue
            label = LABELS[base]
        else:
            label, value = label_for(col), show(col, row)
        out.append({"factor": label, "value": value, "effect": "raises risk" if contrib[col] > 0 else "lowers risk",
                    "strength": round(float(abs(contrib[col])), 2)})
        if len(out) == top:
            break
    return out


def band_for(p, bands):
    cuts = [bands["medium_from"], bands["high_from"], bands["very_high_from"]]
    return BAND_NAMES[sum(p >= c for c in cuts)]


def repeat_returner(row):
    """A customer with a record of sending parcels back. Checked separately from the model: a merchant
    should never be told to 'ship as usual' to someone who has returned a third of their orders."""
    seen = row.cust_prior_rto + row.cust_prior_delivered
    return bool(row.cust_prior_rto >= 2 and row.cust_prior_rto / seen >= 0.30)


def confidence_for(row):
    """How much of this merchant's own history stands behind the score."""
    pin, cust = int(row.pin_prior_parcels), int(row.prior_orders)
    level = "High" if pin >= 100 and cust >= 2 else "Medium" if pin >= 30 else "Low"
    return {"level": level, "pincode_parcels_seen": pin, "customer_orders_seen": cust}


def score_orders(merchant, orders):
    """Score a list of not-yet-shipped orders. Returns one result dict per order, in the same order."""
    f = build_features(merchant, orders)
    scorer, bands = scorer_for(merchant)
    if scorer is not None:
        X = design_matrix(f, scorer.columns)
        probs, contrib = scorer.predict_proba(X), scorer.contributions(X)
    results = []
    for i, row in f.iterrows():
        if scorer is not None:
            p, factors = float(probs[i]), model_factors(contrib.loc[i], row)
        else:
            p, factors = rule_score(row)
        band, cod, note = band_for(p, bands), bool(row.is_cod), ""
        if band == "Low" and cod and repeat_returner(row):
            band = "Medium"
            note = (f"Raised from Low by policy: this customer returned {int(row.cust_prior_rto)} of "
                    f"{int(row.cust_prior_rto + row.cust_prior_delivered)} earlier parcels.")
        action = ACTIONS[(band, cod)]
        if band != "Low" and row.addr_has_number == 0 and row.addr_len < 25:
            action += ADDRESS_ACTION
        if cod and not row.cod_serviceable:
            action = COD_NOT_SERVICEABLE
        results.append({
            "risk_probability": round(p, 3), "risk_pct": round(100 * p, 1), "risk_category": band,
            "contributing_factors": factors, "recommended_action": action, "policy_note": note,
            "confidence": confidence_for(row),
            "scored_by": f"model:{scorer.kind}" if scorer is not None else "rules",
            "customer": {"known": row.customer_pk is not None and not pd.isna(row.customer_pk),
                         "previous_orders": int(row.prior_orders),
                         "delivered": int(row.cust_prior_delivered), "returned": int(row.cust_prior_rto)},
            "destination": {"pincode": row.pincode, "city": row.city, "zone": row.zone,
                            "parcels_sent_before": int(row.pin_prior_parcels),
                            "past_rto_rate_pct": round(100 * float(row.pin_prior_rto_rate), 1)},
        })
    return results
