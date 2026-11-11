"""Write validated rows into the canonical tables. Re-uploading the same file updates, never duplicates."""
from decimal import Decimal
from zoneinfo import ZoneInfo

import pandas as pd

from core.models import Courier, Customer, Order, Shipment

IST = ZoneInfo("Asia/Kolkata")
BATCH = 2000


def money(x):
    return Decimal(str(round(float(x), 2)))


def text(x):
    return "" if pd.isna(x) else str(x)


def ts(x):
    return None if pd.isna(x) else pd.Timestamp(x).to_pydatetime().replace(tzinfo=IST)


def day(x):
    return None if pd.isna(x) else pd.Timestamp(x).date()


def load_orders(df, merchant):
    # one customer row per key, taking details from their most recent order
    latest = df.sort_values("order_ts").drop_duplicates("customer_key", keep="last")
    rows = [Customer(merchant=merchant, external_id=r.customer_key, name=text(r.customer_name), pincode=r.pincode,
                     address_line=text(r.address_line), phone_hash=text(r.phone_hash).strip())
            for r in latest.itertuples()]
    # a file without a phone must not wipe a hash we already hold, so blank-hash rows leave phone_hash alone
    upsert = dict(batch_size=BATCH, update_conflicts=True, unique_fields=["merchant", "external_id"])
    Customer.objects.bulk_create([c for c in rows if c.phone_hash], **upsert,
                                 update_fields=["name", "pincode", "address_line", "phone_hash"])
    Customer.objects.bulk_create([c for c in rows if not c.phone_hash], **upsert,
                                 update_fields=["name", "pincode", "address_line"])
    customer = dict(Customer.objects.for_merchant(merchant).values_list("external_id", "id"))

    before = Order.objects.for_merchant(merchant).count()
    Order.objects.bulk_create(
        [Order(merchant=merchant, external_id=r.order_id, customer_id=customer[r.customer_key],
               order_ts=ts(r.order_ts), sales_channel=text(r.sales_channel), payment_mode=r.payment_mode,
               gross_value=money(r.gross_value), discount_inr=money(r.discount_inr),
               shipping_fee_inr=money(r.shipping_fee_inr), order_value=money(r.order_value), status=r.status)
         for r in df.itertuples()],
        batch_size=BATCH, update_conflicts=True, unique_fields=["merchant", "external_id"],
        update_fields=["customer", "order_ts", "sales_channel", "payment_mode", "gross_value", "discount_inr",
                       "shipping_fee_inr", "order_value", "status"])
    created = Order.objects.for_merchant(merchant).count() - before
    return {"created": created, "updated": len(df) - created, "customers_touched": len(latest)}


def _courier_ids(names, merchant):
    """Match the courier text in the file to a Courier by code or name; create it if it's new."""
    existing = {}
    for c in Courier.objects.for_merchant(merchant):
        existing[c.code.lower()] = c.id
        existing[c.name.lower()] = c.id
    out = {}
    for name in names:
        key = name.lower()
        if key not in existing:
            existing[key] = Courier.objects.create(merchant=merchant, code=name[:20], name=name[:80]).id
        out[name] = existing[key]
    return out


def load_shipments(df, merchant):
    order = dict(Order.objects.for_merchant(merchant).values_list("external_id", "id"))
    courier = _courier_ids(df.courier.unique(), merchant)
    before = Shipment.objects.for_merchant(merchant).count()
    Shipment.objects.bulk_create(
        [Shipment(merchant=merchant, awb_number=r.awb_number, order_id=order[r.order_id],
                  courier_id=courier[r.courier], pickup_ts=ts(r.pickup_ts), pkg_weight_g=int(round(r.pkg_weight_g)),
                  pkg_length_cm=money(r.pkg_length_cm), pkg_breadth_cm=money(r.pkg_breadth_cm),
                  pkg_height_cm=money(r.pkg_height_cm), promised_delivery_date=day(r.promised_delivery_date),
                  delivery_attempts=int(r.delivery_attempts), last_ndr_reason=text(r.last_ndr_reason),
                  final_status=r.final_status, delivered_ts=ts(r.delivered_ts),
                  rto_initiated_ts=ts(r.rto_initiated_ts), rto_received_ts=ts(r.rto_received_ts),
                  rto_condition=text(r.rto_condition)) for r in df.itertuples()],
        batch_size=BATCH, update_conflicts=True, unique_fields=["merchant", "awb_number"],
        update_fields=["order", "courier", "pickup_ts", "pkg_weight_g", "pkg_length_cm", "pkg_breadth_cm",
                       "pkg_height_cm", "promised_delivery_date", "delivery_attempts", "last_ndr_reason",
                       "final_status", "delivered_ts", "rto_initiated_ts", "rto_received_ts", "rto_condition"])
    created = Shipment.objects.for_merchant(merchant).count() - before
    return {"created": created, "updated": len(df) - created}


LOADERS = {"orders": load_orders, "shipments": load_shipments}
