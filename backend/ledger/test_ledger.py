from decimal import Decimal

import pytest
from rest_framework.test import APIClient

from core.models import Merchant, User
from ingestion.test_ingestion import ORDERS, SHIPMENTS, client, run  # noqa: F401
from ingestion.test_money_files import INVOICES, RATES, REMITS, ZONES
from ledger import metrics
from ledger.build import rebuild_ledger
from ledger.models import ShipmentLedger


@pytest.fixture
def ledgered(client):
    """All six datasets committed; every commit rebuilds the ledger, so the last one sees everything."""
    run(client, "orders", ORDERS)
    run(client, "shipments", SHIPMENTS)
    run(client, "pincode_zones", ZONES)
    run(client, "rate_card", RATES)
    run(client, "invoices", INVOICES)
    _, c = run(client, "remittances", REMITS)
    assert c["ledger"]["rows"] == 2
    return client


@pytest.fixture
def other_client(db):
    other = User.objects.create_user("other", password="x", merchant=Merchant.objects.create(name="Other"))
    c = APIClient()
    c.force_authenticate(other)
    c.merchant = other.merchant
    return c


def test_one_row_per_awb_with_everything_merged(ledgered):
    rows = ShipmentLedger.objects.for_merchant(ledgered.merchant)
    assert rows.count() == 2          # two invoice lines and duplicate remittances do not multiply rows

    x100 = rows.get(awb_number="X100")
    assert x100.order_ref == "A1" and x100.payment_mode == "COD"
    assert x100.zone == "A" and x100.city == "Pune"
    assert x100.is_delivered and x100.is_first_order
    assert x100.weight_slabs == 1
    assert x100.invoice_lines == 2
    assert x100.billed_total_inr == Decimal("141.60")
    assert x100.cod_due_inr == Decimal("1299.00")
    assert x100.cod_remitted_inr == Decimal("1299.00")
    assert x100.days_pickup_to_delivery == Decimal("2.00")
    assert x100.on_time is None       # no promised date in the file

    x101 = rows.get(awb_number="X101")
    assert x101.is_rto
    assert x101.prior_orders == 1 and not x101.is_first_order
    assert x101.cod_due_inr == 0
    assert x101.delivered_ts is None


def test_metrics(ledgered):
    m = ledgered.merchant

    o = metrics.overview(m)
    assert o["total_orders"] == 2 and o["total_shipments"] == 2
    assert o["rto_rate_pct"] == 50.0
    assert o["cod_share_pct"] == 50.0
    assert o["delivered_revenue_inr"] == 1299.0
    assert o["rto_order_value_inr"] == 799.0
    assert o["total_courier_billed_inr"] == 240.6     # 141.60 + 99.00; GHOST1 is not one of our shipments
    assert "total_courier_billed" not in o

    rto = {r["payment_mode"]: r["rto_rate_pct"] for r in metrics.rto_by(m, "payment_mode")}
    assert rto == {"COD": 0.0, "Prepaid": 100.0}

    assert metrics.monthly(m)[0]["month"] == "2025-03"
    assert metrics.monthly(m)[0]["rto_rate_pct"] == 50.0

    [cod] = metrics.cod_summary(m)
    assert cod == {"courier": "FastShip", "cod_delivered_shipments": 1, "cod_due_inr": 1299.0,
                   "cod_remitted_inr": 1299.0, "gap_inr": 0.0, "not_remitted": 0, "short_paid": 0}

    # 1 of 2 shipments delivered, on the first attempt: 100% of delivered, not 50% of all shipments
    [fastship] = metrics.delivery_by(m, "courier")
    assert fastship["delivered_rate_pct"] == 50.0
    assert fastship["first_attempt_delivery_pct"] == 100.0


def test_api_and_tenant_isolation(ledgered, other_client):
    assert ledgered.get("/api/metrics/overview/").json()["total_shipments"] == 2

    rto = ledgered.get("/api/metrics/rto/?by=courier")
    assert rto.status_code == 200 and [r["courier"] for r in rto.json()] == ["FastShip"]

    assert ledgered.get("/api/metrics/rto/?by=merchant_id").status_code == 400
    assert ledgered.get("/api/metrics/rto/?min_shipments=abc").status_code == 400

    delivery = ledgered.get("/api/metrics/delivery/?by=zone").json()
    assert [r["zone"] for r in delivery] == ["A"]

    # the other merchant sees nothing of ours, and rebuilding their ledger leaves ours alone
    assert other_client.get("/api/metrics/overview/").json()["total_shipments"] == 0
    assert other_client.get("/api/metrics/rto/?by=courier").json() == []
    assert other_client.get("/api/metrics/cod/").json() == []
    assert other_client.post("/api/ledger/rebuild/").json() == {"rows": 0}
    assert ShipmentLedger.objects.for_merchant(ledgered.merchant).count() == 2
    assert rebuild_ledger(ledgered.merchant)["rows"] == 2
