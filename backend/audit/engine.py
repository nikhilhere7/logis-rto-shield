from collections import Counter
from datetime import timedelta
from decimal import ROUND_HALF_UP, Decimal
from math import ceil
from zoneinfo import ZoneInfo

import pandas as pd
from django.db import transaction
from django.db.models import Max

from core.models import CodRemittance, InvoiceLine, Order, RateCard
from ledger.build import frame
from ledger.models import ShipmentLedger

from .models import AuditFinding

GST_RATE = 0.18
TOLERANCE_INR = 1.0
COD_GRACE_DAYS = 21

IST = ZoneInfo("Asia/Kolkata")
CENT = Decimal("0.01")
ZERO = Decimal("0")
GST = Decimal(str(GST_RATE))
TOLERANCE = Decimal(str(TOLERANCE_INR))
K = AuditFinding.Kind


def money(x):
    """Any number -> Decimal rounded to paise. Decimals stay Decimals, so no float drift."""
    return Decimal(str(x)).quantize(CENT, rounding=ROUND_HALF_UP)


def slabs(grams):
    return max(1, ceil(int(grams) / 500))


def local_date(ts):
    """Timestamp -> its date in IST. Naive values are read as UTC, as ledger.build does
    (pd.to_datetime(..., utc=True)), so the audit and the ledger agree on the delivery date."""
    if ts is None or pd.isna(ts):
        return None
    ts = pd.Timestamp(ts)
    if ts.tzinfo is None:
        ts = ts.tz_localize("UTC")
    return ts.tz_convert(IST).date()


def _finding(merchant, kind, courier_id, courier_name, awb, billed, expected, claim, detail,
             invoice_id="", line_ref=""):
    return AuditFinding(
        merchant=merchant, kind=kind, courier_id=int(courier_id), courier_name=courier_name,
        awb_number=awb, invoice_id=invoice_id, line_ref=line_ref,
        billed_inr=money(billed), expected_inr=money(expected), claim_inr=money(claim),
        detail=detail[:200],
    )


def _ledger_by_awb(merchant):
    df = frame(
        ShipmentLedger.objects.for_merchant(merchant),
        "awb_number", "courier_id", "courier_name", "zone", "weight_slabs", "payment_mode",
        "is_delivered", "is_rto", "order_value", "cod_due_inr", "cod_remitted_inr", "delivered_ts",
    )
    return df.set_index("awb_number").to_dict("index")


def _invoice_findings(merchant):
    """Price every invoice line against the rate card and the parcel's real weight, zone and outcome."""
    stats = {"lines_checked": 0, "lines_not_verifiable": 0, "lines_underbilled": 0}
    ledger = _ledger_by_awb(merchant)
    lines = frame(
        InvoiceLine.objects.for_merchant(merchant),
        "line_ref", "invoice_id", "invoice_date", "courier_id", "courier__name", "awb_number",
        "billed_weight_g", "billed_zone", "forward_freight_inr", "cod_charge_inr",
        "rto_freight_inr", "gst_inr", "total_billed_inr",
    )
    if lines.empty:
        return [], stats
    if not ledger:
        # No ledger means we cannot tell a real AWB from an unknown one. Claim nothing.
        stats["lines_checked"] = stats["lines_not_verifiable"] = len(lines)
        return [], stats

    rates = {(r.courier_id, r.zone): r for r in RateCard.objects.for_merchant(merchant)}
    lines = lines.sort_values(["invoice_date", "line_ref"], kind="stable")
    seen, findings = set(), []

    for ln in lines.to_dict("records"):
        stats["lines_checked"] += 1
        awb, billed = ln["awb_number"], money(ln["total_billed_inr"])

        def found(kind, expected, claim, detail):
            findings.append(_finding(merchant, kind, ln["courier_id"], ln["courier__name"], awb,
                                     billed, expected, claim, detail, ln["invoice_id"], ln["line_ref"]))

        parcel = ledger.get(awb)
        if parcel is None:
            found(K.UNKNOWN_AWB, ZERO, billed, f"AWB {awb} is not one of our shipments")
            continue
        if awb in seen:
            found(K.DUPLICATE, ZERO, billed, f"AWB {awb} was already billed on an earlier line")
            continue
        seen.add(awb)

        rate = rates.get((ln["courier_id"], parcel["zone"])) if parcel["zone"] else None
        if rate is None:
            stats["lines_not_verifiable"] += 1
            continue

        actual_slabs = int(parcel["weight_slabs"])
        freight = rate.first_500g_inr + (actual_slabs - 1) * rate.addl_500g_inr
        cod_due = parcel["payment_mode"] == Order.PaymentMode.COD and bool(parcel["is_delivered"])
        cod_fee = max(rate.cod_min_inr, parcel["order_value"] * rate.cod_fee_pct / 100) if cod_due else ZERO
        rto_fee = freight * rate.rto_charge_pct_of_freight / 100 if parcel["is_rto"] else ZERO
        expected = freight + cod_fee + rto_fee
        if money(ln["gst_inr"]) > ZERO:
            expected *= 1 + GST
        expected = money(expected)

        claim = billed - expected
        if claim < -TOLERANCE:
            stats["lines_underbilled"] += 1
            continue
        if claim <= TOLERANCE:
            continue

        billed_slabs = slabs(ln["billed_weight_g"])
        if billed_slabs > actual_slabs:
            found(K.WEIGHT, expected, claim,
                  f"Billed {billed_slabs} x 500g slabs, parcel is {actual_slabs}")
        elif ln["billed_zone"] != parcel["zone"]:
            found(K.ZONE, expected, claim, f"Billed zone {ln['billed_zone']}, destination is zone {parcel['zone']}")
        elif money(ln["rto_freight_inr"]) > ZERO and not parcel["is_rto"]:
            found(K.RTO_NOT_DUE, expected, claim,
                  f"RTO charge Rs {money(ln['rto_freight_inr'])} but the parcel was not returned")
        elif money(ln["cod_charge_inr"]) > money(cod_fee) + TOLERANCE:
            found(K.COD_NOT_DUE, expected, claim,
                  f"COD fee Rs {money(ln['cod_charge_inr'])}, due Rs {money(cod_fee)}")
        else:
            found(K.OTHER, expected, claim, f"Billed Rs {billed}, rate card allows Rs {expected}")

    return findings, stats


def _cod_findings(merchant, grace_days):
    """Delivered COD parcels the courier has not paid for (after the grace period) or has short-paid."""
    stats = {"cod_delivered_parcels": 0, "cod_pending_not_yet_due": 0}
    parcels = [p for p in _ledger_by_awb(merchant).items()
               if p[1]["payment_mode"] == Order.PaymentMode.COD and p[1]["is_delivered"]]
    stats["cod_delivered_parcels"] = len(parcels)

    latest = CodRemittance.objects.for_merchant(merchant).aggregate(d=Max("remittance_date"))["d"]
    if not parcels or latest is None:
        # No statement yet: nothing is overdue, so every unpaid parcel is still pending.
        stats["cod_pending_not_yet_due"] = sum(1 for _, p in parcels if money(p["cod_remitted_inr"]) == ZERO)
        return [], stats
    cutoff = latest - timedelta(days=grace_days)

    findings = []
    for awb, p in parcels:
        due, paid = money(p["cod_due_inr"]), money(p["cod_remitted_inr"])
        if paid == ZERO:
            delivered = local_date(p["delivered_ts"])
            if delivered is None or delivered > cutoff:
                stats["cod_pending_not_yet_due"] += 1
                continue
            findings.append(_finding(merchant, K.COD_UNPAID, p["courier_id"], p["courier_name"], awb,
                                     paid, due, due,
                                     f"Delivered {delivered}, nothing remitted by {latest} (grace {grace_days} days)"))
        elif due - paid > TOLERANCE:
            findings.append(_finding(merchant, K.COD_SHORT, p["courier_id"], p["courier_name"], awb,
                                     paid, due, due - paid, f"Collected Rs {due}, remitted Rs {paid}"))
    return findings, stats


@transaction.atomic
def run_audit(merchant, cod_grace_days=COD_GRACE_DAYS):
    """Delete and rewrite this merchant's findings. Other merchants are never touched."""
    AuditFinding.objects.for_merchant(merchant).delete()
    invoice, invoice_stats = _invoice_findings(merchant)
    cod, cod_stats = _cod_findings(merchant, cod_grace_days)
    findings = invoice + cod
    AuditFinding.objects.bulk_create(findings, batch_size=2000)
    return {
        **invoice_stats,
        **cod_stats,
        "findings": len(findings),
        "by_kind": dict(Counter(str(f.kind) for f in findings)),
        "claim_total_inr": float(sum((f.claim_inr for f in findings), ZERO)),
    }
