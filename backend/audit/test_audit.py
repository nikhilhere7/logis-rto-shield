import csv
import io
from datetime import date

import pytest
from rest_framework.test import APIClient

from audit.engine import run_audit
from audit.models import AuditFinding
from core.models import CodRemittance, Courier, Merchant, User
from ingestion.test_ingestion import ORDERS, client, run  # noqa: F401

# A1 = COD Rs 1299, A2 = Prepaid Rs 799, both to 411001 (zone A). Both parcels delivered, one 500g slab each.
SHIPMENTS = """AWB,Order Number,Courier Name,Pickup Date,Weight (kg),Status,Delivered Date
X100,A1,FastShip,2025-03-02,0.45,Delivered,2025-03-04
X101,A2,FastShip,2025-03-03,0.30,Delivered,2025-03-05
"""
ZONES = """Pin Code,Zone,City,COD Available
411001,A,Pune,Yes
"""
RATES = """Courier Name,Zone,First 500g,Additional 500g,COD %,COD Minimum
FastShip,A,30,25,2,30
FastShip,B,40,35,2,30
"""
INVOICE_HEADER = ("Invoice No,Bill Date,Courier Name,AWB,Charged Weight,Zone,"
                  "Freight,COD Charges,RTO Charges,GST,Total Amount\n")

# X100 correct ((30 + 30 COD) x 1.18 = 70.80), then billed again; X101 billed 2 slabs; GHOST1 never shipped
BILLING_ERRORS = INVOICE_HEADER + """INV-1,31/03/2025,FastShip,X100,450,A,30,30,0,10.80,70.80
INV-1,31/03/2025,FastShip,X100,450,A,30,30,0,10.80,70.80
INV-1,31/03/2025,FastShip,X101,1000,A,55,0,0,9.90,64.90
INV-1,31/03/2025,FastShip,GHOST1,500,A,30,0,0,5.40,35.40
"""
# X100 billed at zone B rates; delivered prepaid X101 billed RTO and COD fees
WRONG_ZONE_AND_NOT_DUE = INVOICE_HEADER + """INV-2,31/03/2025,FastShip,X100,450,B,40,30,0,12.60,82.60
INV-2,31/03/2025,FastShip,X101,300,A,30,30,30,16.20,106.20
"""
SHORT_PAID = """AWB,Courier Name,Payment Date,COD Amount,UTR No
X100,FastShip,10/03/2025,999,UTR1
"""


@pytest.fixture
def shipped(client):
    for kind, content in [("orders", ORDERS), ("shipments", SHIPMENTS),
                          ("pincode_zones", ZONES), ("rate_card", RATES)]:
        run(client, kind, content)
    return client


def findings(merchant):
    return {(f.kind, f.awb_number): f for f in AuditFinding.objects.for_merchant(merchant)}


def amounts(f):
    return str(f.billed_inr), str(f.expected_inr), str(f.claim_inr)


def statement_on(merchant, day):
    """A remittance statement for some other parcel: sets the latest statement date, pays nothing for X100."""
    CodRemittance.objects.filter(merchant=merchant, awb_number="Z999").delete()
    courier = merchant.couriers.get(name="FastShip")
    CodRemittance.objects.create(merchant=merchant, courier=courier, awb_number="Z999", utr_batch="UTR9",
                                 remittance_date=day, amount_remitted_inr=10)


def test_invoice_billing_errors(shipped):
    run(shipped, "invoices", BILLING_ERRORS)
    stats = run_audit(shipped.merchant)
    f = findings(shipped.merchant)

    assert set(f) == {("duplicate_line", "X100"), ("weight_inflated", "X101"), ("unknown_awb", "GHOST1")}
    assert str(f["duplicate_line", "X100"].claim_inr) == "70.80"
    assert amounts(f["weight_inflated", "X101"]) == ("64.90", "35.40", "29.50")
    assert str(f["unknown_awb", "GHOST1"].claim_inr) == "35.40"
    assert stats["lines_checked"] == 4 and stats["claim_total_inr"] == 135.7


def test_cod_short_payment(shipped):
    run(shipped, "remittances", SHORT_PAID)
    run_audit(shipped.merchant)
    f = findings(shipped.merchant)

    assert set(f) == {("cod_short_paid", "X100")}
    assert amounts(f["cod_short_paid", "X100"]) == ("999.00", "1299.00", "300.00")


def test_wrong_zone_and_charges_not_due(shipped):
    run(shipped, "invoices", WRONG_ZONE_AND_NOT_DUE)
    run_audit(shipped.merchant)
    f = findings(shipped.merchant)

    assert set(f) == {("wrong_zone", "X100"), ("rto_charge_not_due", "X101")}
    assert amounts(f["wrong_zone", "X100"]) == ("82.60", "70.80", "11.80")
    # RTO outranks the COD fee: one finding per line, claiming the whole overcharge
    assert amounts(f["rto_charge_not_due", "X101"]) == ("106.20", "35.40", "70.80")


def test_audit_api_and_dispute_csv(shipped):
    run(shipped, "invoices", BILLING_ERRORS)
    run(shipped, "remittances", SHORT_PAID)

    assert shipped.post("/api/audit/run/").status_code == 200

    summary = shipped.get("/api/audit/summary/").json()
    assert summary["billing_overcharge_inr"] == 135.7
    assert summary["cod_missing_inr"] == 300.0
    assert summary["total_recoverable_inr"] == 435.7

    all_findings = shipped.get("/api/audit/findings/").json()
    assert len(all_findings) == 4

    weight = shipped.get("/api/audit/findings/?kind=weight_inflated").json()
    assert [r["awb_number"] for r in weight] == ["X101"]
    assert shipped.get("/api/audit/findings/?kind=not_a_kind").status_code == 400

    r = shipped.get("/api/audit/disputes.csv")
    assert r.status_code == 200 and r["Content-Type"].startswith("text/csv")
    body = b"".join(r.streaming_content) if r.streaming else r.content
    rows = list(csv.reader(io.StringIO(body.decode("utf-8-sig"))))
    text = "\n".join(",".join(row) for row in rows)
    for awb in ["X100", "X101", "GHOST1"]:
        assert awb in text
    assert "Billed weight higher than the parcel" in text
    assert "Same AWB billed more than once" in text


def test_cod_grace_period(shipped):
    m = shipped.merchant          # X100: COD Rs 1299, delivered 2025-03-04, nothing remitted

    statement_on(m, date(2025, 2, 24))          # delivered 8 days AFTER the latest statement
    stats = run_audit(m)
    assert findings(m) == {} and stats["cod_pending_not_yet_due"] == 1

    statement_on(m, date(2025, 3, 30))          # delivered 26 days before the latest statement
    run_audit(m)
    assert amounts(findings(m)["cod_not_remitted", "X100"]) == ("0.00", "1299.00", "1299.00")

    # the default 21-day grace: exactly 21 days is overdue, 20 days is still pending
    statement_on(m, date(2025, 3, 25))
    assert run_audit(m)["by_kind"] == {"cod_not_remitted": 1}
    statement_on(m, date(2025, 3, 24))
    stats = run_audit(m)
    assert stats["by_kind"] == {} and stats["cod_pending_not_yet_due"] == 1


def test_tenant_isolation(shipped):
    other_user = User.objects.create_user("other", password="x",
                                          merchant=Merchant.objects.create(name="Other Merchant"))
    other = APIClient()
    other.force_authenticate(other_user)
    other.merchant = other_user.merchant
    for kind, content in [("orders", ORDERS), ("shipments", SHIPMENTS), ("pincode_zones", ZONES),
                          ("rate_card", RATES), ("invoices", WRONG_ZONE_AND_NOT_DUE)]:
        run(other, kind, content)
    run(shipped, "invoices", BILLING_ERRORS)

    run_audit(other.merchant)
    theirs = set(AuditFinding.objects.for_merchant(other.merchant).values_list("id", flat=True))
    assert len(theirs) == 2

    run_audit(shipped.merchant)
    run_audit(shipped.merchant)     # rebuilding ours twice never touches theirs
    assert set(AuditFinding.objects.for_merchant(other.merchant).values_list("id", flat=True)) == theirs

    ours = AuditFinding.objects.for_merchant(shipped.merchant)
    assert ours.count() == 3 and not ours.filter(id__in=theirs).exists()
    assert {f.kind for f in AuditFinding.objects.for_merchant(other.merchant)} == {"wrong_zone", "rto_charge_not_due"}


def test_findings_pages_are_stable_when_claims_tie(client):
    m = client.merchant
    courier = Courier.objects.create(merchant=m, code="FS", name="FastShip")
    claims = ["50.00", "20.00", "20.00", "20.00", "20.00", "20.00", "10.00"]   # five-way tie in the middle
    for i, claim in enumerate(claims):
        AuditFinding.objects.create(merchant=m, kind="duplicate_line", courier=courier, courier_name="FastShip",
                                    awb_number=f"T{i}", billed_inr=claim, expected_inr=0, claim_inr=claim,
                                    detail="tie test")
    expected = list(AuditFinding.objects.for_merchant(m).order_by("-claim_inr", "id").values_list("id", flat=True))

    pages = [client.get(f"/api/audit/findings/?limit=2&offset={o}").json() for o in range(0, 8, 2)]
    paged = [r["id"] for page in pages for r in page]
    assert paged == expected                       # same order, nothing skipped, nothing repeated
    assert len(set(paged)) == len(claims)
    assert [r["id"] for r in client.get("/api/audit/findings/").json()] == expected   # repeat call, same order
