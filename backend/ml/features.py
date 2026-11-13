"""Order-time features for the RTO model.

Every feature here is known when the order is placed. Nothing about the courier, pickup, delivery,
billing or COD remittance is used as a feature, and a customer's or pincode's past outcomes count only
once they were resolved strictly before the order being scored.
"""
import re

import numpy as np
import pandas as pd

from core.models import Customer, Shipment
from ledger.build import frame
from ledger.models import ShipmentLedger

IST = "Asia/Kolkata"
SMOOTHING = 20              # a pincode needs about this many parcels before its own RTO rate is trusted
LANDMARK = re.compile(r"\b(?:near|opp|opposite|behind|beside|next to|above|below)\b", re.IGNORECASE)

CUSTOMER_SMOOTHING = 3      # same idea for one customer's own return rate
REPEAT_CAP = 5              # a 6th order tells us little more than the 5th did

NUMERIC = [
    "is_cod",
    "cod_first_order",
    "order_value",
    "order_hour",
    "is_late_night",
    "is_weekend",
    "repeat_orders",
    "cust_rto_rate",
    "pin_prior_rto_rate",
    "city_tier",
    "addr_commas",
    "addr_has_number",
    "addr_has_landmark",
    "addr_is_lowercase",
]

CATEGORICAL = ["zone", "sales_channel"]

LABELS = {
    "is_cod": "Cash on delivery",
    "cod_first_order": "First-time customer paying COD",
    "order_value": "Order value",
    "order_hour": "Hour of order",
    "is_late_night": "Placed late at night",
    "is_weekend": "Placed on a weekend",
    "repeat_orders": "Customer's earlier orders",
    "cust_rto_rate": "Customer's own return rate",
    "pin_prior_rto_rate": "Pincode's past RTO rate",
    "city_tier": "City tier",
    "addr_commas": "Address parts",
    "addr_has_number": "House / flat number given",
    "addr_has_landmark": "Landmark given",
    "addr_is_lowercase": "Address typed carelessly",
    "zone": "Delivery zone",
    "sales_channel": "Sales channel",
}

TARGET = "is_rto"
UNRESOLVED_AFTER = pd.Timedelta(days=10)

# history and helper columns kept next to the features: derive() needs them, and live scoring will
# rebuild exactly these from the merchant's history as it stands now
HISTORY = ["prior_orders", "cust_prior_rto", "cust_prior_delivered", "base_rto_rate", "pin_prior_parcels"]


def address_features(text):
    """Works on a Series of address strings."""
    s = text.fillna("").astype(str)
    return pd.DataFrame({
        "addr_len": s.str.len().clip(upper=100),
        "addr_commas": s.str.count(","),
        "addr_has_number": s.str.contains(r"\d").astype(int),
        "addr_has_landmark": s.str.contains(LANDMARK).astype(int),
        "addr_is_lowercase": (
            (s == s.str.lower()) & (s.str.len() > 0)
        ).astype(int),
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
    d["base_rto_rate"] = base_rate

    cust = _history_before(d, events, "customer_id")
    d["cust_prior_rto"] = cust["rto_n"]
    d["cust_prior_delivered"] = cust["n"] - cust["rto_n"]

    pin = _history_before(d, events, "pincode")
    d["pin_prior_parcels"] = pin["n"]
    d["pin_prior_rto_rate"] = (pin.rto_n + SMOOTHING * base_rate) / (pin.n + SMOOTHING)
    return d


def derive(d):
    """Raw order-time facts and historical counts -> model features.

    Training and live scoring must both use this function.
    It must never use parcel outcomes or post-order information.
    """
    d = d.copy()

    d["is_cod"] = (d.payment_mode == "COD").astype(int)
    d["is_first_order"] = (d.prior_orders == 0).astype(int)
    d["cod_first_order"] = d.is_cod * d.is_first_order

    d["repeat_orders"] = d.prior_orders.clip(upper=REPEAT_CAP)

    d["is_late_night"] = (
        (d.order_hour >= 23) | (d.order_hour <= 3)
    ).astype(int)

    seen = d.cust_prior_rto + d.cust_prior_delivered

    d["cust_rto_rate"] = (
        d.cust_prior_rto + CUSTOMER_SMOOTHING * d.base_rto_rate
    ) / (seen + CUSTOMER_SMOOTHING)

    d["city_tier"] = d.city_tier.fillna(2)

    return pd.concat(
        [d, address_features(d.address)],
        axis=1,
    )


def training_frame(merchant):
    """One row per non-lost shipment, oldest order first, with order-time features and the is_rto target."""
    ledger = frame(
        ShipmentLedger.objects.for_merchant(merchant).exclude(is_lost=True),
        "shipment_id", "awb_number", "customer_id", "order_ts", "order_hour", "payment_mode", "sales_channel",
        "order_value", "prior_orders", "pincode", "zone", "city_tier",
        "is_rto", "pickup_ts", "delivered_ts", "billed_total_inr",
    )
    # billed_total_inr is kept for the training economics (average RTO cost); it is never a feature
    columns = ["shipment_id", "awb_number", "customer_id", "pincode", "order_ts", "resolved_ts", TARGET,
               "billed_total_inr", *HISTORY, *NUMERIC, *CATEGORICAL]
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
    d["is_weekend"] = (d["order_ts"].dt.tz_convert(IST).dt.day_of_week >= 5).astype(int)
    d["order_value"] = d["order_value"].astype(float)
    d["billed_total_inr"] = d["billed_total_inr"].astype(float)
    d["address"] = d["address_line"]
    d[TARGET] = d[TARGET].astype(int)

    d = d.sort_values(["order_ts", "shipment_id"], kind="stable").reset_index(drop=True)
    d = derive(time_aware_history(d))      # the same derive() live scoring uses
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
