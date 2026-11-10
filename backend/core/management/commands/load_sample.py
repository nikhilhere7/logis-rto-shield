from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from core import models as m

IST = ZoneInfo("Asia/Kolkata")
BATCH = 5000


def money(x):
    return Decimal(str(round(float(x), 2)))


def text(x):
    return "" if pd.isna(x) else str(x)


def ts(x):
    """CSV timestamps are naive IST. Store them timezone-aware."""
    return None if pd.isna(x) else pd.Timestamp(x).to_pydatetime().replace(tzinfo=IST)


def day(x):
    return None if pd.isna(x) else pd.Timestamp(x).date()


class Command(BaseCommand):
    help = "Load the Pune Threads sample dataset into the canonical tables"

    def add_arguments(self, parser):
        parser.add_argument("--dir", required=True)
        parser.add_argument("--merchant", default="Pune Threads")
        parser.add_argument("--reset", action="store_true", help="delete this merchant's data first")

    @transaction.atomic
    def handle(self, *args, **o):
        d = Path(o["dir"])
        if not (d / "orders.csv").exists():
            raise CommandError(f"orders.csv not found in {d}")
        read = lambda name: pd.read_csv(d / f"{name}.csv", dtype={"pincode": str})

        merchant, created = m.Merchant.objects.get_or_create(
            name=o["merchant"], defaults={"warehouse_pincode": "411001"})
        if not created:
            if not o["reset"]:
                raise CommandError("Merchant already loaded. Pass --reset to reload.")
            for model in [m.CodRemittance, m.InvoiceLine, m.TrackingEvent, m.Shipment, m.OrderItem, m.Order,
                          m.Customer, m.RateCard, m.Courier, m.Product, m.PincodeZone]:
                model.objects.for_merchant(merchant).delete()
        M = dict(merchant=merchant)

        # reference data
        m.PincodeZone.objects.bulk_create([
            m.PincodeZone(**M, pincode=r.pincode, city=r.city, state=r.state, zone=r.zone,
                          city_tier=r.city_tier, cod_serviceable=bool(r.cod_serviceable))
            for r in read("pincodes").itertuples()])
        m.Product.objects.bulk_create([
            m.Product(**M, sku=r.sku, name=r.product_name, category=r.category, mrp=money(r.mrp),
                      dead_weight_g=r.dead_weight_g, length_cm=r.length_cm, breadth_cm=r.breadth_cm,
                      height_cm=r.height_cm, launch_date=day(r.launch_date))
            for r in read("products").itertuples()])
        m.Courier.objects.bulk_create([
            m.Courier(**M, code=r.courier_id, name=r.courier_name) for r in read("couriers").itertuples()])
        courier = {c.code: c.id for c in m.Courier.objects.for_merchant(merchant)}
        product = {p.sku: p.id for p in m.Product.objects.for_merchant(merchant)}
        m.RateCard.objects.bulk_create([
            m.RateCard(**M, courier_id=courier[r.courier_id], zone=r.zone, first_500g_inr=money(r.first_500g_inr),
                       addl_500g_inr=money(r.addl_500g_inr), cod_fee_pct=money(r.cod_fee_pct),
                       cod_min_inr=money(r.cod_min_inr), rto_charge_pct_of_freight=money(r.rto_charge_pct_of_freight))
            for r in read("rate_card").itertuples()])

        # customers and orders
        m.Customer.objects.bulk_create([
            m.Customer(**M, external_id=r.customer_id, name=text(r.customer_name), pincode=r.pincode,
                       address_line=text(r.address_line), signup_date=day(r.signup_date),
                       acquisition_channel=text(r.acquisition_channel), phone_verified=bool(r.phone_verified))
            for r in read("customers").itertuples()], batch_size=BATCH)
        customer = dict(m.Customer.objects.for_merchant(merchant).values_list("external_id", "id"))

        m.Order.objects.bulk_create([
            m.Order(**M, external_id=r.order_id, customer_id=customer[r.customer_id], order_ts=ts(r.order_ts),
                    sales_channel=text(r.sales_channel), payment_mode=r.payment_mode,
                    prepaid_gateway=text(r.prepaid_gateway), gross_value=money(r.gross_value),
                    discount_inr=money(r.discount_inr), shipping_fee_inr=money(r.shipping_fee_inr),
                    order_value=money(r.order_value), status=r.order_status)
            for r in read("orders").itertuples()], batch_size=BATCH)
        order = dict(m.Order.objects.for_merchant(merchant).values_list("external_id", "id"))

        m.OrderItem.objects.bulk_create([
            m.OrderItem(**M, order_id=order[r.order_id], product_id=product[r.sku], qty=r.qty,
                        unit_price=money(r.unit_price), line_total=money(r.line_total))
            for r in read("order_items").itertuples()], batch_size=BATCH)

        # shipping
        m.Shipment.objects.bulk_create([
            m.Shipment(**M, awb_number=r.awb_number, order_id=order[r.order_id], courier_id=courier[r.courier_id],
                       pickup_ts=ts(r.pickup_ts), pkg_weight_g=r.pkg_weight_g, pkg_length_cm=r.pkg_length_cm,
                       pkg_breadth_cm=r.pkg_breadth_cm, pkg_height_cm=r.pkg_height_cm,
                       promised_delivery_date=day(r.promised_delivery_date), delivery_attempts=r.delivery_attempts,
                       last_ndr_reason=text(r.last_ndr_reason), final_status=r.final_status,
                       delivered_ts=ts(r.delivered_ts), rto_initiated_ts=ts(r.rto_initiated_ts),
                       rto_received_ts=ts(r.rto_received_ts), rto_condition=text(r.rto_condition))
            for r in read("shipments").itertuples()], batch_size=BATCH)
        shipment = dict(m.Shipment.objects.for_merchant(merchant).values_list("awb_number", "id"))

        m.TrackingEvent.objects.bulk_create([
            m.TrackingEvent(**M, shipment_id=shipment[r.awb_number], event_ts=ts(r.event_ts), status=r.status,
                            location=text(r.location))
            for r in read("tracking_events").itertuples()], batch_size=BATCH)

        # money. shipment is looked up with .get() because a courier can bill an AWB we don't know
        m.InvoiceLine.objects.bulk_create([
            m.InvoiceLine(**M, line_ref=r.invoice_line_id, invoice_id=r.invoice_id, invoice_date=day(r.invoice_date),
                          courier_id=courier[r.courier_id], awb_number=r.awb_number,
                          shipment_id=shipment.get(r.awb_number), billed_weight_g=r.billed_weight_g,
                          billed_zone=r.billed_zone, forward_freight_inr=money(r.forward_freight_inr),
                          cod_charge_inr=money(r.cod_charge_inr), rto_freight_inr=money(r.rto_freight_inr),
                          gst_inr=money(r.gst_18pct_inr), total_billed_inr=money(r.total_billed_inr))
            for r in read("courier_invoices").itertuples()], batch_size=BATCH)
        m.CodRemittance.objects.bulk_create([
            m.CodRemittance(**M, utr_batch=r.utr_batch, courier_id=courier[r.courier_id], awb_number=r.awb_number,
                            shipment_id=shipment.get(r.awb_number), remittance_date=day(r.remittance_date),
                            amount_remitted_inr=money(r.amount_remitted_inr))
            for r in read("cod_remittances").itertuples()], batch_size=BATCH)

        self.stdout.write(self.style.SUCCESS(f"Loaded merchant '{merchant.name}'"))
        for model in [m.PincodeZone, m.Product, m.Courier, m.RateCard, m.Customer, m.Order, m.OrderItem,
                      m.Shipment, m.TrackingEvent, m.InvoiceLine, m.CodRemittance]:
            self.stdout.write(f"  {model.__name__:<14} {model.objects.for_merchant(merchant).count():>7,}")
        ships = m.Shipment.objects.for_merchant(merchant)
        rto = ships.filter(final_status="RTO Delivered").count() / ships.count() * 100
        self.stdout.write(f"  RTO rate       {rto:.1f}%")