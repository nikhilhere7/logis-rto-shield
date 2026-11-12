from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.response import Response

from ingestion.views import MerchantAPIView

from .models import RiskModel
from .train import KEEP_RATE, MARGIN_PCT, active_model, economics, load_artifact, train_model


def describe(run):
    return {
        "id": run.id,
        "status": run.status,
        "is_active": run.is_active,
        "trained_at": run.trained_at,
        **run.metrics,
    }


def number(request, name, default, low, high):
    raw = request.query_params.get(name)
    if raw is None or raw == "":
        return default
    try:
        value = float(raw)
    except ValueError:
        raise ValidationError({name: "Must be a number."})
    if not low <= value <= high:
        raise ValidationError({name: f"Must be between {low} and {high}."})
    return value


class TrainView(MerchantAPIView):
    """Train this merchant's RTO model on its current ledger. The new model becomes active if training works."""

    def post(self, request):
        return Response(describe(train_model(self.merchant())))


class ModelView(MerchantAPIView):
    """The active model, or else the latest training attempt (e.g. one that had too little data)."""

    def get(self, request):
        m = self.merchant()
        run = active_model(m) or RiskModel.objects.for_merchant(m).first()
        if run is None:
            raise NotFound("No model has been trained for this merchant yet. POST /api/ml/train/ to train one.")
        return Response(describe(run))


class EconomicsView(MerchantAPIView):
    """Threshold economics on the active model's test period, with ?margin_pct= and ?keep_rate= what-ifs."""

    def get(self, request):
        margin_pct = number(request, "margin_pct", MARGIN_PCT, 0, 100)
        keep_rate = number(request, "keep_rate", KEEP_RATE, 0, 1)
        run = active_model(self.merchant())
        if run is None:
            raise NotFound("No active model for this merchant. POST /api/ml/train/ to train one.")
        saved = load_artifact(run)
        p = saved["scorer"].score(saved["test"])
        return Response(economics(saved["test"], p, saved["rto_cost"], margin_pct=margin_pct, keep_rate=keep_rate))
