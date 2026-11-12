import csv

from django.http import HttpResponse
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from ingestion.views import MerchantAPIView

from . import reports
from .engine import COD_GRACE_DAYS, run_audit
from .models import AuditFinding

LABELS = dict(AuditFinding.Kind.choices)
MAX_LIMIT = 500


def whole_number(request, name, default, maximum=None):
    raw = request.query_params.get(name, default)
    try:
        value = int(raw)
    except (TypeError, ValueError):
        raise ValidationError({name: "Must be a whole number."})
    if value < 0:
        raise ValidationError({name: "Must not be negative."})
    if maximum is not None and value > maximum:
        raise ValidationError({name: f"Must be at most {maximum}."})
    return value


def row(f):
    return {
        "id": f.id,
        "kind": f.kind,
        "label": LABELS.get(f.kind, f.kind),
        "courier_name": f.courier_name,
        "awb_number": f.awb_number,
        "invoice_id": f.invoice_id,
        "line_ref": f.line_ref,
        "billed_inr": float(f.billed_inr),
        "expected_inr": float(f.expected_inr),
        "claim_inr": float(f.claim_inr),
        "detail": f.detail,
        "created_at": f.created_at.isoformat(),
    }


class RunView(MerchantAPIView):
    """Rebuild this merchant's findings. ?cod_grace_days= overrides the 21-day COD grace period."""

    def post(self, request):
        days = whole_number(request, "cod_grace_days", COD_GRACE_DAYS)
        return Response(run_audit(self.merchant(), cod_grace_days=days))


class SummaryView(MerchantAPIView):
    def get(self, request):
        return Response(reports.summary(self.merchant()))


class FindingsView(MerchantAPIView):
    """?kind= and ?courier= filter; ?limit= (default 50, max 500) and ?offset= page through."""

    def get(self, request):
        qs = reports.findings(self.merchant())
        kind = request.query_params.get("kind")
        if kind:
            if kind not in LABELS:
                raise ValidationError({"kind": f"Must be one of: {', '.join(LABELS)}"})
            qs = qs.filter(kind=kind)
        courier = request.query_params.get("courier")
        if courier:
            qs = qs.filter(courier_name=courier)
        limit = whole_number(request, "limit", 50, MAX_LIMIT)
        offset = whole_number(request, "offset", 0)
        return Response([row(f) for f in qs[offset:offset + limit]])


class DisputeFileView(MerchantAPIView):
    """Every finding as a CSV the merchant can send to the courier."""

    def get(self, request):
        response = HttpResponse(content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = 'attachment; filename="logis_dispute_claims.csv"'
        response.write("﻿")    # BOM, so Excel opens it as UTF-8
        out = csv.writer(response)
        out.writerow(["Kind", "Reason", "Courier", "AWB", "Invoice ID", "Line ref",
                      "Billed (INR)", "Expected (INR)", "Claim (INR)", "Detail"])
        for f in reports.findings(self.merchant()):
            out.writerow([f.kind, LABELS.get(f.kind, f.kind), f.courier_name, f.awb_number, f.invoice_id,
                          f.line_ref, f.billed_inr, f.expected_inr, f.claim_inr, f.detail])
        return response
