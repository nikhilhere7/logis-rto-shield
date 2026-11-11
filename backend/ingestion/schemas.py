from dataclasses import dataclass

@dataclass(frozen=True)
class F:
    name: str
    kind: str
    required: bool = False
    aliases: tuple = ()
    choices: dict | None = None

@dataclass(frozen=True)
class Spec:
    label: str
    fields: tuple

    @property
    def required(self):
        return [f.name for f in self.fields if f.required]

PAYMENT = {
    "COD": ("cod", "cash on delivery", "c.o.d", "c.o.d.", "cash", "pay on delivery"),
    "Prepaid": ("prepaid", "paid", "online", "upi", "card", "netbanking", "wallet", "razorpay", "pre-paid"),
}

ORDER_STATUS = {
    "Shipped": ("shipped", "fulfilled", "delivered", "completed", "dispatched", "rto"),
    "Cancelled": ("cancelled", "canceled", "voided"),
}

FINAL_STATUS = {
    "Delivered": ("delivered", "dl", "completed"),
    "RTO Delivered": ("rto delivered", "rto", "returned", "rto-delivered", "returned to origin", "rtd"),
    "Lost": ("lost", "damaged", "lost in transit"),
}

SPECS = {
    "orders": Spec("Orders export", (
        F("order_id", "id", True, ("order id", "order number", "order no", "order name")),
        F("order_ts", "ts", True, ("order date", "created at", "date", "order created", "ordered at")),
        F("customer_id", "id", False, ("customer id", "customer code")),
        F("customer_phone", "phone", False, ("phone", "mobile", "shipping phone", "billing phone", "contact number")),
        F("customer_name", "str", False, ("customer name", "shipping name", "billing name")),
        F("pincode", "pincode", True, ("shipping pincode", "pin code", "pin", "zip", "shipping zip", "postal code")),
        F("address_line", "str", False, ("address", "shipping address", "address1", "shipping address1")),
        F("payment_mode", "choice", True, ("payment method", "payment type", "payment"), PAYMENT),
        F("order_value", "money", True, ("total", "order total", "amount", "total price", "grand total")),
        F("gross_value", "money", False, ("subtotal", "sub total")),
        F("discount_inr", "money", False, ("discount", "discount amount")),
        F("shipping_fee_inr", "money", False, ("shipping", "shipping charge", "shipping fee")),
        F("sales_channel", "str", False, ("channel", "source")),
        F("status", "choice", False, ("order status", "fulfillment status"), ORDER_STATUS),
    )),
    "shipments": Spec("Shipment / delivery report", (
        F("awb_number", "id", True, ("awb", "awb no", "tracking number", "tracking id", "waybill")),
        F("order_id", "id", True, ("order id", "order number", "order no", "reference number")),
        F("courier", "str", True, ("courier name", "courier partner", "carrier", "courier id", "logistics partner")),
        F("pickup_ts", "ts", True, ("pickup date", "shipped date", "dispatch date", "shipped at", "pickup time")),
        F("pkg_weight_g", "num", True, ("weight", "weight g", "dead weight", "package weight", "weight kg")),
        F("pkg_length_cm", "num", False, ("length", "length cm")),
        F("pkg_breadth_cm", "num", False, ("breadth", "width", "breadth cm", "width cm")),
        F("pkg_height_cm", "num", False, ("height", "height cm")),
        F("final_status", "choice", True, ("status", "delivery status", "shipment status", "current status"), FINAL_STATUS),
        F("delivered_ts", "ts", False, ("delivered date", "delivery date", "delivered at")),
        F("promised_delivery_date", "date", False, ("edd", "expected delivery date", "promised date")),
        F("delivery_attempts", "int", False, ("attempts", "attempt count")),
        F("last_ndr_reason", "str", False, ("ndr reason", "failure reason")),
        F("rto_initiated_ts", "ts", False, ("rto initiated date", "rto date")),
        F("rto_received_ts", "ts", False, ("rto delivered date", "rto received date")),
        F("rto_condition", "str", False, ("return condition",)),
    )),
}
