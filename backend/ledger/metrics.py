from datetime import date
from zoneinfo import ZoneInfo

from django.db.models import Avg, Count, F, Q, Sum
from django.db.models.functions import TruncMonth

from core.models import Order

from .models import ShipmentLedger

IST = ZoneInfo("Asia/Kolkata")

# Public dimension name -> ShipmentLedger field. Only these names ever reach the ORM.
DIMENSIONS = {
    "payment_mode": "payment_mode",
    "courier": "courier_name",
    "zone": "zone",
    "city": "city",
    "state": "state",
    "pincode": "pincode",
    "sales_channel": "sales_channel",
    "first_order": "is_first_order",
    "order_hour": "order_hour",
    "month": "order_month",
    "city_tier": "city_tier",
}

DELIVERED = Q(is_delivered=True)
RTO = Q(is_rto=True)
COD = Q(payment_mode=Order.PaymentMode.COD)


def ledger(merchant):
    return ShipmentLedger.objects.for_merchant(merchant)


def pct(numerator, denominator):
    if not denominator:
        return None
    return round(100 * (numerator or 0) / denominator, 1)


def num(value):
    return None if value is None else round(float(value), 2)


def field_for(dim):
    if dim not in DIMENSIONS:
        raise ValueError(f"Unknown dimension '{dim}'. Use one of: {', '.join(DIMENSIONS)}.")
    return DIMENSIONS[dim]


def label(value):
    return value.isoformat() if isinstance(value, date) else value


def overview(merchant):
    orders = Order.objects.for_merchant(merchant).aggregate(
        total=Count("id"), cancelled=Count("id", filter=Q(status=Order.Status.CANCELLED)))
    s = ledger(merchant).aggregate(
        shipments=Count("id"),
        delivered=Count("id", filter=DELIVERED),
        rto=Count("id", filter=RTO),
        lost=Count("id", filter=Q(is_lost=True)),
        cod=Count("id", filter=COD),
        delivered_revenue=Sum("order_value", filter=DELIVERED),
        rto_order_value=Sum("order_value", filter=RTO),
        rto_courier_cost=Sum("billed_total_inr", filter=RTO),
        billed=Sum("billed_total_inr"),
        on_time_yes=Count("id", filter=Q(on_time=True)),
        on_time_known=Count("id", filter=Q(on_time__isnull=False)),
        avg_delivery_days=Avg("days_pickup_to_delivery"),
    )
    return {
        "total_orders": orders["total"],
        "cancelled_orders": orders["cancelled"],
        "total_shipments": s["shipments"],
        "delivered": s["delivered"],
        "delivered_rate_pct": pct(s["delivered"], s["shipments"]),
        "rto": s["rto"],
        "rto_rate_pct": pct(s["rto"], s["shipments"]),
        "lost": s["lost"],
        "cod_share_pct": pct(s["cod"], s["shipments"]),
        "delivered_revenue_inr": num(s["delivered_revenue"] or 0),
        "rto_order_value_inr": num(s["rto_order_value"] or 0),
        "rto_courier_cost_inr": num(s["rto_courier_cost"] or 0),
        "total_courier_billed_inr": num(s["billed"] or 0),
        "on_time_pct": pct(s["on_time_yes"], s["on_time_known"]),
        "avg_delivery_days": num(s["avg_delivery_days"]),
    }


def monthly(merchant):
    """Orders come from Order (cancelled excluded), shipments from the ledger; both by IST month."""
    orders = (Order.objects.for_merchant(merchant).exclude(status=Order.Status.CANCELLED)
              .annotate(month=TruncMonth("order_ts", tzinfo=IST)).values("month").order_by()
              .annotate(orders=Count("id"), order_value=Sum("order_value")))
    shipments = (ledger(merchant).values("order_month").order_by()
                 .annotate(shipments=Count("id"),
                           delivered=Count("id", filter=DELIVERED),
                           rto=Count("id", filter=RTO),
                           delivered_revenue=Sum("order_value", filter=DELIVERED),
                           rto_courier_cost=Sum("billed_total_inr", filter=RTO)))

    months = {}

    def row(month):
        return months.setdefault(month, {
            "month": month.strftime("%Y-%m"), "orders": 0, "order_value_inr": 0.0, "shipments": 0,
            "delivered": 0, "rto": 0, "rto_rate_pct": None, "delivered_revenue_inr": 0.0,
            "rto_courier_cost_inr": 0.0})

    for o in orders:
        r = row(o["month"].date() if hasattr(o["month"], "date") else o["month"])
        r["orders"] = o["orders"]
        r["order_value_inr"] = num(o["order_value"] or 0)
    for s in shipments:
        r = row(s["order_month"])
        r["shipments"] = s["shipments"]
        r["delivered"] = s["delivered"]
        r["rto"] = s["rto"]
        r["rto_rate_pct"] = pct(s["rto"], s["shipments"])
        r["delivered_revenue_inr"] = num(s["delivered_revenue"] or 0)
        r["rto_courier_cost_inr"] = num(s["rto_courier_cost"] or 0)
    return [months[m] for m in sorted(months)]


def rto_by(merchant, dim, min_shipments=1):
    field = field_for(dim)
    groups = (ledger(merchant).values(field).order_by()
              .annotate(shipments=Count("id"),
                        rto=Count("id", filter=RTO),
                        cod=Count("id", filter=COD),
                        rto_courier_cost=Sum("billed_total_inr", filter=RTO))
              .filter(shipments__gte=min_shipments))
    rows = [{
        dim: label(g[field]),
        "shipments": g["shipments"],
        "rto": g["rto"],
        "rto_rate_pct": pct(g["rto"], g["shipments"]),
        "cod_share_pct": pct(g["cod"], g["shipments"]),
        "rto_courier_cost_inr": num(g["rto_courier_cost"] or 0),
    } for g in groups]
    rows.sort(key=lambda r: (-(r["rto_rate_pct"] or 0), -r["shipments"]))
    return rows


def delivery_by(merchant, dim):
    field = field_for(dim)
    groups = (ledger(merchant).values(field).order_by()
              .annotate(shipments=Count("id"),
                        delivered=Count("id", filter=DELIVERED),
                        on_time_yes=Count("id", filter=Q(on_time=True)),
                        on_time_known=Count("id", filter=Q(on_time__isnull=False)),
                        first_attempt=Count("id", filter=Q(first_attempt_delivered=True)),
                        avg_delivery_days=Avg("days_pickup_to_delivery"),
                        avg_days_order_to_pickup=Avg("days_order_to_pickup"),
                        billed=Sum("billed_total_inr")))
    rows = [{
        dim: label(g[field]),
        "shipments": g["shipments"],
        "delivered_rate_pct": pct(g["delivered"], g["shipments"]),
        "on_time_pct": pct(g["on_time_yes"], g["on_time_known"]),
        "first_attempt_delivery_pct": pct(g["first_attempt"], g["delivered"]),
        "avg_delivery_days": num(g["avg_delivery_days"]),
        "avg_days_order_to_pickup": num(g["avg_days_order_to_pickup"]),
        "avg_billed_per_shipment_inr": num((g["billed"] or 0) / g["shipments"]),
    } for g in groups]
    rows.sort(key=lambda r: (-r["shipments"], str(r[dim])))
    return rows


def cod_summary(merchant):
    """Delivered COD parcels per courier: what the courier owes us vs what it has paid."""
    groups = (ledger(merchant).filter(COD, DELIVERED).values("courier_id", "courier_name").order_by()
              .annotate(shipments=Count("id"),
                        due=Sum("cod_due_inr"),
                        remitted=Sum("cod_remitted_inr"),
                        unpaid=Count("id", filter=Q(cod_remitted_inr=0)),
                        short_paid=Count("id", filter=Q(cod_remitted_inr__gt=0,
                                                        cod_remitted_inr__lt=F("cod_due_inr")))))
    rows = [{
        "courier": g["courier_name"],
        "cod_delivered_shipments": g["shipments"],
        "cod_due_inr": num(g["due"] or 0),
        "cod_remitted_inr": num(g["remitted"] or 0),
        "gap_inr": num((g["due"] or 0) - (g["remitted"] or 0)),
        "not_remitted": g["unpaid"],
        "short_paid": g["short_paid"],
    } for g in groups]
    rows.sort(key=lambda r: r["courier"])
    return rows
