import re

from django.utils import timezone
from rest_framework import serializers
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.response import Response

from ingestion.views import MerchantAPIView

from .models import RiskModel
from .score import BAND_NAMES, MOBILE, PAYMENT_MODES, SALES_CHANNELS, score_orders
from .train import (KEEP_RATE, MARGIN_PCT, active_model, economics, load_artifact, model_feature_compatible,
                    train_model)

STALE_MODEL = {
    "error": "This model was trained with an older feature set.",
    "action": "POST /api/ml/train/ to retrain the model.",
}


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
        if not model_feature_compatible(run):
            return Response(STALE_MODEL, status=409)
        saved = load_artifact(run)
        p = saved["scorer"].score(saved["test"])
        return Response(economics(saved["test"], p, saved["rto_cost"], margin_pct=margin_pct, keep_rate=keep_rate))


# ---------------------------------------------------------------- Order Risk Checker
MAX_BATCH = 500


class OrderInput(serializers.Serializer):
    """One order that has not shipped yet. Only order_value, payment_mode and pincode are compulsory."""
    order_value = serializers.DecimalField(max_digits=10, decimal_places=2, min_value=0)
    payment_mode = serializers.CharField()
    pincode = serializers.CharField()
    address = serializers.CharField(required=False, allow_blank=True, default="")
    customer_id = serializers.CharField(required=False, allow_blank=True, default="")
    phone = serializers.CharField(required=False, allow_blank=True, default="")
    sales_channel = serializers.CharField(required=False, allow_blank=True, default="")
    order_ts = serializers.DateTimeField(required=False)
    order_id = serializers.CharField(required=False, allow_blank=True, default="")

    def validate_payment_mode(self, value):
        mode = PAYMENT_MODES.get(value.strip().lower())
        if mode is None:
            raise serializers.ValidationError("Use COD or Prepaid.")
        return mode

    def validate_pincode(self, value):
        pin = re.sub(r"\s", "", value)
        if not re.fullmatch(r"[1-9]\d{5}", pin):
            raise serializers.ValidationError("Enter a 6-digit pincode.")
        return pin

    def validate_phone(self, value):
        if not value.strip():
            return ""
        digits = re.sub(r"\D", "", value)[-10:]
        if not MOBILE.fullmatch(digits):
            raise serializers.ValidationError("Enter a 10-digit mobile number starting with 6, 7, 8 or 9.")
        return digits

    def validate_sales_channel(self, value):
        channel = value.strip()
        return SALES_CHANNELS.get(channel.lower(), channel)      # unknown channels are scored as unseen

    def validate(self, data):
        data.setdefault("order_ts", timezone.now())
        return data


class ScoreView(MerchantAPIView):
    """Order Risk Checker for one order. Reads the merchant's history; writes nothing."""

    def post(self, request):
        order = OrderInput(data=request.data)
        order.is_valid(raise_exception=True)
        result = score_orders(self.merchant(), [order.validated_data])[0]
        return Response({"order_id": order.validated_data["order_id"], **result})


class ScoreBatchView(MerchantAPIView):
    """Score up to 500 orders in one call: {"orders": [{...}, {...}]}. Results keep the input order."""

    def post(self, request):
        if not isinstance(request.data, dict):
            raise ValidationError({"orders": 'Send a JSON object like {"orders": [ ... ]}.'})
        rows = request.data.get("orders")
        if not isinstance(rows, list) or not rows:
            raise ValidationError({"orders": "Send a non-empty list of orders."})
        if len(rows) > MAX_BATCH:
            raise ValidationError({"orders": f"At most {MAX_BATCH} orders per call."})
        orders = OrderInput(data=rows, many=True)
        if not orders.is_valid():
            raise ValidationError({"orders": orders.errors})      # keyed by row position, failing rows only
        validated = list(orders.validated_data)
        results = score_orders(self.merchant(), validated)
        out = [{"order_id": o["order_id"], **r} for o, r in zip(validated, results)]
        by_category = {band: sum(r["risk_category"] == band for r in out) for band in BAND_NAMES}
        return Response({"count": len(out), "by_category": by_category, "results": out})
