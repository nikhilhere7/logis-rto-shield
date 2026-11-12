from django.db import models

from core.models import Courier, TenantModel


class AuditFinding(TenantModel):
    """One disputable charge. Rebuilt from scratch by engine.run_audit(), never edited by hand."""

    class Kind(models.TextChoices):
        WEIGHT = "weight_inflated", "Billed weight higher than the parcel"
        ZONE = "wrong_zone", "Billed for a costlier zone"
        DUPLICATE = "duplicate_line", "Same AWB billed more than once"
        RTO_NOT_DUE = "rto_charge_not_due", "RTO charge on a parcel that was not returned"
        COD_NOT_DUE = "cod_fee_not_due", "COD fee that should not apply"
        OTHER = "other_overcharge", "Total higher than the rate card allows"
        UNKNOWN_AWB = "unknown_awb", "Billed for a parcel we never shipped"
        COD_UNPAID = "cod_not_remitted", "COD collected but never paid to us"
        COD_SHORT = "cod_short_paid", "COD paid, but less than collected"

    kind = models.CharField(max_length=24, choices=Kind.choices, db_index=True)
    courier = models.ForeignKey(Courier, on_delete=models.CASCADE)
    courier_name = models.CharField(max_length=80)
    awb_number = models.CharField(max_length=40, db_index=True)
    invoice_id = models.CharField(max_length=40, blank=True)
    line_ref = models.CharField(max_length=120, blank=True)
    billed_inr = models.DecimalField(max_digits=10, decimal_places=2)
    expected_inr = models.DecimalField(max_digits=10, decimal_places=2)
    claim_inr = models.DecimalField(max_digits=10, decimal_places=2)
    detail = models.CharField(max_length=200)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-claim_inr"]
