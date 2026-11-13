from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from ingestion.views import MerchantAPIView
from ml.models import RiskModel
from ml.train import active_model, model_feature_compatible

from .models import CodRemittance, Customer, InvoiceLine, Merchant, Order, PincodeZone, RateCard, Shipment


@api_view(["GET"])
@permission_classes([AllowAny])
def health(request):
    return Response({"status": "ok", "merchants": Merchant.objects.count()})


# ---------------------------------------------------------------- workspace readiness
MODEL_REASONS = {
    "ready": "Orders are scored by your trained risk model.",
    "none": "No risk model has been trained yet. Orders are scored with rules until there is enough history.",
    "stale": ("Your risk model was trained on an older set of features. Orders are scored with rules "
              "until it is retrained."),
}


def model_status(merchant):
    """The risk model's state for this merchant, from the existing ML code (no thresholds of its own):
    an active compatible model is ready, an active older one is stale, a latest run that had too little
    data is insufficient_data, otherwise there is none."""
    run = active_model(merchant)
    if run is not None:
        state = "ready" if model_feature_compatible(run) else "stale"
        return {"state": state, "reason": MODEL_REASONS[state], "trained_at": run.trained_at}
    latest = RiskModel.objects.for_merchant(merchant).first()
    if latest is not None and latest.status == RiskModel.Status.INSUFFICIENT_DATA:
        reason = latest.metrics.get("reason") or "There is not enough shipment history to train a model yet."
        return {"state": "insufficient_data", "reason": reason, "trained_at": None}
    return {"state": "none", "reason": MODEL_REASONS["none"], "trained_at": None}


class WorkspaceStatusView(MerchantAPIView):
    """What this merchant has loaded, as plain counts, and the risk model's state. Reads only.
    Counts come from the business tables, which only change when an upload is committed, so failed or
    validated-but-uncommitted uploads are never counted."""

    def get(self, request):
        m = self.merchant()
        shipments = Shipment.objects.for_merchant(m)
        return Response({
            "counts": {
                "orders": Order.objects.for_merchant(m).count(),
                "customers": Customer.objects.for_merchant(m).count(),
                "shipments": shipments.count(),
                "shipments_with_outcome": shipments.filter(
                    final_status__in=[Shipment.FinalStatus.DELIVERED, Shipment.FinalStatus.RTO]).count(),
                "cod_shipments": shipments.filter(order__payment_mode=Order.PaymentMode.COD).count(),
                "pincode_zones": PincodeZone.objects.for_merchant(m).count(),
                "rate_cards": RateCard.objects.for_merchant(m).count(),
                "invoice_lines": InvoiceLine.objects.for_merchant(m).count(),
                "remittances": CodRemittance.objects.for_merchant(m).count(),
            },
            "model": model_status(m),
        })
