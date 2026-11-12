from decimal import Decimal

from django.db.models import Count, Q, Sum

from core.models import InvoiceLine
from ledger.metrics import num, pct

from .models import AuditFinding

K = AuditFinding.Kind
LABELS = dict(K.choices)
COD_KINDS = [K.COD_UNPAID, K.COD_SHORT]
COD = Q(kind__in=COD_KINDS)
BILLING = ~COD
ZERO = Decimal("0")


def findings(merchant):
    """This merchant's findings, biggest claim first. Never anyone else's.
    id breaks ties between equal claims, so limit/offset pages never overlap or skip a finding."""
    return AuditFinding.objects.for_merchant(merchant).order_by("-claim_inr", "id")


def summary(merchant):
    mine = findings(merchant)
    billed = InvoiceLine.objects.for_merchant(merchant).aggregate(t=Sum("total_billed_inr"))["t"] or ZERO
    totals = mine.aggregate(
        billing=Sum("claim_inr", filter=BILLING), billing_n=Count("id", filter=BILLING),
        cod=Sum("claim_inr", filter=COD), cod_n=Count("id", filter=COD),
    )
    billing, cod = totals["billing"] or ZERO, totals["cod"] or ZERO

    by_kind = [{"kind": g["kind"], "label": LABELS.get(g["kind"], g["kind"]),
                "findings": g["n"], "claim_inr": num(g["claim"])}
               for g in mine.values("kind").order_by().annotate(n=Count("id"), claim=Sum("claim_inr"))]
    by_courier = [{"courier": g["courier_name"], "findings": g["n"], "claim_inr": num(g["claim"])}
                  for g in mine.values("courier_id", "courier_name").order_by()
                  .annotate(n=Count("id"), claim=Sum("claim_inr"))]
    by_courier_kind = [{"courier": g["courier_name"], "kind": g["kind"], "label": LABELS.get(g["kind"], g["kind"]),
                        "findings": g["n"], "claim_inr": num(g["claim"])}
                       for g in mine.values("courier_id", "courier_name", "kind").order_by()
                       .annotate(n=Count("id"), claim=Sum("claim_inr"))]
    for rows in (by_kind, by_courier, by_courier_kind):
        rows.sort(key=lambda r: (-r["claim_inr"], r.get("courier", ""), r.get("kind", "")))

    return {
        "total_courier_billed_inr": num(billed),
        "billing_overcharge_inr": num(billing),
        "billing_findings": totals["billing_n"],
        "overcharge_pct_of_billed": pct(float(billing), float(billed)),
        "cod_missing_inr": num(cod),
        "cod_findings": totals["cod_n"],
        "total_recoverable_inr": num(billing + cod),
        "findings": totals["billing_n"] + totals["cod_n"],
        "by_kind": by_kind,
        "by_courier": by_courier,
        "by_courier_kind": by_courier_kind,
    }
