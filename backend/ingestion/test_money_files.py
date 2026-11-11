import pytest

from core.models import CodRemittance, InvoiceLine, PincodeZone, RateCard
from ingestion.test_ingestion import ORDERS, SHIPMENTS, client, run  # noqa: F401


ZONES = """Pin Code,Zone,City,COD Available
411001,zone a,Pune,Yes
400001,B,Mumbai,No
411001,C,Pune,Yes
12345,A,Nowhere,Yes
"""

RATES = """Courier Name,Zone,First 500g,Additional 500g,COD %,COD Minimum
FastShip,A,30,25,2,30
FastShip,B,40,35,2,30
FastShip,B,45,35,2,30
FastShip,C,0,35,2,30
"""

INVOICES = """Invoice No,Bill Date,Courier Name,AWB,Charged Weight,Zone,Freight,COD Charges,GST,Total Amount
INV-1,31/03/2025,FastShip,X100,0.5,A,30,30,10.80,70.80
INV-1,31/03/2025,FastShip,X100,0.5,A,30,30,10.80,70.80
INV-1,31/03/2025,FastShip,GHOST1,1.0,B,75,0,13.50,88.50
INV-1,31/03/2025,FastShip,X101,0.5,A,30,0,5.40,99.00
INV-1,31/03/2025,FastShip,X101,0.5,A,-30,0,5.40,-24.60
"""

REMITS = """AWB,Courier Name,Payment Date,COD Amount,UTR No
X100,FastShip,10/03/2025,"1,299",UTR1
X100,FastShip,10/03/2025,"1,299",UTR1
X100,FastShip,12/03/2025,0,UTR2
"""


@pytest.fixture
def loaded(client):
    run(client, "orders", ORDERS)
    run(client, "shipments", SHIPMENTS)
    return client


def rules(v, key="errors"):
    return {e["rule"]: e["count"] for e in v["quality_report"][key]}


def test_pincode_zones(loaded):
    v, c = run(loaded, "pincode_zones", ZONES)

    assert rules(v) == {
        "invalid_pincode": 1,
        "duplicate_in_file": 1,
    }

    z = PincodeZone.objects.get(pincode="411001")
    assert z.zone == "A" and z.cod_serviceable is True

    assert PincodeZone.objects.get(pincode="400001").cod_serviceable is False


def test_rate_card(loaded):
    v, c = run(loaded, "rate_card", RATES)

    assert rules(v) == {
        "duplicate_in_file": 1,
        "rate_not_positive": 1,
    }

    assert RateCard.objects.count() == 2

    assert str(
        RateCard.objects.get(zone="B").first_500g_inr
    ) == "40.00"

    assert RateCard.objects.first().courier.name == "FastShip"


def test_invoices_keep_duplicates_and_unknown_awbs(loaded):
    v, c = run(loaded, "invoices", INVOICES)

    assert rules(v) == {"negative_amount": 1}

    w = rules(v, "warnings")

    assert w["awb_not_in_shipments"] == 1
    assert w["total_does_not_match_components"] == 1
    assert w["weight_looked_like_kg_converted_to_g"] == 5

    assert InvoiceLine.objects.filter(awb_number="X100").count() == 2

    ghost = InvoiceLine.objects.get(awb_number="GHOST1")

    assert ghost.shipment is None
    assert ghost.billed_weight_g == 1000

    assert c["load_result"] == {
        "created": 4,
        "updated": 0,
        "linked_to_shipment": 3,
    }

    _, again = run(loaded, "invoices", INVOICES)

    assert again["load_result"]["created"] == 0
    assert InvoiceLine.objects.count() == 4


def test_remittances_skip_what_is_already_loaded(loaded):
    v, c = run(loaded, "remittances", REMITS)

    assert rules(v) == {
        "amount_not_positive": 1,
        "duplicate_in_file": 1,
    }

    assert c["load_result"] == {
        "created": 1,
        "skipped_already_loaded": 0,
    }

    _, again = run(loaded, "remittances", REMITS)

    assert again["load_result"]["created"] == 0
    assert again["load_result"]["skipped_already_loaded"] == 1

    r = CodRemittance.objects.get()

    assert str(r.amount_remitted_inr) == "1299.00"
    assert r.shipment.awb_number == "X100"
