from decimal import Decimal
from math import ceil

import numpy as np
import pandas as pd
from django.db import transaction

from core.models import CodRemittance, InvoiceLine, Order, PincodeZone, Shipment

from .models import ShipmentLedger

IST = "Asia/Kolkata"


def frame(qs, *fields):
    return pd.DataFrame(list(qs.values(*fields)), columns=list(fields))


def dec(x):
    return Decimal(str(round(float(x), 2)))


def none_if_nan(x):
    return None if pd.isna(x) else x


@transaction.atomic
def rebuild_ledger(merchant):
    """Delete and rewrite this merchant's ledger: one row per shipment, never more."""
    ShipmentLedger.objects.for_merchant(merchant).delete()

    # A. shipments
    df = frame(
        Shipment.objects.for_merchant(merchant),
        "id", "awb_number", "order_id", "courier_id", "courier__name", "pickup_ts",
        "pkg_weight_g", "pkg_length_cm", "pkg_breadth_cm", "pkg_height_cm",
        "promised_delivery_date", "delivery_attempts", "last_ndr_reason", "final_status", "delivered_ts",
    )
    if df.empty:
        return {"rows": 0}

    # B. orders, with how many earlier orders the same customer had placed
    orders = frame(
        Order.objects.for_merchant(merchant),
        "id", "external_id", "customer_id", "customer__pincode", "order_ts",
        "payment_mode", "sales_channel", "order_value",
    )
    orders = orders.sort_values("order_ts", kind="stable")
    orders["prior_orders"] = orders.groupby("customer_id").cumcount()
    orders = orders.rename(columns={"id": "order_id", "external_id": "order_ref", "customer__pincode": "pincode"})
    df = df.merge(orders, on="order_id", how="left", validate="many_to_one")

    # C. destination zone (zone is per merchant, so this is unique by pincode)
    zones = frame(PincodeZone.objects.for_merchant(merchant), "pincode", "city", "state", "zone", "city_tier")
    df = df.merge(zones, on="pincode", how="left", validate="many_to_one")

    # D. invoices and remittances: aggregate to one row per AWB first, so joins never multiply rows
    inv = frame(InvoiceLine.objects.for_merchant(merchant), "awb_number", "total_billed_inr")
    inv["total_billed_inr"] = inv["total_billed_inr"].astype(float)
    inv = inv.groupby("awb_number", as_index=False).agg(
        invoice_lines=("total_billed_inr", "size"), billed_total_inr=("total_billed_inr", "sum"))
    rem = frame(CodRemittance.objects.for_merchant(merchant), "awb_number", "amount_remitted_inr")
    rem["amount_remitted_inr"] = rem["amount_remitted_inr"].astype(float)
    rem = rem.groupby("awb_number", as_index=False).agg(cod_remitted_inr=("amount_remitted_inr", "sum"))
    df = df.merge(inv, on="awb_number", how="left", validate="many_to_one")
    df = df.merge(rem, on="awb_number", how="left", validate="many_to_one")
    df["invoice_lines"] = df["invoice_lines"].fillna(0).astype(int)
    df["billed_total_inr"] = df["billed_total_inr"].fillna(0.0)
    df["cod_remitted_inr"] = df["cod_remitted_inr"].fillna(0.0)

    # E. order date and time, in IST
    order_ts = pd.to_datetime(df["order_ts"], utc=True).dt.tz_convert(IST)
    df["order_date"] = order_ts.dt.date
    df["order_month"] = order_ts.dt.to_period("M").dt.to_timestamp().dt.date
    df["order_hour"] = order_ts.dt.hour

    # F. parcel weights
    vol = (df["pkg_length_cm"].astype(float) * df["pkg_breadth_cm"].astype(float)
           * df["pkg_height_cm"].astype(float) / 5000 * 1000)
    df["vol_weight_g"] = vol.round().astype(int)
    df["chargeable_weight_g"] = np.maximum(df["pkg_weight_g"].astype(int), df["vol_weight_g"])
    df["weight_slabs"] = df["chargeable_weight_g"].map(lambda g: max(1, ceil(g / 500)))

    # G. outcome
    df["is_delivered"] = df["final_status"] == "Delivered"
    df["is_rto"] = df["final_status"] == "RTO Delivered"
    df["is_lost"] = df["final_status"] == "Lost"
    df["first_attempt_delivered"] = df["is_delivered"] & (df["delivery_attempts"] <= 1)

    # H. timing, in IST
    pickup_ts = pd.to_datetime(df["pickup_ts"], utc=True).dt.tz_convert(IST)
    delivered_ts = pd.to_datetime(df["delivered_ts"], utc=True).dt.tz_convert(IST)
    df["days_order_to_pickup"] = (pickup_ts - order_ts).dt.total_seconds() / 86400
    df["days_pickup_to_delivery"] = (delivered_ts - pickup_ts).dt.total_seconds() / 86400
    delivered_date = delivered_ts.dt.date

    def on_time(i):
        promised = df.at[i, "promised_delivery_date"]
        if not df.at[i, "is_delivered"] or pd.isna(promised) or pd.isna(delivered_ts.at[i]):
            return None
        return bool(delivered_date.at[i] <= promised)

    df["on_time"] = [on_time(i) for i in df.index]

    # I. COD money the courier owes us: only for delivered COD parcels
    df["cod_due_inr"] = np.where(
        (df["payment_mode"] == "COD") & df["is_delivered"], df["order_value"].astype(float), 0.0)

    # J. write
    rows = []
    for r in df.itertuples(index=False):
        city_tier = none_if_nan(r.city_tier)
        days_to_delivery = none_if_nan(r.days_pickup_to_delivery)
        rows.append(ShipmentLedger(
            merchant=merchant,
            shipment_id=int(r.id),
            awb_number=r.awb_number,
            order_ref=r.order_ref,
            customer_id=int(r.customer_id),
            courier_id=int(r.courier_id),
            courier_name=r.courier__name,
            order_ts=r.order_ts,
            order_date=r.order_date,
            order_month=r.order_month,
            order_hour=int(r.order_hour),
            payment_mode=r.payment_mode,
            sales_channel=r.sales_channel or "",
            order_value=dec(r.order_value),
            prior_orders=int(r.prior_orders),
            is_first_order=int(r.prior_orders) == 0,
            pincode=r.pincode,
            city=none_if_nan(r.city) or "",
            state=none_if_nan(r.state) or "",
            zone=none_if_nan(r.zone) or "",
            city_tier=None if city_tier is None else int(city_tier),
            pkg_weight_g=int(r.pkg_weight_g),
            vol_weight_g=int(r.vol_weight_g),
            chargeable_weight_g=int(r.chargeable_weight_g),
            weight_slabs=int(r.weight_slabs),
            final_status=r.final_status,
            is_delivered=bool(r.is_delivered),
            is_rto=bool(r.is_rto),
            is_lost=bool(r.is_lost),
            delivery_attempts=int(r.delivery_attempts),
            first_attempt_delivered=bool(r.first_attempt_delivered),
            last_ndr_reason=r.last_ndr_reason or "",
            pickup_ts=r.pickup_ts,
            delivered_ts=none_if_nan(r.delivered_ts),
            promised_delivery_date=none_if_nan(r.promised_delivery_date),
            days_order_to_pickup=dec(r.days_order_to_pickup),
            days_pickup_to_delivery=None if days_to_delivery is None else dec(days_to_delivery),
            on_time=r.on_time,
            invoice_lines=int(r.invoice_lines),
            billed_total_inr=dec(r.billed_total_inr),
            cod_due_inr=dec(r.cod_due_inr),
            cod_remitted_inr=dec(r.cod_remitted_inr),
        ))
    ShipmentLedger.objects.bulk_create(rows, batch_size=2000)

    return {
        "rows": len(rows),
        "without_zone": int(df["zone"].isna().sum()),
        "without_invoice": int((df["invoice_lines"] == 0).sum()),
    }
