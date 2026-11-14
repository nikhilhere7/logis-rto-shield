"""Removing uploaded data, taking an upload off the history, and replacing a kind of data with a new file."""
import io

import pandas as pd
import pytest
from rest_framework.test import APIClient

from core.models import Customer, InvoiceLine, Merchant, Order, Shipment, User
from ingestion.models import UploadBatch
from ledger.models import ShipmentLedger
from ml.models import RiskModel

pytestmark = pytest.mark.django_db

ORDERS = pd.DataFrame({
    "order_id": ["O1", "O2", "O3"], "customer_id": ["C1", "C2", "C1"],
    "order_ts": ["2025-01-01 10:00", "2025-01-02 11:00", "2025-01-03 12:00"],
    "payment_mode": ["COD", "Prepaid", "COD"], "order_value": [500, 800, 650], "order_status": ["Shipped"] * 3,
    "shipping_pincode": ["411001"] * 3,
})
SHIPMENTS = pd.DataFrame({
    "awb_number": ["A1", "A2"], "order_id": ["O1", "O2"], "courier_id": ["Swift", "Swift"],
    "pickup_ts": ["2025-01-02 10:00", "2025-01-03 10:00"], "pkg_weight_g": [300, 400],
    "pkg_length_cm": [20, 20], "pkg_breadth_cm": [15, 15], "pkg_height_cm": [5, 5],
    "final_status": ["Delivered", "RTO Delivered"], "delivered_ts": ["2025-01-05 10:00", ""],
})


def client_for(merchant, name):
    c = APIClient()
    c.force_authenticate(User.objects.create_user(username=name, password="pw-12345678", merchant=merchant))
    return c


def upload(c, kind, frame, replace=None):
    """Run the three upload steps through the API and return the commit response."""
    f = io.BytesIO(frame.to_csv(index=False).encode())
    f.name = f"{kind}.csv"
    up = c.post("/api/ingestion/uploads/", {"dataset_type": kind, "file": f}, format="multipart")
    assert up.status_code == 201, up.json()
    pk = up.json()["id"]
    assert c.post(f"/api/ingestion/uploads/{pk}/validate/", {}, format="json").status_code == 200
    body = {} if replace is None else {"replace": replace}
    return c.post(f"/api/ingestion/uploads/{pk}/commit/", body, format="json")


@pytest.fixture
def store():
    m = Merchant.objects.create(name="Store")
    c = client_for(m, "owner")
    assert upload(c, "orders", ORDERS).status_code == 200
    assert upload(c, "shipments", SHIPMENTS).status_code == 200
    return m, c


def test_removing_needs_the_confirm_word_and_a_known_kind(store):
    m, c = store
    assert c.post("/api/ingestion/data/remove/", {"kinds": ["orders"]}, format="json").status_code == 400
    assert c.post("/api/ingestion/data/remove/", {"kinds": ["nonsense"], "confirm": "remove"}, format="json").status_code == 400
    assert Order.objects.for_merchant(m).count() == 3


def test_removing_shipments_keeps_orders_and_rebuilds_the_ledger(store):
    m, c = store
    r = c.post("/api/ingestion/data/remove/", {"kinds": ["shipments"], "confirm": "remove"}, format="json")
    assert r.status_code == 200 and r.json()["removed"] == {"shipments": 2}
    assert Order.objects.for_merchant(m).count() == 3
    assert Shipment.objects.for_merchant(m).count() == 0
    assert ShipmentLedger.objects.for_merchant(m).count() == 0
    assert not UploadBatch.objects.for_merchant(m).filter(dataset_type="shipments").exists()
    assert UploadBatch.objects.for_merchant(m).filter(dataset_type="orders").exists()


def test_removing_orders_takes_their_shipments_and_customers_and_switches_the_model_off(store):
    m, c = store
    RiskModel.objects.create(merchant=m, status="trained", is_active=True)
    r = c.post("/api/ingestion/data/remove/", {"kinds": ["orders"], "confirm": "remove"}, format="json")
    assert r.status_code == 200 and r.json()["risk_model_switched_off"] is True
    assert (Order.objects.for_merchant(m).count(), Shipment.objects.for_merchant(m).count(), Customer.objects.for_merchant(m).count()) == (0, 0, 0)
    assert not UploadBatch.objects.for_merchant(m).exists()  # the shipment uploads went with their shipments
    assert not RiskModel.objects.for_merchant(m).filter(is_active=True).exists()


def test_start_over_removes_everything_but_only_for_this_merchant(store):
    m, c = store
    other = Merchant.objects.create(name="Other")
    oc = client_for(other, "other")
    upload(oc, "orders", ORDERS)
    RiskModel.objects.create(merchant=m, status="trained", is_active=True)
    assert c.post("/api/ingestion/data/remove/", {"kinds": "all", "confirm": "remove"}, format="json").status_code == 200
    assert not Order.objects.for_merchant(m).exists() and not UploadBatch.objects.for_merchant(m).exists()
    assert not RiskModel.objects.for_merchant(m).exists()
    assert Order.objects.for_merchant(other).count() == 3 and UploadBatch.objects.for_merchant(other).count() == 1
    assert c.get("/api/workspace/status/").json()["counts"]["orders"] == 0


def test_a_new_file_adds_to_the_data_unless_replace_is_asked_for(store):
    m, c = store
    later = ORDERS.assign(order_id=["O7", "O8", "O9"])
    assert upload(c, "orders", later).status_code == 200
    assert Order.objects.for_merchant(m).count() == 6  # added: different order IDs
    r = upload(c, "orders", later.iloc[:2], replace=True)
    assert r.status_code == 200
    assert sorted(Order.objects.for_merchant(m).values_list("external_id", flat=True)) == ["O7", "O8"]
    history = UploadBatch.objects.for_merchant(m)
    assert history.count() == 1 and history.get().status == "loaded"  # only the replacing file is left, and it kept its file


def test_only_an_upload_that_was_never_loaded_can_be_taken_off_the_history(store):
    m, c = store
    loaded = UploadBatch.objects.for_merchant(m).filter(dataset_type="orders").get()
    assert c.delete(f"/api/ingestion/uploads/{loaded.id}/").status_code == 400
    f = io.BytesIO(ORDERS.to_csv(index=False).encode())
    f.name = "draft.csv"
    pk = c.post("/api/ingestion/uploads/", {"dataset_type": "orders", "file": f}, format="multipart").json()["id"]
    assert c.delete(f"/api/ingestion/uploads/{pk}/").status_code == 204
    assert not UploadBatch.objects.filter(id=pk).exists()
    other = client_for(Merchant.objects.create(name="Nosy"), "nosy")
    assert other.delete(f"/api/ingestion/uploads/{loaded.id}/").status_code == 404  # another merchant cannot see it at all
    assert InvoiceLine.objects.count() == 0


# ---- Safety additions: files go only after the commit, a failure rolls everything back, and the merchant
# ---- always comes from the login. Uploaded files are written to a temporary folder, never to media/.

@pytest.fixture
def files_in_tmp(settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    return tmp_path


def stored(m):
    return [b.file for b in UploadBatch.objects.for_merchant(m)]


def test_stored_files_are_deleted_only_once_the_removal_has_committed(files_in_tmp, store, django_capture_on_commit_callbacks):
    m, c = store
    files = stored(m)
    assert files and all(f.storage.exists(f.name) for f in files)
    with django_capture_on_commit_callbacks(execute=False) as pending:
        assert c.post("/api/ingestion/data/remove/", {"kinds": "all", "confirm": "remove"}, format="json").status_code == 200
        assert all(f.storage.exists(f.name) for f in files)  # rows are gone, files are still there until the commit
    assert len(pending) == len(files)
    for callback in pending:
        callback()
    assert not any(f.storage.exists(f.name) for f in files)


def test_a_failure_during_start_over_rolls_back_every_row_and_keeps_every_file(files_in_tmp, store, monkeypatch, django_capture_on_commit_callbacks):
    m, c = store
    files = stored(m)
    before = (Order.objects.for_merchant(m).count(), Shipment.objects.for_merchant(m).count(), UploadBatch.objects.for_merchant(m).count())

    def broken(merchant):
        raise RuntimeError("audit failed half way")
    monkeypatch.setattr("ingestion.cleanup.run_audit", broken)
    with django_capture_on_commit_callbacks(execute=True) as pending:
        with pytest.raises(RuntimeError):
            c.post("/api/ingestion/data/remove/", {"kinds": "all", "confirm": "remove"}, format="json")
    assert pending == []  # nothing was scheduled to delete files
    assert (Order.objects.for_merchant(m).count(), Shipment.objects.for_merchant(m).count(), UploadBatch.objects.for_merchant(m).count()) == before
    assert all(f.storage.exists(f.name) for f in files)


def test_a_replace_that_fails_while_loading_keeps_the_old_data(files_in_tmp, store, monkeypatch):
    m, c = store
    before = sorted(Order.objects.for_merchant(m).values_list("external_id", flat=True))

    def broken(clean, merchant):
        raise RuntimeError("loader failed")
    monkeypatch.setitem(__import__("ingestion.views", fromlist=["LOADERS"]).LOADERS, "orders", broken)
    with pytest.raises(RuntimeError):
        upload(c, "orders", ORDERS.assign(order_id=["N1", "N2", "N3"]), replace=True)
    assert sorted(Order.objects.for_merchant(m).values_list("external_id", flat=True)) == before
    assert Shipment.objects.for_merchant(m).count() == 2


def test_replace_must_be_exactly_true(files_in_tmp, store):
    m, c = store
    assert upload(c, "orders", ORDERS.assign(order_id=["N1", "N2", "N3"]), replace="true").status_code == 200
    assert Order.objects.for_merchant(m).count() == 6  # a string is not a yes: the file was added, nothing removed


def test_a_merchant_id_in_the_request_is_ignored(files_in_tmp, store):
    m, c = store
    other = Merchant.objects.create(name="Other")
    upload(client_for(other, "other"), "orders", ORDERS)
    r = c.post("/api/ingestion/data/remove/", {"kinds": ["orders"], "confirm": "remove", "merchant": other.id, "merchant_id": other.id}, format="json")
    assert r.status_code == 200
    assert Order.objects.for_merchant(m).count() == 0
    assert Order.objects.for_merchant(other).count() == 3
