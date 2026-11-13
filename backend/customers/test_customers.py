import json

import pandas as pd
import pytest
from rest_framework.test import APIClient

from core.models import Customer, Merchant, Order, Shipment, User
from customers.profiles import segment_of
from ingestion.test_ingestion import ORDERS, SHIPMENTS, client, run  # noqa: F401
from ledger.models import ShipmentLedger
from ml.score import repeat_returner

# two more customers who ordered once and have no parcels yet: identical sort keys, so only
# the customer_id tie-break decides their order
NO_PARCELS_YET = """Order Number,Created At,Customer ID,Customer Name,Shipping Zip,Payment Method,Total
B1,2025-03-05 10:00:00,CU-B,Bina Rao,411002,COD,500
B2,2025-03-05 10:00:00,CU-C,Chetan Rao,411002,COD,500
"""


@pytest.fixture
def shop(client):  # noqa: F811
    run(client, "orders", ORDERS)          # one customer, two orders: A1 (COD) and A2 (prepaid)
    run(client, "shipments", SHIPMENTS)    # A1 delivered, A2 returned
    return client


def no_secrets(body):
    """No phone number, phone hash or field about them anywhere in a response."""
    text = json.dumps(body)
    return "phone" not in text.lower().replace("by phone", "") and "9876543210" not in text and "NaN" not in text


def test_segments():
    parcels = pd.Series([0, 1, 1, 18, 12, 6, 3, 4])
    returned = pd.Series([0, 0, 1, 6, 2, 0, 1, 1])
    assert segment_of(parcels, returned).tolist() == [
        "No history", "New", "Returned first order", "Repeat returner", "Regular", "Loyal", "Regular", "Regular"]


def test_repeat_returner_means_the_same_here_and_in_the_risk_checker():
    for parcels, returned in [(18, 6), (12, 2), (2, 2), (1, 1), (10, 3), (7, 2)]:
        row = pd.Series({"cust_prior_rto": returned, "cust_prior_delivered": parcels - returned})
        ours = segment_of(pd.Series([parcels]), pd.Series([returned])).iloc[0] == "Repeat returner"
        assert ours == repeat_returner(row), (parcels, returned)


def test_list_search_and_sort(shop):
    r = shop.get("/api/customers/").json()
    assert r["count"] == 1
    c = r["results"][0]
    assert (c["orders"], c["parcels"], c["delivered"], c["returned"], c["rto_rate_pct"]) == (2, 2, 1, 1, 50.0)
    assert c["segment"] == "Regular" and c["payment_preference"] == "Mixed"
    assert c["delivered_value_inr"] == 1299.0 and c["returned_value_inr"] == 799.0 and c["last_order"] == "2025-03-02"
    assert no_secrets(r)
    assert shop.get("/api/customers/?search=asha").json()["count"] == 1
    assert shop.get("/api/customers/?search=411001").json()["count"] == 1
    assert shop.get("/api/customers/?search=nobody").json() == {"count": 0, "results": []}
    assert shop.get("/api/customers/?segment=Loyal").json()["count"] == 0
    assert shop.get("/api/customers/?segment=Regular").json()["count"] == 1
    assert shop.get("/api/customers/?segment=VIP").status_code == 400
    assert shop.get("/api/customers/?sort=height").status_code == 400
    for bad in ["limit=501", "limit=-1", "limit=ten", "offset=-5"]:
        assert shop.get(f"/api/customers/?{bad}").status_code == 400, bad
    for sort in ["recent", "returned", "rto_rate", "orders", "value"]:
        assert shop.get(f"/api/customers/?sort={sort}").status_code == 200, sort
    assert shop.get("/api/customers/?offset=1").json() == {"count": 1, "results": []}

    # ties are broken by customer_id, so pages are stable and line up exactly with the full list
    run(shop, "orders", NO_PARCELS_YET)
    full = shop.get("/api/customers/?sort=orders").json()
    refs = [x["customer_id"] for x in full["results"]]
    first_ids = sorted(Customer.objects.filter(external_id__in=["CU-B", "CU-C"]).values_list("id", "external_id"))
    assert full["count"] == 3 and refs[1:] == [ref for _, ref in first_ids]
    paged = [shop.get(f"/api/customers/?sort=orders&limit=1&offset={o}").json()["results"][0]["customer_id"]
             for o in range(3)]
    assert paged == refs and shop.get("/api/customers/?sort=orders").json() == full
    # customers with orders but no parcels: no NaN, no division errors, a null rate
    newcomers = shop.get("/api/customers/?segment=No history").json()
    assert newcomers["count"] == 2 and all(x["rto_rate_pct"] is None and x["payment_preference"] == "Unknown"
                                           for x in newcomers["results"])
    assert no_secrets(newcomers)


def test_profile_by_phone(shop):
    p = shop.get("/api/customers/lookup/?phone=%2B91 98765 43210").json()
    assert p["name"] == "Asha Patil" and p["segment"] == "Regular" and p["advice"]
    assert p["payment_behaviour"] == {"COD": {"parcels": 1, "returned": 0, "rto_rate_pct": 0.0},
                                      "Prepaid": {"parcels": 1, "returned": 1, "rto_rate_pct": 100.0}}
    assert [(o["order_id"], o["outcome"]) for o in p["recent_orders"]] == [("A2", "RTO Delivered"), ("A1", "Delivered")]
    assert "phone" not in p and "phone_hash" not in p and no_secrets(p)
    assert shop.get("/api/customers/lookup/?customer_id=" + p["customer_id"]).json()["orders"] == 2
    # customer_id wins over phone when both are sent
    both = shop.get("/api/customers/lookup/?customer_id=" + p["customer_id"] + "&phone=9000000000")
    assert both.status_code == 200 and both.json()["name"] == "Asha Patil"
    assert shop.get("/api/customers/lookup/?phone=9000000000").status_code == 404
    assert shop.get("/api/customers/lookup/?customer_id=NOPE").status_code == 404
    assert shop.get("/api/customers/lookup/?phone=123").status_code == 400
    bad = shop.get("/api/customers/lookup/?phone=1234567890")
    assert bad.status_code == 400 and bad.json() == {
        "phone": "Enter a 10-digit mobile number starting with 6, 7, 8 or 9."}
    missing = shop.get("/api/customers/lookup/")
    assert missing.status_code == 400 and missing.json() == {"detail": "Pass customer_id or phone."}


def test_segment_summary(shop):
    s = shop.get("/api/customers/segments/").json()
    assert len(s) == 1 and s[0]["segment"] == "Regular"
    assert (s[0]["customers"], s[0]["parcels"], s[0]["rto_rate_pct"], s[0]["revenue_share_pct"]) == (1, 2, 50.0, 100.0)
    assert "NaN" not in json.dumps(s)


def test_another_merchant_cannot_look_up_my_customer(shop):
    before = [m.objects.count() for m in (Order, Customer, Shipment, ShipmentLedger)]
    asha = shop.get("/api/customers/").json()["results"][0]["customer_id"]

    other = APIClient()
    other.force_authenticate(User.objects.create_user("spy", password="x", merchant=Merchant.objects.create(name="O")))
    assert other.get("/api/customers/lookup/?phone=9876543210").status_code == 404
    assert other.get("/api/customers/lookup/?customer_id=" + asha).status_code == 404
    assert other.get("/api/customers/").json() == {"count": 0, "results": []}
    assert other.get("/api/customers/segments/").json() == []

    loner = APIClient()
    loner.force_authenticate(User.objects.create_user("loner", password="x"))      # no merchant
    anonymous = APIClient()
    for path in ["/api/customers/", "/api/customers/segments/", "/api/customers/lookup/?customer_id=" + asha]:
        assert loner.get(path).status_code == 403, path
        assert anonymous.get(path).status_code in (401, 403), path

    # the M5 Risk Checker still answers, single and batch
    order = {"order_value": 500, "payment_mode": "COD", "pincode": "411001", "phone": "9876543210"}
    assert shop.post("/api/risk/score/", order, format="json").json()["customer"]["known"] is True
    assert shop.post("/api/risk/score-batch/", {"orders": [order]}, format="json").json()["count"] == 1

    assert [m.objects.count() for m in (Order, Customer, Shipment, ShipmentLedger)] == before   # reads only
