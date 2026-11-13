from rest_framework.test import APIClient

from core.models import Merchant, User
from ingestion.test_ingestion import ORDERS, SHIPMENTS, client, run, upload  # noqa: F401
from ml.features import NUMERIC
from ml.models import RiskModel

URL = "/api/workspace/status/"
ZERO = {"orders": 0, "customers": 0, "shipments": 0, "shipments_with_outcome": 0, "cod_shipments": 0,
        "pincode_zones": 0, "rate_cards": 0, "invoice_lines": 0, "remittances": 0}
# a parcel that was lost: a shipment, but not a delivered or returned outcome
LOST = """AWB,Order Number,Courier Name,Pickup Date,Weight (kg),Status,Delivered Date
X103,A1,FastShip,2025-03-02,0.40,Lost,
"""
MORE_ORDERS = """Order Number,Created At,Customer ID,Shipping Zip,Payment Method,Total
C1,2025-03-06 10:00:00,CU-C,411002,COD,500
"""


def status(client):
    r = client.get(URL)
    assert r.status_code == 200
    return r.json()


def test_empty_merchant_gets_zeros_and_no_model(client):  # noqa: F811
    assert status(client) == {"counts": ZERO, "model": {
        "state": "none",
        "reason": "No risk model has been trained yet. Orders are scored with rules until there is enough history.",
        "trained_at": None}}


def test_counts_only_committed_business_data_and_real_outcomes(client):  # noqa: F811
    run(client, "orders", ORDERS)          # one customer, A1 (COD) and A2 (prepaid)
    run(client, "shipments", SHIPMENTS)    # X100 delivered, X101 returned; X102 rejected (unknown order)
    run(client, "shipments", LOST)         # X103 lost
    run(client, "pincode_zones", "Pin Code,Zone,City\n411001,A,Pune\n")

    # uploads that never reached the business tables do not count
    bid = upload(client, "orders", MORE_ORDERS).json()["id"]
    assert client.post(f"/api/ingestion/uploads/{bid}/validate/", {}, format="json").status_code == 200  # not committed
    upload(client, "orders", "not,a,real\nfile")                                                           # never valid

    c = status(client)["counts"]
    assert c == {**ZERO, "orders": 2, "customers": 1, "shipments": 3, "shipments_with_outcome": 2,
                 "cod_shipments": 2, "pincode_zones": 1}


def test_model_states_come_from_the_ml_code(client):  # noqa: F811
    m = client.merchant
    weak = RiskModel.objects.create(merchant=m, status=RiskModel.Status.INSUFFICIENT_DATA, is_active=False,
                                    metrics={"rows": 2, "rto": 1, "reason": "Need at least 2000 shipments with a "
                                                                           "known outcome and 200 RTOs."})
    model = status(client)["model"]
    assert model == {"state": "insufficient_data", "trained_at": None,
                     "reason": "Need at least 2000 shipments with a known outcome and 200 RTOs."}

    old = RiskModel.objects.create(merchant=m, status=RiskModel.Status.TRAINED, is_active=True,
                                   metrics={"chosen": "logistic"})            # M4-style: no feature version
    model = status(client)["model"]
    assert model["state"] == "stale" and "older set of features" in model["reason"] and model["trained_at"]

    old.is_active = False
    old.save()
    RiskModel.objects.create(merchant=m, status=RiskModel.Status.TRAINED, is_active=True,
                             metrics={"feature_version": 2, "feature_columns": NUMERIC + ["zone=A"]})
    model = status(client)["model"]
    assert model["state"] == "ready" and model["reason"] == "Orders are scored by your trained risk model."
    assert model["trained_at"] and set(model) == {"state", "reason", "trained_at"}
    assert "artifact" not in str(status(client)) and weak.pk          # no file paths or internals leak


def test_merchants_never_see_each_others_counts(client):  # noqa: F811
    run(client, "orders", ORDERS)
    RiskModel.objects.create(merchant=client.merchant, status=RiskModel.Status.INSUFFICIENT_DATA, metrics={})

    other = APIClient()
    other.force_authenticate(User.objects.create_user("b", password="x", merchant=Merchant.objects.create(name="B")))
    assert status(other) == {"counts": ZERO, "model": status(other)["model"]}
    assert status(other)["model"]["state"] == "none"
    assert status(client)["counts"]["orders"] == 2


def test_login_and_a_merchant_are_required(client):  # noqa: F811
    r = APIClient().get(URL)
    assert r.status_code == 401
    loner = APIClient()
    loner.force_authenticate(User.objects.create_user("loner", password="x"))
    r = loner.get(URL)
    assert r.status_code == 403 and r.json() == {"detail": "This user is not attached to a merchant."}
