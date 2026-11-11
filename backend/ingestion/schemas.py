from dataclasses import dataclass

@dataclass(frozen=True)
class F:
    name: str
    kind: str  # id, str, ts, date, money, num, int, pincode, phone, choice, zone, bool
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
    "pincode_zones": Spec("Pincode to zone list", (
        F("pincode", "pincode", True, ("pin code", "pin", "zip", "postal code", "destination pincode")),
        F("zone", "zone", True, ("zone code", "billing zone", "courier zone")),
        F("city", "str", False, ("city name", "district")),
        F("state", "str", False, ("state name",)),
        F("city_tier", "int", False, ("tier",)),
        F("cod_serviceable", "bool", False, ("cod", "cod available", "cod serviceability")),
    )),
    "rate_card": Spec("Courier rate card", (
        F("courier", "str", True, ("courier name", "courier partner", "carrier", "courier id")),
        F("zone", "zone", True, ("zone code", "billing zone")),
        F("first_500g_inr", "money", True, ("first 500g", "base rate", "upto 500g", "first slab")),
        F("addl_500g_inr", "money", True, ("additional 500g", "addl 500g", "every additional 500g", "next slab")),
        F("cod_fee_pct", "num", False, ("cod percent", "cod fee percent", "cod pct", "cod %")),
        F("cod_min_inr", "money", False, ("cod minimum", "min cod charge", "cod min")),
        F("rto_charge_pct_of_freight", "num", False, ("rto percent", "rto charge percent", "rto %")),
    )),
    "invoices": Spec("Courier invoice lines", (
        F("invoice_id", "id", True, ("invoice no", "invoice number", "bill no", "bill number")),
        F("invoice_date", "date", True, ("bill date", "invoice dt")),
        F("courier", "str", True, ("courier name", "courier partner", "carrier", "courier id")),
        F("awb_number", "id", True, ("awb", "awb no", "tracking number", "tracking id", "waybill")),
        F("billed_weight_g", "num", True, ("billed weight", "charged weight", "chargeable weight", "charged weight g")),
        F("billed_zone", "zone", True, ("zone", "charged zone")),
        F("forward_freight_inr", "money", True, ("freight", "forward freight", "freight charge", "forward charge")),
        F("total_billed_inr", "money", True, ("total", "total amount", "total billed", "net amount", "invoice amount")),
        F("cod_charge_inr", "money", False, ("cod charge", "cod charges", "cod fee")),
        F("rto_freight_inr", "money", False, ("rto freight", "rto charge", "rto charges", "return freight")),
        F("gst_inr", "money", False, ("gst", "gst 18pct inr", "tax", "igst", "gst amount")),
        F("line_ref", "id", False, ("invoice line id", "line id", "line no", "sr no")),
    )),
    "remittances": Spec("COD remittance statement", (
        F("awb_number", "id", True, ("awb", "awb no", "tracking number", "tracking id", "waybill")),
        F("courier", "str", True, ("courier name", "courier partner", "carrier", "courier id")),
        F("remittance_date", "date", True, ("remitted on", "payment date", "remit date", "settlement date")),
        F("amount_remitted_inr", "money", True, ("amount", "cod amount", "remitted amount", "amount remitted",
                                                 "cod remitted")),
        F("utr_batch", "id", False, ("utr", "utr no", "utr number", "reference no", "batch id", "crf id")),
    )),
}
