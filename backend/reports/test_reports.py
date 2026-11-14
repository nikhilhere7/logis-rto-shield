"""Reports: the catalogue reflects real data, PDFs are real PDFs, and a merchant only ever gets its own."""
from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from audit.engine import run_audit
from core.models import Courier, Customer, InvoiceLine, Merchant, Order, Shipment, User
from ledger.build import rebuild_ledger
from reports.build import REPORTS

pytestmark = pytest.mark.django_db
KEYS = ["summary", "returns", "couriers", "audit", "customers"]


def client_for(merchant, name):
    user = User.objects.create_user(username=name, password="pw-12345678", merchant=merchant)
    c = APIClient()
    c.force_authenticate(user)
    return c


def seed(merchant, tag, parcels=6):
    """A small but complete store: orders, shipments with outcomes, and one AWB billed on two invoice lines."""
    courier = Courier.objects.create(merchant=merchant, code=f"{tag}C", name=f"{tag} Courier")
    customer = Customer.objects.create(merchant=merchant, external_id=f"{tag}-C1", name=f"{tag} <Buyer> & Co", pincode="411001")
    now = timezone.now()
    for i in range(parcels):
        order = Order.objects.create(merchant=merchant, external_id=f"{tag}-O{i}", customer=customer, order_ts=now - timedelta(days=40 + i),
                                     payment_mode="COD" if i % 2 else "Prepaid", gross_value=Decimal("1000"), order_value=Decimal("1000"), status="Shipped")
        Shipment.objects.create(merchant=merchant, order=order, courier=courier, awb_number=f"{tag}AWB{i}", pickup_ts=now - timedelta(days=39 + i),
                                pkg_weight_g=400, pkg_length_cm=10, pkg_breadth_cm=10, pkg_height_cm=5, delivery_attempts=1,
                                final_status="RTO Delivered" if i == 0 else "Delivered", delivered_ts=None if i == 0 else now - timedelta(days=36 + i))
    for n in (1, 2):  # the same AWB billed on two lines: the audit flags the second
        InvoiceLine.objects.create(merchant=merchant, courier=courier, invoice_id=f"{tag}-INV", line_ref=f"{tag}-L{n}", awb_number=f"{tag}AWB1",
                                   invoice_date=now.date(), billed_weight_g=500, billed_zone="A", forward_freight_inr=Decimal("100.00"),
                                   gst_inr=Decimal("18.00"), total_billed_inr=Decimal("118.00"))
    rebuild_ledger(merchant)
    run_audit(merchant)


def test_catalogue_lists_five_reports_and_marks_an_empty_store_unavailable():
    c = client_for(Merchant.objects.create(name="Empty"), "e")
    body = c.get("/api/reports/").json()
    assert [r["id"] for r in body] == KEYS == list(REPORTS)
    assert all(r["available"] is False and r["reason"] for r in body)
    for key in KEYS:  # asking for a report with no data behind it is refused with the reason, not answered with an empty PDF
        r = c.get(f"/api/reports/{key}.pdf")
        assert r.status_code == 400 and "Import" in r.json()["detail"]


def test_every_report_builds_a_real_pdf_for_a_store_with_data():
    m = Merchant.objects.create(name="Has Data")
    seed(m, "A")
    c = client_for(m, "a")
    assert all(r["available"] for r in c.get("/api/reports/").json())
    for key in KEYS:
        r = c.get(f"/api/reports/{key}.pdf")
        assert r.status_code == 200, key
        assert r["Content-Type"] == "application/pdf"
        today = timezone.localdate().strftime("%Y-%m-%d")
        assert r["Content-Disposition"] == f'attachment; filename="logis_has-data_{key}_{today}.pdf"'
        assert r["Cache-Control"] == "no-store, private"  # private business data: no browser or proxy may keep it
        assert r.content.startswith(b"%PDF-") and r.content.rstrip().endswith(b"%%EOF") and len(r.content) > 5000


def test_a_report_never_contains_another_merchants_data():
    from io import BytesIO

    from pypdf import PdfReader

    a, b = Merchant.objects.create(name="Alpha Store"), Merchant.objects.create(name="Beta Store")
    seed(a, "ALPHA")
    seed(b, "BETA", parcels=9)
    ca = client_for(a, "ua")
    for key in KEYS:
        text = " ".join(p.extract_text() for p in PdfReader(BytesIO(ca.get(f"/api/reports/{key}.pdf").content)).pages)
        assert "Alpha Store" in text, key
        assert "BETA" not in text and "Beta Store" not in text, key


def test_two_merchants_each_get_their_own_name_in_the_pdf_and_the_file_name():
    from io import BytesIO

    from pypdf import PdfReader

    a, b = Merchant.objects.create(name="Alpha Store"), Merchant.objects.create(name="Beta Store")
    seed(a, "ALPHA")
    seed(b, "BETA", parcels=9)
    ca, cb = client_for(a, "ua"), client_for(b, "ub")
    today = timezone.localdate().strftime("%Y-%m-%d")
    for key in KEYS:
        ra, rb = ca.get(f"/api/reports/{key}.pdf"), cb.get(f"/api/reports/{key}.pdf")
        text_a = " ".join(p.extract_text() for p in PdfReader(BytesIO(ra.content)).pages)
        text_b = " ".join(p.extract_text() for p in PdfReader(BytesIO(rb.content)).pages)
        assert "Alpha Store" in text_a and "Beta Store" not in text_a, key
        assert "Beta Store" in text_b and "Alpha Store" not in text_b, key
        assert f"logis_alpha-store_{key}_{today}.pdf" in ra["Content-Disposition"], key
        assert f"logis_beta-store_{key}_{today}.pdf" in rb["Content-Disposition"], key


def test_a_merchant_id_from_the_client_is_ignored():
    """The report is always for the logged-in user's merchant, whatever the request says."""
    from io import BytesIO

    from pypdf import PdfReader

    a, b = Merchant.objects.create(name="Alpha Store"), Merchant.objects.create(name="Beta Store")
    seed(a, "ALPHA")
    seed(b, "BETA")
    r = client_for(a, "ua").get(f"/api/reports/summary.pdf?merchant={b.id}&merchant_id={b.id}")
    text = " ".join(p.extract_text() for p in PdfReader(BytesIO(r.content)).pages)
    assert "Alpha Store" in text and "Beta Store" not in text
    assert "alpha-store" in r["Content-Disposition"]


def test_reports_need_a_login_and_reject_unknown_names():
    assert APIClient().get("/api/reports/").status_code == 401
    assert APIClient().get("/api/reports/summary.pdf").status_code == 401
    c = client_for(Merchant.objects.create(name="X"), "x")
    assert c.get("/api/reports/nonsense.pdf").status_code == 404


def test_building_a_report_writes_nothing():
    m = Merchant.objects.create(name="Read Only")
    seed(m, "R")
    before = (Order.objects.count(), Shipment.objects.count(), InvoiceLine.objects.count())
    c = client_for(m, "r")
    for key in KEYS:
        c.get(f"/api/reports/{key}.pdf")
    assert (Order.objects.count(), Shipment.objects.count(), InvoiceLine.objects.count()) == before
