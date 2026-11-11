from django.db import models

from core.models import Courier, Customer, Shipment, TenantModel


class ShipmentLedger(TenantModel):
    """One row per AWB with everything known about that parcel side by side.
    Never edited by hand: build.rebuild_ledger() deletes and rewrites a merchant's rows."""

    shipment = models.OneToOneField(
        Shipment, on_delete=models.CASCADE, related_name="ledger"
    )
    awb_number = models.CharField(max_length=40, db_index=True)
    order_ref = models.CharField(max_length=40)
    customer = models.ForeignKey(Customer, on_delete=models.CASCADE)
    courier = models.ForeignKey(Courier, on_delete=models.CASCADE)
    courier_name = models.CharField(max_length=80)

    # order
    order_ts = models.DateTimeField()
    order_date = models.DateField()
    order_month = models.DateField(db_index=True)
    order_hour = models.PositiveSmallIntegerField()
    payment_mode = models.CharField(max_length=10)
    sales_channel = models.CharField(max_length=40, blank=True)
    order_value = models.DecimalField(max_digits=10, decimal_places=2)
    prior_orders = models.PositiveIntegerField()
    is_first_order = models.BooleanField()

    # destination
    pincode = models.CharField(max_length=6, db_index=True)
    city = models.CharField(max_length=80, blank=True)
    state = models.CharField(max_length=80, blank=True)
    zone = models.CharField(max_length=2, blank=True)
    city_tier = models.PositiveSmallIntegerField(null=True)

    # parcel
    pkg_weight_g = models.PositiveIntegerField()
    vol_weight_g = models.PositiveIntegerField()
    chargeable_weight_g = models.PositiveIntegerField()
    weight_slabs = models.PositiveSmallIntegerField()

    # outcome
    final_status = models.CharField(max_length=20)
    is_delivered = models.BooleanField()
    is_rto = models.BooleanField(db_index=True)
    is_lost = models.BooleanField()
    delivery_attempts = models.PositiveSmallIntegerField()
    first_attempt_delivered = models.BooleanField()
    last_ndr_reason = models.CharField(max_length=80, blank=True)

    # timing
    pickup_ts = models.DateTimeField()
    delivered_ts = models.DateTimeField(null=True)
    promised_delivery_date = models.DateField(null=True)
    days_order_to_pickup = models.DecimalField(max_digits=6, decimal_places=2)
    days_pickup_to_delivery = models.DecimalField(
        max_digits=6, decimal_places=2, null=True
    )
    on_time = models.BooleanField(null=True)

    # money
    invoice_lines = models.PositiveSmallIntegerField()
    billed_total_inr = models.DecimalField(max_digits=10, decimal_places=2)
    cod_due_inr = models.DecimalField(max_digits=10, decimal_places=2)
    cod_remitted_inr = models.DecimalField(max_digits=10, decimal_places=2)

    built_at = models.DateTimeField(auto_now_add=True)
