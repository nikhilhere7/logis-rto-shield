from django.contrib.auth.models import AbstractUser
from django.db import models


class Merchant(models.Model):
    name = models.CharField(max_length=120, unique=True)
    warehouse_pincode = models.CharField(max_length=6, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name


class User(AbstractUser):
    """Custom user so every login belongs to one merchant. Staff users can have merchant = NULL."""
    merchant = models.ForeignKey(Merchant, null=True, blank=True, on_delete=models.CASCADE, related_name="users")


class TenantQuerySet(models.QuerySet):
    def for_merchant(self, merchant):
        return self.filter(merchant=merchant)


class TenantModel(models.Model):
    """Base for every business table. Nothing is stored without a merchant."""
    merchant = models.ForeignKey(Merchant, on_delete=models.CASCADE, related_name="%(class)ss")
    objects = TenantQuerySet.as_manager()

    class Meta:
        abstract = True


# ---------------------------------------------------------------- reference data
class PincodeZone(TenantModel):
    """Zone is measured from the merchant's warehouse, so it is per merchant, not global."""
    pincode = models.CharField(max_length=6)
    city = models.CharField(max_length=80)
    state = models.CharField(max_length=80)
    zone = models.CharField(max_length=2)
    city_tier = models.PositiveSmallIntegerField(default=1)
    cod_serviceable = models.BooleanField(default=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["merchant", "pincode"], name="uq_pincode")]


class Product(TenantModel):
    sku = models.CharField(max_length=40)
    name = models.CharField(max_length=160)
    category = models.CharField(max_length=60, blank=True)
    mrp = models.DecimalField(max_digits=10, decimal_places=2)
    dead_weight_g = models.PositiveIntegerField()
    length_cm = models.DecimalField(max_digits=6, decimal_places=1)
    breadth_cm = models.DecimalField(max_digits=6, decimal_places=1)
    height_cm = models.DecimalField(max_digits=6, decimal_places=1)
    launch_date = models.DateField(null=True, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["merchant", "sku"], name="uq_sku")]


class Courier(TenantModel):
    code = models.CharField(max_length=20)
    name = models.CharField(max_length=80)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["merchant", "code"], name="uq_courier")]

    def __str__(self):
        return self.name


class RateCard(TenantModel):
    courier = models.ForeignKey(Courier, on_delete=models.CASCADE, related_name="rates")
    zone = models.CharField(max_length=2)
    first_500g_inr = models.DecimalField(max_digits=8, decimal_places=2)
    addl_500g_inr = models.DecimalField(max_digits=8, decimal_places=2)
    cod_fee_pct = models.DecimalField(max_digits=5, decimal_places=2)
    cod_min_inr = models.DecimalField(max_digits=8, decimal_places=2)
    rto_charge_pct_of_freight = models.DecimalField(max_digits=5, decimal_places=2, default=100)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["merchant", "courier", "zone"], name="uq_rate")]


# ---------------------------------------------------------------- customers and orders
class Customer(TenantModel):
    external_id = models.CharField(max_length=40)
    name = models.CharField(max_length=120, blank=True)
    phone_hash = models.CharField(max_length=64, blank=True, db_index=True)  # SHA-256, never the raw number
    pincode = models.CharField(max_length=6, db_index=True)
    address_line = models.TextField(blank=True)
    signup_date = models.DateField(null=True, blank=True)
    acquisition_channel = models.CharField(max_length=40, blank=True)
    phone_verified = models.BooleanField(default=False)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["merchant", "external_id"], name="uq_customer")]


class Order(TenantModel):
    class PaymentMode(models.TextChoices):
        COD = "COD"
        PREPAID = "Prepaid"

    class Status(models.TextChoices):
        SHIPPED = "Shipped"
        CANCELLED = "Cancelled"

    external_id = models.CharField(max_length=40)
    customer = models.ForeignKey(Customer, on_delete=models.CASCADE, related_name="orders")
    order_ts = models.DateTimeField(db_index=True)
    sales_channel = models.CharField(max_length=40, blank=True)
    payment_mode = models.CharField(max_length=10, choices=PaymentMode.choices)
    prepaid_gateway = models.CharField(max_length=20, blank=True)
    gross_value = models.DecimalField(max_digits=10, decimal_places=2)
    discount_inr = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    shipping_fee_inr = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    order_value = models.DecimalField(max_digits=10, decimal_places=2)
    status = models.CharField(max_length=12, choices=Status.choices)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["merchant", "external_id"], name="uq_order")]


class OrderItem(TenantModel):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey(Product, on_delete=models.PROTECT)
    qty = models.PositiveIntegerField()
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)
    line_total = models.DecimalField(max_digits=10, decimal_places=2)


# ---------------------------------------------------------------- shipping
class Shipment(TenantModel):
    class FinalStatus(models.TextChoices):
        DELIVERED = "Delivered"
        RTO = "RTO Delivered"
        LOST = "Lost"

    awb_number = models.CharField(max_length=40)
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="shipments")
    courier = models.ForeignKey(Courier, on_delete=models.PROTECT)
    pickup_ts = models.DateTimeField()
    pkg_weight_g = models.PositiveIntegerField()
    pkg_length_cm = models.DecimalField(max_digits=6, decimal_places=1)
    pkg_breadth_cm = models.DecimalField(max_digits=6, decimal_places=1)
    pkg_height_cm = models.DecimalField(max_digits=6, decimal_places=1)
    promised_delivery_date = models.DateField(null=True, blank=True)
    delivery_attempts = models.PositiveSmallIntegerField(default=0)
    last_ndr_reason = models.CharField(max_length=80, blank=True)
    final_status = models.CharField(max_length=20, choices=FinalStatus.choices, db_index=True)
    delivered_ts = models.DateTimeField(null=True, blank=True)
    rto_initiated_ts = models.DateTimeField(null=True, blank=True)
    rto_received_ts = models.DateTimeField(null=True, blank=True)
    rto_condition = models.CharField(max_length=20, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["merchant", "awb_number"], name="uq_awb")]


class TrackingEvent(TenantModel):
    shipment = models.ForeignKey(Shipment, on_delete=models.CASCADE, related_name="events")
    event_ts = models.DateTimeField()
    status = models.CharField(max_length=40)
    location = models.CharField(max_length=80, blank=True)


# ---------------------------------------------------------------- money
class InvoiceLine(TenantModel):
    """What the courier billed. awb_number is plain text on purpose: a courier can bill an AWB
    we have never seen, or bill the same AWB twice, and the audit has to be able to store both."""
    line_ref = models.CharField(max_length=40)
    invoice_id = models.CharField(max_length=40, db_index=True)
    invoice_date = models.DateField()
    courier = models.ForeignKey(Courier, on_delete=models.PROTECT)
    awb_number = models.CharField(max_length=40, db_index=True)
    shipment = models.ForeignKey(Shipment, null=True, blank=True, on_delete=models.SET_NULL,
                                 related_name="invoice_lines")
    billed_weight_g = models.PositiveIntegerField()
    billed_zone = models.CharField(max_length=2)
    forward_freight_inr = models.DecimalField(max_digits=10, decimal_places=2)
    cod_charge_inr = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    rto_freight_inr = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    gst_inr = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    total_billed_inr = models.DecimalField(max_digits=10, decimal_places=2)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["merchant", "line_ref"], name="uq_invoice_line")]


class CodRemittance(TenantModel):
    utr_batch = models.CharField(max_length=40)
    courier = models.ForeignKey(Courier, on_delete=models.PROTECT)
    awb_number = models.CharField(max_length=40, db_index=True)
    shipment = models.ForeignKey(Shipment, null=True, blank=True, on_delete=models.SET_NULL,
                                 related_name="remittances")
    remittance_date = models.DateField()
    amount_remitted_inr = models.DecimalField(max_digits=10, decimal_places=2)