from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from ingestion.views import MerchantAPIView

from . import metrics
from .build import rebuild_ledger


def dimension(request, default):
    by = request.query_params.get("by", default)
    if by not in metrics.DIMENSIONS:
        raise ValidationError({"by": f"Must be one of: {', '.join(metrics.DIMENSIONS)}"})
    return by


class RebuildView(MerchantAPIView):
    """Rebuild this merchant's ledger from the canonical tables."""

    def post(self, request):
        return Response(rebuild_ledger(self.merchant()))


class OverviewView(MerchantAPIView):
    def get(self, request):
        return Response(metrics.overview(self.merchant()))


class MonthlyView(MerchantAPIView):
    def get(self, request):
        return Response(metrics.monthly(self.merchant()))


class RtoView(MerchantAPIView):
    def get(self, request):
        by = dimension(request, "courier")
        try:
            min_shipments = int(request.query_params.get("min_shipments", 1))
        except ValueError:
            raise ValidationError({"min_shipments": "Must be a whole number."})
        return Response(metrics.rto_by(self.merchant(), by, min_shipments))


class DeliveryView(MerchantAPIView):
    def get(self, request):
        return Response(metrics.delivery_by(self.merchant(), dimension(request, "courier")))


class CodView(MerchantAPIView):
    def get(self, request):
        return Response(metrics.cod_summary(self.merchant()))
