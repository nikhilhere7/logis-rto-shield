import json
import math

import pytest
from rest_framework.test import APIClient

from core.models import Customer, Merchant, Order, Shipment, User
from ingestion.test_ingestion import ORDERS, SHIPMENTS, client, run  # noqa: F401
from ingestion.validators import hash_phone
from ledger.models import ShipmentLedger
from ml import score
from ml.models import RiskModel
from ml.test_ml import m4_model, synthetic
from ml.train import RISK_BANDS, fit

# The fixture merchant has one customer (phone 98765 43210) with two orders to 411001:
# A1 was delivered on 4 Mar, A2 came back (its outcome counts as known on 13 Mar). By 1 April both are known.
ASHA = "9876543210"
NEW_COD = {"order_id": "N1", "order_value": 500, "payment_mode": "cash on delivery", "pincode": "411001",
           "address": "home", "phone": "9000000001", "order_ts": "2025-04-01T14:00:00+05:30"}


@pytest.fixture
def shop(client):  # noqa: F811
    run(client, "orders", ORDERS)
    run(client, "shipments", SHIPMENTS)
    run(client, "pincode_zones", "Pin Code,Zone,City\n411001,A,Pune\n")
    return client


def table_counts():
    return [m.objects.count() for m in (Order, Customer, Shipment, ShipmentLedger, RiskModel)]


def no_phone_in(body, phone):
    text = json.dumps(body)
    return phone not in text and hash_phone(phone) not in text and hash_phone(phone)[:16] not in text


def test_rules_score_a_merchant_that_has_no_model(shop, monkeypatch):
    m4_model(shop.merchant)                         # an active model on the old features: must be ignored
    monkeypatch.setattr(score, "load_artifact", lambda run: pytest.fail("a stale model was loaded"))
    before = table_counts()

    r = shop.post("/api/risk/score/", NEW_COD, format="json").json()

    # -3.0 base +1.9 COD +0.7 first-time COD +0.5 no house number +0.7 short address = 0.8
    p = 1 / (1 + math.exp(-0.8))
    assert r["scored_by"] == "rules"
    assert r["risk_probability"] == round(p, 3) == 0.690 and r["risk_pct"] == 69.0
    assert r["risk_category"] == "Very high" and r["policy_note"] == ""
    assert r["recommended_action"] == ("Do not ship as COD. Ask the customer to pay online first."
                                       " Ask for a complete address with house number and landmark.")
    assert r["contributing_factors"] == [
        {"factor": "Cash on delivery", "value": "Yes", "effect": "raises risk", "strength": 1.9},
        {"factor": "First-time customer paying COD", "value": "Yes", "effect": "raises risk", "strength": 0.7},
        {"factor": "Very short address", "value": "Yes", "effect": "raises risk", "strength": 0.7},
        {"factor": "Address has no house or flat number", "value": "Yes", "effect": "raises risk", "strength": 0.5},
    ]
    assert r["order_id"] == "N1"
    assert r["customer"] == {"known": False, "previous_orders": 0, "delivered": 0, "returned": 0}
    assert r["confidence"] == {"level": "Low", "pincode_parcels_seen": 2, "customer_orders_seen": 0}
    assert r["destination"]["city"] == "Pune" and r["destination"]["zone"] == "A"
    assert no_phone_in(r, NEW_COD["phone"])
    assert table_counts() == before                 # scoring reads history and writes nothing


def test_customer_is_recognised_by_phone_in_any_format(shop):
    r = shop.post("/api/risk/score/", {**NEW_COD, "phone": "+91 98765 43210"}, format="json").json()

    assert r["customer"] == {"known": True, "previous_orders": 2, "delivered": 1, "returned": 1}
    assert r["confidence"]["customer_orders_seen"] == 2
    # a known customer is no longer "first-time COD", and having returned a parcel now counts against them
    factors = {f["factor"] for f in r["contributing_factors"]}
    assert "First-time customer paying COD" not in factors and "Customer has returned parcels before" in factors
    assert no_phone_in(r, ASHA)


def test_bad_input_is_refused_with_a_reason(shop):
    r = shop.post("/api/risk/score/", {"order_value": -10, "payment_mode": "bitcoin", "pincode": "012345",
                                       "phone": "12345"}, format="json")
    assert r.status_code == 400
    errors = r.json()
    assert set(errors) == {"order_value", "payment_mode", "pincode", "phone"}
    assert errors["payment_mode"] == ["Use COD or Prepaid."]
    assert errors["pincode"] == ["Enter a 6-digit pincode."]
    assert errors["phone"] == ["Enter a 10-digit mobile number starting with 6, 7, 8 or 9."]

    assert shop.post("/api/risk/score/", {"order_value": 500}, format="json").json().keys() == {"payment_mode",
                                                                                              "pincode"}
    assert shop.post("/api/risk/score/", {**NEW_COD, "phone": "1234567890"}, format="json").status_code == 400
    # spaces in a pincode, other payment wordings and odd channel casing are cleaned, not refused
    ok = shop.post("/api/risk/score/", {**NEW_COD, "pincode": " 411 001", "payment_mode": "UPI",
                                        "sales_channel": "website"}, format="json")
    assert ok.status_code == 200 and ok.json()["destination"]["pincode"] == "411001"


def test_batch_scoring(shop):
    prepaid = {**NEW_COD, "order_id": "N2", "payment_mode": "Prepaid"}

    r = shop.post("/api/risk/score-batch/", {"orders": [NEW_COD, prepaid]}, format="json").json()

    # the prepaid twin: -3.0 +0.5 no house number +0.7 short address = -1.8 -> 14.2%, Medium
    assert r["count"] == 2 and r["by_category"] == {"Low": 0, "Medium": 1, "High": 0, "Very high": 1}
    assert [x["order_id"] for x in r["results"]] == ["N1", "N2"]
    assert [x["risk_category"] for x in r["results"]] == ["Very high", "Medium"]
    assert no_phone_in(r, NEW_COD["phone"])

    post = lambda body: shop.post("/api/risk/score-batch/", body, format="json")   # noqa: E731
    assert post({"orders": []}).status_code == 400
    assert post({"orders": [NEW_COD] * 501}).status_code == 400
    assert post([NEW_COD]).status_code == 400                                      # not {"orders": [...]}
    bad = post({"orders": [NEW_COD, {"order_value": 5, "payment_mode": "cash"}, prepaid]})
    assert bad.status_code == 400
    assert bad.json() == {"orders": {"1": {"payment_mode": ["Use COD or Prepaid."],
                                           "pincode": ["This field is required."]}}}


def test_trained_model_is_used_when_there_is_one(shop, monkeypatch):
    scorer, _, _ = fit(synthetic())
    monkeypatch.setattr(score, "scorer_for", lambda merchant: (scorer, dict(RISK_BANDS)))
    before = table_counts()

    cod = shop.post("/api/risk/score/", NEW_COD, format="json").json()
    prepaid = shop.post("/api/risk/score/", {**NEW_COD, "payment_mode": "Prepaid"}, format="json").json()

    assert cod["scored_by"] == f"model:{scorer.kind}"
    assert 0 < prepaid["risk_probability"] < cod["risk_probability"] < 1
    top = cod["contributing_factors"][0]
    assert set(top) == {"factor", "value", "effect", "strength"} and top["strength"] >= score.MIN_STRENGTH
    assert {"factor": "Cash on delivery", "value": "COD", "effect": "raises risk"}.items() <= next(
        f for f in cod["contributing_factors"] if f["factor"] == "Cash on delivery").items()
    assert table_counts() == before                 # no RiskModel or artifact was saved


def test_repeat_returner_rule():
    import pandas as pd
    row = lambda rto, ok: pd.Series({"cust_prior_rto": rto, "cust_prior_delivered": ok})   # noqa: E731

    assert score.repeat_returner(row(6, 12)) is True          # 6 of 18 = 33%
    assert score.repeat_returner(row(3, 7)) is True           # exactly 30%
    assert score.repeat_returner(row(2, 10)) is False         # 2 of 12 = 17%: rate too low
    assert score.repeat_returner(row(1, 0)) is False          # one return is not a pattern
    assert score.repeat_returner(row(0, 0)) is False


def test_another_merchant_does_not_see_my_customers(shop):
    spy = User.objects.create_user("spy", password="x", merchant=Merchant.objects.create(name="Other"))
    other = APIClient()
    other.force_authenticate(spy)

    r = other.post("/api/risk/score/", {**NEW_COD, "phone": ASHA}, format="json").json()
    assert r["scored_by"] == "rules"
    assert r["customer"] == {"known": False, "previous_orders": 0, "delivered": 0, "returned": 0}
    assert r["destination"]["parcels_sent_before"] == 0 and r["destination"]["city"] == ""
    assert other.post("/api/risk/score-batch/", {"orders": [{**NEW_COD, "phone": ASHA}]},
                      format="json").json()["results"][0]["customer"]["known"] is False

    no_merchant = APIClient()
    no_merchant.force_authenticate(User.objects.create_user("loner", password="x"))
    assert no_merchant.post("/api/risk/score/", NEW_COD, format="json").status_code == 403
    for path, body in [("/api/risk/score/", NEW_COD), ("/api/risk/score-batch/", {"orders": [NEW_COD]})]:
        assert APIClient().post(path, body, format="json").status_code in (401, 403)
