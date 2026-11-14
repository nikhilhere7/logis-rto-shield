from django.http import Http404, HttpResponse
from django.utils import timezone
from django.utils.text import slugify
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from ingestion.views import MerchantAPIView

from .build import REPORTS, catalogue


class ReportListView(MerchantAPIView):
    """The reports on offer, and which of them this merchant has the data for."""

    def get(self, request):
        return Response(catalogue(self.merchant()))


class ReportPdfView(MerchantAPIView):
    """Build one report for the logged-in merchant and send it as a PDF. Nothing is stored."""

    def get(self, request, key):
        if key not in REPORTS:
            raise Http404("No such report.")
        merchant = self.merchant()
        entry = next(r for r in catalogue(merchant) if r["id"] == key)
        if not entry["available"]:
            raise ValidationError({"detail": entry["reason"]})
        pdf = REPORTS[key][2](merchant)
        response = HttpResponse(pdf, content_type="application/pdf")
        response["Content-Disposition"] = f'attachment; filename="{report_filename(merchant, key)}"'
        # Private business data: never kept by the browser or any proxy in between.
        response["Cache-Control"] = "no-store, private"
        return response


def report_filename(merchant, key):
    """logis_<merchant>_<report>_<YYYY-MM-DD>.pdf, ASCII only so it is safe in a header.
    Different merchants and different days never produce the same file name."""
    who = slugify(merchant.name) or "workspace"
    return f"logis_{who}_{key}_{timezone.localdate():%Y-%m-%d}.pdf"
