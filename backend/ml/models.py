from django.db import models

from core.models import TenantModel


class RiskModel(TenantModel):
    """One training run of a merchant's RTO model. Only the active one is used for predictions."""

    class Status(models.TextChoices):
        TRAINED = "trained"
        INSUFFICIENT_DATA = "insufficient_data"

    status = models.CharField(max_length=20, choices=Status.choices)
    is_active = models.BooleanField(default=False, db_index=True)
    artifact = models.FileField(upload_to="models/", blank=True)
    metrics = models.JSONField(default=dict)
    trained_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-trained_at"]
