"""Order-time features for the RTO model.

Every feature here is known when the order is placed. Nothing about the courier, pickup, delivery,
billing or COD remittance is used as a feature, and a customer's or pincode's past outcomes count only
once they were resolved strictly before the order being scored.
"""
import re

import numpy as np
import pandas as pd

from core.models import Customer, Order, Shipment
from ledger.build import frame
from ledger.models import ShipmentLedger

IST = "Asia/Kolkata"
SMOOTHING = 20
LANDMARK = re.compile(r"\b(?:near|opp|opposite|behind|beside|next to|above|below)\b", re.IGNORECASE)

NUMERIC = [
    "is_cod", "order_value", "order_hour", "is_late_night",
    "is_weekend", "prior_orders", "is_first_order",
    "cust_prior_rto", "cust_prior_delivered",
    "pin_prior_parcels", "pin_prior_rto_rate", "city_tier",
    "addr_len", "addr_words", "addr_commas",
    "addr_has_number", "addr_has_landmark", "addr_is_lowercase",
]

CATEGORICAL = ["zone", "sales_channel"]

LABELS = {
    "is_cod": "Cash on delivery",
    "order_value": "Order value",
    "order_hour": "Hour of order",
    "is_late_night": "Placed late at night",
    "is_weekend": "Placed on a weekend",
    "prior_orders": "Customer's earlier orders",
    "is_first_order": "First-time customer",
    "cust_prior_rto": "Customer's past returns",
    "cust_prior_delivered": "Customer's past deliveries",
    "pin_prior_parcels": "Parcels sent to this pincode before",
    "pin_prior_rto_rate": "Pincode's past RTO rate",
    "city_tier": "City tier",
    "addr_len": "Address length",
    "addr_words": "Words in address",
    "addr_commas": "Address parts",
    "addr_has_number": "House / flat number given",
    "addr_has_landmark": "Landmark given",
    "addr_is_lowercase": "Address typed carelessly",
    "zone": "Delivery zone",
    "sales_channel": "Sales channel",
}

TARGET = "is_rto"
LATE_NIGHT_HOURS = {22, 23, 0, 1, 2, 3, 4, 5}
UNRESOLVED_AFTER = pd.Timedelta(days=10)


def address_features(text):
    """A Series of addresses -> one row of address features per address, same index."""
    s = text.fillna("").astype(str)
    return pd.DataFrame({
        "addr_len": s.str.len(),
        "addr_words": s.str.split().str.len(),
        "addr_commas": s.str.count(","),
        "addr_has_number": s.str.contains(r"\d").astype(int),
        "addr_has_landmark": s.str.contains(LANDMARK).astype(int),
        "addr_is_lowercase": ((s == s.str.lower()) & (s.str.len() > 0)).astype(int),
    }, index=text.index)


def _utc(series):
    """Any mix of aware, naive (read as UTC, like ledger.build) or missing values -> one comparable dtype."""
    return pd.to_datetime(series, utc=True).astype("datetime64[ns, UTC]")


def _history_before(orders, events, by):
    """For each order: how many outcomes for the same `by` value were resolved strictly before
    order_ts, and how many of those were RTO. Returns (n, rto_n) aligned to orders.index."""
    zero = pd.DataFrame({"n": 0.0, "rto_n": 0.0}, index=orders.index)
    if orders.empty or events.empty:
        return zero

    def keyed(df):
        k = df[by]
        return df[k.notna() & (k.astype(str).str.strip() != "")]

    ev = keyed(events)[[by, "resolved_ts", TARGET]].copy()
    ev["resolved_ts"] = _utc(ev["resolved_ts"])
    ev = ev.dropna(subset=["resolved_ts"]).sort_values("resolved_ts", kind="stable")
    if ev.empty:
        return zero
    ev[by] = ev[by].astype(str)
    ev["n"] = ev.groupby(by).cumcount() + 1.0
    ev["rto_n"] = ev.groupby(by)[TARGET].cumsum().astype(float)

    od = keyed(orders)[[by, "order_ts"]].copy()
    od[by] = od[by].astype(str)
    od["order_ts"] = _utc(od["order_ts"])
    od["_row"] = od.index
    od = od.dropna(subset=["order_ts"]).sort_values("order_ts", kind="stable")

    hit = pd.merge_asof(od, ev[[by, "resolved_ts", "n", "rto_n"]], left_on="order_ts", right_on="resolved_ts",
                        by=by, direction="backward", allow_exact_matches=False)
    hit = hit.set_index("_row")[["n", "rto_n"]].fillna(0.0)
    zero.loc[hit.index, ["n", "rto_n"]] = hit.values
    return zero


def time_aware_history(d):
    """Add customer and pincode history to d. Rows with a resolved_ts are outcomes; every row is scored."""
    d = d.copy()
    events = d[d["resolved_ts"].notna()] if "resolved_ts" in d else d.iloc[0:0]

    # merchant-wide return rate of outcomes known before each order; 0.2 until the first one is known
    everyone = _history_before(d.assign(_all="all"), events.assign(_all="all"), "_all")
    base_rate = (everyone.rto_n / everyone.n.replace(0, np.nan)).fillna(0.2).values

    cust = _history_before(d, events, "customer_id")
    d["cust_prior_rto"] = cust["rto_n"]
    d["cust_prior_delivered"] = cust["n"] - cust["rto_n"]

    pin = _history_before(d, events, "pincode")
    d["pin_prior_parcels"] = pin["n"]
    d["pin_prior_rto_rate"] = (pin.rto_n + SMOOTHING * base_rate) / (pin.n + SMOOTHING)
    return d


def training_frame(merchant):
    """One row per non-lost shipment, oldest order first, with order-time features and the is_rto target."""
    ledger = frame(
        ShipmentLedger.objects.for_merchant(merchant).exclude(is_lost=True),
        "shipment_id", "awb_number", "customer_id", "order_ts", "order_hour", "payment_mode", "sales_channel",
        "order_value", "prior_orders", "is_first_order", "pincode", "zone", "city_tier",
        "is_rto", "pickup_ts", "delivered_ts", "billed_total_inr",
    )
    # billed_total_inr is kept for the training economics (average RTO cost); it is never a feature
    columns = ["shipment_id", "awb_number", "customer_id", "order_ts", "resolved_ts", TARGET, "billed_total_inr",
               *NUMERIC, *CATEGORICAL]
    if ledger.empty:
        return pd.DataFrame(columns=columns)

    # rto_initiated_ts lives on Shipment, not on the ledger
    rto = frame(Shipment.objects.for_merchant(merchant).filter(id__in=list(ledger["shipment_id"])),
                "id", "rto_initiated_ts").rename(columns={"id": "shipment_id"})
    address = frame(Customer.objects.for_merchant(merchant), "id", "address_line").rename(
        columns={"id": "customer_id"})
    d = (ledger.merge(rto, on="shipment_id", how="left", validate="one_to_one")
               .merge(address, on="customer_id", how="left", validate="many_to_one"))

    # when the outcome became known: delivered, else return started, else assume 10 days after pickup
    d["resolved_ts"] = (
        _utc(d["delivered_ts"])
        .fillna(_utc(d["rto_initiated_ts"]))
        .fillna(_utc(d["pickup_ts"]) + UNRESOLVED_AFTER)
    )

    d["order_ts"] = _utc(d["order_ts"])
    local = d["order_ts"].dt.tz_convert(IST)
    d["is_cod"] = (d["payment_mode"] == Order.PaymentMode.COD).astype(int)
    d["order_value"] = d["order_value"].astype(float)
    d["is_late_night"] = d["order_hour"].isin(LATE_NIGHT_HOURS).astype(int)
    d["is_weekend"] = (local.dt.day_of_week >= 5).astype(int)
    d["is_first_order"] = d["is_first_order"].astype(int)
    d["city_tier"] = d.city_tier.fillna(2)
    d["billed_total_inr"] = d["billed_total_inr"].astype(float)
    d[TARGET] = d[TARGET].astype(int)
    d = pd.concat([d, address_features(d["address_line"])], axis=1)

    d = d.sort_values(["order_ts", "shipment_id"], kind="stable").reset_index(drop=True)
    d = time_aware_history(d)
    return d[columns]


def design_matrix(d, columns=None):
    """Numeric features as floats plus one-hot categories. Pass the training columns to line up new rows."""
    numeric = d[NUMERIC].astype(float)
    cats = d[CATEGORICAL].astype(object).where(d[CATEGORICAL].notna(), "").astype(str)
    onehot = pd.get_dummies(cats, prefix=CATEGORICAL, prefix_sep="=", dtype=float)
    onehot = onehot[[c for c in onehot.columns if not str(c).endswith("=")]]   # blank category -> no column
    X = pd.concat([numeric, onehot], axis=1)
    if columns is not None:
        X = X.reindex(columns=list(columns), fill_value=0.0)
    return X
