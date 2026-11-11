from django.conf import settings
from django.db import models

from core.models import TenantModel


class UploadBatch(TenantModel):
    class Status(models.TextChoices):
        UPLOADED = "uploaded"
        VALIDATED = "validated"
        LOADED = "loaded"
        FAILED = "failed"

    dataset_type = models.CharField(max_length=20)
    file = models.FileField(upload_to="uploads/%Y/%m/")
    original_filename = models.CharField(max_length=255)
    uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.UPLOADED)
    column_mapping = models.JSONField(default=dict)
    quality_report = models.JSONField(default=dict)
    load_result = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
