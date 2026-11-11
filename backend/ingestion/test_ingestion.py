import io

import pandas as pd
import pytest
from rest_framework.test import APIClient

from core.models import Customer, Merchant, Order, Shipment, User
from ingestion.mapper import suggest_mapping
from ingestion.schemas import SPECS

ORDERS = """Order Number,Created At,Phone,Customer Name,Shipping Zip,Address,Payment Method,Total
A1,2025-03-01 10:00:00,9876543210,Asha Patil,411001,"Flat 2, FC Road",Cash on Delivery,"Rs. 1,299"
A2,02/03/2025 18:30,+91 98765 43210,Asha Patil,411001,"Flat 2, FC Road",UPI,799
A3,2025-03-03 09:00:00,9123456780,Ravi Shah,41100,MG Road,COD,500
A4,not a date,9123456780,Ravi Shah,400001,MG Road,COD,500
A1,2025-03-04 09:00:00,9123456780,Ravi Shah,400001,MG Road,COD,500
A6,2025-03-05 09:00:00,,No Phone,400001,MG Road,Prepaid,650
"""
SHIPMENTS = """AWB,Order Number,Courier Name,Pickup Date,Weight (kg),Status,Delivered Date
X100,A1,FastShip,2025-03-02,0.45,Delivered,2025-03-04
X101,A2,FastShip,2025-03-03,0.30,RTO,
X102,ZZZ,FastShip,2025-03-03,0.30,Delivered,2025-03-05
"""


@pytest.fixture
def client(db, settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    m = Merchant.objects.create(name="Test Merchant")
    user = User.objects.create_user("owner", password="x", merchant=m)
    c = APIClient()
    c.force_authenticate(user)
    c.merchant = m
    return c


def upload(client, kind, content, name="file.csv"):
    f = io.BytesIO(content.encode())
    f.name = name
    return client.post("/api/ingestion/uploads/", {"dataset_type": kind, "file": f}, format="multipart")


def run(client, kind, content):
    bid = upload(client, kind, content).json()["id"]
    v = client.post(f"/api/ingestion/uploads/{bid}/validate/", {}, format="json")
    c = client.post(f"/api/ingestion/uploads/{bid}/commit/")
    return v.json(), c.json()


def test_mapper_handles_renamed_columns():
    cols = pd.read_csv(io.StringIO(ORDERS)).columns
    m = suggest_mapping(cols, SPECS["orders"])
    assert m["order_id"] == "Order Number" and m["pincode"] == "Shipping Zip" and m["order_value"] == "Total"


def test_orders_validation_and_load(client):
    v, c = run(client, "orders", ORDERS)
    rep = v["quality_report"]
    assert rep["total_rows"] == 6 and rep["valid_rows"] == 2
    rules = {e["rule"] for e in rep["errors"]}
    assert {"invalid_pincode", "invalid_ts", "duplicate_in_file", "no_customer_id_or_phone"} <= rules
    assert c["load_result"]["created"] == 2
    # two phone formats, one person
    assert Customer.objects.for_merchant(client.merchant).count() == 1
    o = Order.objects.get(external_id="A1")
    assert str(o.order_value) == "1299.00" and o.payment_mode == "COD"
    assert Order.objects.get(external_id="A2").order_ts.astimezone().month == 3   # 02/03 read as 2 March


def test_reupload_updates_instead_of_duplicating(client):
    run(client, "orders", ORDERS)
    _, c = run(client, "orders", ORDERS)
    assert c["load_result"] == {"created": 0, "updated": 2, "customers_touched": 1}
    assert Order.objects.count() == 2


def test_shipments_need_known_order_and_convert_kg(client):
    run(client, "orders", ORDERS)
    v, c = run(client, "shipments", SHIPMENTS)
    assert v["quality_report"]["valid_rows"] == 2
    assert any(e["rule"] == "order_not_found" for e in v["quality_report"]["errors"])
    s = Shipment.objects.get(awb_number="X100")
    assert s.pkg_weight_g == 450 and s.courier.name == "FastShip"
    assert Shipment.objects.get(awb_number="X101").final_status == "RTO Delivered"


def test_missing_required_column_is_refused(client):
    bid = upload(client, "orders", "Order Number,Total\nA1,100\n").json()["id"]
    r = client.post(f"/api/ingestion/uploads/{bid}/validate/", {}, format="json")
    assert r.status_code == 400 and "order_ts" in str(r.json())


def test_other_merchant_cannot_touch_my_upload(client):
    bid = upload(client, "orders", ORDERS).json()["id"]
    other = User.objects.create_user("spy", password="x", merchant=Merchant.objects.create(name="Other"))
    c2 = APIClient()
    c2.force_authenticate(other)
    assert c2.post(f"/api/ingestion/uploads/{bid}/validate/", {}, format="json").status_code == 404


def test_reupload_without_phone_keeps_existing_phone_hash(client):
    with_phone = "Order Number,Created At,Customer ID,Phone,Shipping Zip,Payment Method,Total\n" \
                 "B1,2025-03-01 10:00:00,CU1,9876543210,411001,COD,500\n"
    no_phone = "Order Number,Created At,Customer ID,Shipping Zip,Payment Method,Total\n" \
               "B1,2025-03-01 10:00:00,CU1,411002,COD,500\n"
    run(client, "orders", with_phone)
    original = Customer.objects.for_merchant(client.merchant).get(external_id="CU1").phone_hash
    assert len(original) == 64

    run(client, "orders", no_phone)
    cust = Customer.objects.for_merchant(client.merchant).get(external_id="CU1")
    assert cust.phone_hash == original      # hash survives the phone-less upload
    assert cust.pincode == "411002"         # while the rest of the row still updates
