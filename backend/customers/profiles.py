"""Customer Intelligence: what one merchant knows about each of its own customers.
Everything is worked out from the ledger, so there is no new table to keep in step."""
import numpy as np
import pandas as pd
from django.db.models import Count, Max, Q

from core.models import Customer, Order
from ledger.build import frame
from ledger.models import ShipmentLedger
from ml.score import repeat_returner

LOYAL_MIN_PARCELS, LOYAL_MAX_RATE = 4, 0.15
RECENT_ORDERS = 10

SEGMENTS = {
    "Repeat returner": "Returned at least 2 parcels and at least 30% of everything sent",
    "Returned first order": "Only one parcel so far, and it came back",
    "Loyal": "4 or more parcels, almost all accepted",
    "Regular": "Several parcels with a mixed or short record",
    "New": "One parcel so far, accepted",
    "No history": "Has ordered, but no parcel was delivered or returned yet (cancelled, lost or in transit)",
}

ADVICE = {
    "Repeat returner": "Ask for prepaid, or confirm by phone before every COD dispatch.",
    "Returned first order": "Confirm the next COD order by phone before dispatch.",
    "Loyal": "Safe to ship. A good candidate for offers and early access.",
    "Regular": "No special handling needed.",
    "New": "No special handling needed.",
    "No history": "No outcome on record yet. Treat as a first-time customer.",
}


def local_date(ts):
    """A timestamp's calendar date in IST. Naive values are read as UTC, as everywhere else in the project."""
    ts = pd.Timestamp(ts)
    if ts.tzinfo is None:
        ts = ts.tz_localize("UTC")
    return ts.tz_convert("Asia/Kolkata").date().isoformat()


def segment_of(parcels, returned):
    """Vectorised: two Series in, one Series of segment names out. First matching rule wins.
    parcels counts delivered + returned parcels (lost ones are not parcels here), so a customer's
    delivered count is parcels - returned. "Repeat returner" is decided by the Risk Checker's own
    policy rule, so the two can never drift apart."""
    rate = returned / parcels.replace(0, np.nan)
    returner = pd.Series([repeat_returner(pd.Series({"cust_prior_rto": r, "cust_prior_delivered": p - r}))
                          for p, r in zip(parcels, returned)], index=parcels.index, dtype=bool)
    return pd.Series(np.select(
        [parcels == 0,
         returner,
         (parcels == 1) & (returned == 1),
         parcels == 1,
         (parcels >= LOYAL_MIN_PARCELS) & (rate < LOYAL_MAX_RATE)],
        ["No history", "Repeat returner", "Returned first order", "New", "Loyal"], default="Regular"),
        index=parcels.index)


def customer_table(merchant):
    """One row per customer who has placed an order. Cancelled orders count as orders; parcels are
    ledger rows that were delivered or returned (lost parcels are left out, as in M5)."""
    orders = frame(Order.objects.for_merchant(merchant).values("customer_id").annotate(
        orders=Count("id"), cancelled=Count("id", filter=Q(status=Order.Status.CANCELLED)),
        last_order=Max("order_ts")),
        "customer_id", "orders", "cancelled", "last_order")
    if orders.empty:
        return orders
    led = frame(ShipmentLedger.objects.for_merchant(merchant).filter(is_lost=False),
                "customer_id", "is_rto", "is_delivered", "payment_mode", "order_value")
    led["order_value"] = led.order_value.astype(float)
    led["is_rto"] = led.is_rto.astype(bool)
    led["is_delivered"] = led.is_delivered.astype(bool)
    led["cod"] = led.payment_mode == Order.PaymentMode.COD
    led["cod_returned"] = led.cod & led.is_rto
    led["delivered_value"] = led.order_value.where(led.is_delivered, 0.0)
    led["returned_value"] = led.order_value.where(led.is_rto, 0.0)
    g = led.groupby("customer_id").agg(
        parcels=("is_rto", "size"), returned=("is_rto", "sum"), delivered=("is_delivered", "sum"),
        cod_parcels=("cod", "sum"), cod_returned=("cod_returned", "sum"),
        delivered_value=("delivered_value", "sum"), returned_value=("returned_value", "sum")).reset_index()
    who = frame(Customer.objects.for_merchant(merchant), "id", "external_id", "name", "pincode").rename(
        columns={"id": "customer_id", "external_id": "customer_ref"})
    t = orders.merge(g, on="customer_id", how="left").merge(who, on="customer_id", how="left")
    counts = ["parcels", "returned", "delivered", "cod_parcels", "cod_returned"]
    t[counts] = t[counts].fillna(0).astype(int)
    t[["delivered_value", "returned_value"]] = t[["delivered_value", "returned_value"]].fillna(0.0).astype(float)
    t["rto_rate_pct"] = (100 * t.returned / t.parcels.replace(0, np.nan)).round(1)
    t["segment"] = segment_of(t.parcels, t.returned)
    t["payment_preference"] = np.select(
        [t.parcels == 0, t.cod_parcels == t.parcels, t.cod_parcels == 0], ["Unknown", "COD only", "Prepaid only"],
        default="Mixed")
    return t


def as_row(r):
    return {
        "customer_id": r.customer_ref, "name": r["name"], "pincode": r.pincode, "segment": r.segment,
        "orders": int(r.orders), "cancelled_orders": int(r.cancelled), "parcels": int(r.parcels),
        "delivered": int(r.delivered), "returned": int(r.returned),
        "rto_rate_pct": None if pd.isna(r.rto_rate_pct) else float(r.rto_rate_pct),
        "payment_preference": str(r.payment_preference), "delivered_value_inr": round(float(r.delivered_value), 2),
        "returned_value_inr": round(float(r.returned_value), 2),
        "last_order": local_date(r.last_order) if pd.notna(r.last_order) else None,
    }


def segment_summary(merchant):
    t = customer_table(merchant)
    if t.empty:
        return []
    total_value = t.delivered_value.sum() or 1
    out = []
    for name, why in SEGMENTS.items():
        s = t[t.segment == name]
        if s.empty:
            continue
        parcels, cod = int(s.parcels.sum()), int(s.cod_parcels.sum())
        out.append({
            "segment": name, "meaning": why, "customers": int(len(s)),
            "customer_share_pct": round(100 * len(s) / len(t), 1), "parcels": parcels,
            "rto_rate_pct": round(100 * float(s.returned.sum()) / parcels, 1) if parcels else None,
            "cod_share_pct": round(100 * cod / parcels, 1) if parcels else None,
            "cod_rto_rate_pct": round(100 * float(s.cod_returned.sum()) / cod, 1) if cod else None,
            "delivered_value_inr": round(float(s.delivered_value.sum())),
            "revenue_share_pct": round(100 * float(s.delivered_value.sum()) / total_value, 1),
        })
    return out


def _payment_behaviour(led):
    by_mode = {m["payment_mode"]: m for m in led.filter(is_lost=False).values("payment_mode").annotate(
        parcels=Count("id"), returned=Count("id", filter=Q(is_rto=True)))}

    def mode(name):
        m = by_mode.get(name, {"parcels": 0, "returned": 0})
        return {"parcels": m["parcels"], "returned": m["returned"],
                "rto_rate_pct": round(100 * m["returned"] / m["parcels"], 1) if m["parcels"] else None}

    return {"COD": mode(Order.PaymentMode.COD), "Prepaid": mode(Order.PaymentMode.PREPAID)}


def profile(merchant, customer):
    """Everything about one customer: totals, how they pay, and their 10 most recent orders.
    `customer` must already belong to `merchant`; every query below is scoped to the merchant as well."""
    t = customer_table(merchant)
    row = t[t.customer_id == customer.id] if not t.empty else t
    led = ShipmentLedger.objects.for_merchant(merchant).filter(customer=customer)
    if row.empty:                                   # never ordered: same shape, all zeros
        base = {"customer_id": customer.external_id, "name": customer.name, "pincode": customer.pincode,
                "segment": "No history", "orders": 0, "cancelled_orders": 0, "parcels": 0, "delivered": 0,
                "returned": 0, "rto_rate_pct": None, "payment_preference": "Unknown", "delivered_value_inr": 0.0,
                "returned_value_inr": 0.0, "last_order": None}
    else:
        base = as_row(row.iloc[0])

    outcome = {x["order_ref"]: x for x in led.values("order_ref", "final_status", "courier_name", "last_ndr_reason")}
    recent = []
    for o in Order.objects.for_merchant(merchant).filter(customer=customer).order_by("-order_ts", "-id")[:RECENT_ORDERS]:
        s = outcome.get(o.external_id, {})
        recent.append({"order_id": o.external_id, "date": local_date(o.order_ts),
                       "order_value_inr": float(o.order_value), "payment_mode": o.payment_mode,
                       "outcome": s.get("final_status") or (
                           "Cancelled" if o.status == Order.Status.CANCELLED else "In transit"),
                       "courier": s.get("courier_name", ""), "ndr_reason": s.get("last_ndr_reason", "")})
    return {**base, "segment_meaning": SEGMENTS[base["segment"]], "advice": ADVICE[base["segment"]],
            "payment_behaviour": _payment_behaviour(led), "recent_orders": recent}
