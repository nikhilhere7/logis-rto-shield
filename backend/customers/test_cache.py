"""The customer table is cached per merchant, and any change to the data shows up on the very next request."""
import io
from datetime import timedelta

import pytest
from django.core.cache import cache
from django.db import transaction
from django.utils import timezone
from rest_framework.test import APIClient

from core.models import Customer, Merchant, Order, User
from customers import profiles
from customers.profiles import customer_table
from ingestion.cleanup import clear
from ledger.build import data_generation, mark_data_changed, rebuild_ledger

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def fresh_cache():
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def builds(monkeypatch):
    """Counts how many times the real table is built (a cache miss)."""
    calls = []
    real = profiles._build_customer_table

    def counted(merchant):
        calls.append(merchant.pk)
        return real(merchant)

    monkeypatch.setattr(profiles, "_build_customer_table", counted)
    return calls


def add_customer(merchant, ref, status="Shipped"):
    c = Customer.objects.create(merchant=merchant, external_id=ref, name=ref, pincode="411001")
    Order.objects.create(merchant=merchant, external_id=f"{ref}-O1", customer=c, order_ts=timezone.now() - timedelta(days=3),
                         payment_mode="COD", gross_value=500, order_value=500, status=status)
    return c


def counts_and_newest_ids(merchant):
    """The version without the generation token: what a count/max-id-only cache key would see."""
    return profiles._data_version(merchant)[1:]


def test_first_call_builds_and_repeated_calls_reuse_the_cache(builds):
    a = Merchant.objects.create(name="A")
    add_customer(a, "A1")
    assert list(customer_table(a).customer_ref) == ["A1"]
    assert list(customer_table(a).customer_ref) == ["A1"]
    assert list(customer_table(a).customer_ref) == ["A1"]
    assert builds == [a.pk]  # built once, then served from the cache


def test_cached_table_matches_a_fresh_build_exactly():
    a = Merchant.objects.create(name="A")
    add_customer(a, "A1")
    add_customer(a, "A2", status="Cancelled")
    customer_table(a)                                   # fills the cache
    cached, fresh = customer_table(a), profiles._build_customer_table(a)
    assert list(cached.columns) == list(fresh.columns) and list(cached.dtypes) == list(fresh.dtypes)
    assert cached.equals(fresh)


def test_new_customers_and_orders_show_on_the_next_call(builds):
    a = Merchant.objects.create(name="A")
    add_customer(a, "A1")
    customer_table(a)
    add_customer(a, "A2")                               # no rebuild_ledger: the counts and newest ids catch it
    assert sorted(customer_table(a).customer_ref) == ["A1", "A2"]
    assert len(builds) == 2


def test_updates_in_place_show_after_the_ledger_is_rebuilt():
    """The case a count/max-id key misses: the same rows change, nothing is added or removed, and with no
    shipments the ledger stays empty. Every upload and removal rebuilds the ledger, which renews the token."""
    a = Merchant.objects.create(name="A")
    c = add_customer(a, "A1")
    before = customer_table(a).iloc[0]
    assert before["name"] == "A1" and before.cancelled == 0
    version = counts_and_newest_ids(a)

    Customer.objects.filter(pk=c.pk).update(name="Asha", pincode="400001")
    Order.objects.filter(customer=c).update(status=Order.Status.CANCELLED)
    rebuild_ledger(a)

    assert counts_and_newest_ids(a) == version          # counts and ids alone would have served the old table
    after = customer_table(a).iloc[0]
    assert after["name"] == "Asha" and after.pincode == "400001" and after.cancelled == 1


def test_an_orders_reupload_through_the_api_shows_its_changes():
    """End to end: re-uploading an order with a new date and customer name updates the rows in place."""
    a = Merchant.objects.create(name="A")
    api = APIClient()
    api.force_authenticate(User.objects.create_user("cache-owner", password="x", merchant=a))

    def load(name, when):
        csv = ("Order Number,Created At,Phone,Customer Name,Shipping Zip,Address,Payment Method,Total\n"
               f"R1,{when},9876543210,{name},411001,MG Road,COD,500\n")
        f = io.BytesIO(csv.encode())
        f.name = "orders.csv"
        bid = api.post("/api/ingestion/uploads/", {"dataset_type": "orders", "file": f}, format="multipart").json()["id"]
        assert api.post(f"/api/ingestion/uploads/{bid}/validate/", {}, format="json").status_code == 200
        assert api.post(f"/api/ingestion/uploads/{bid}/commit/").status_code == 200

    load("Asha Patil", "2025-03-01 10:00:00")
    first = customer_table(a).iloc[0]
    load("Asha P", "2025-03-09 10:00:00")
    second = customer_table(a).iloc[0]
    assert first["name"] == "Asha Patil" and second["name"] == "Asha P"
    assert second.last_order > first.last_order


def test_deletions_show_on_the_next_call():
    a = Merchant.objects.create(name="A")
    add_customer(a, "A1")
    gone = add_customer(a, "A2")
    assert sorted(customer_table(a).customer_ref) == ["A1", "A2"]
    gone.delete()                                       # a single row removed, no ledger rebuild
    assert list(customer_table(a).customer_ref) == ["A1"]
    clear(a, ["orders"])                                # the app's own "Remove data"
    assert customer_table(a).empty


def test_one_merchant_never_gets_another_merchants_table():
    a, b = Merchant.objects.create(name="A"), Merchant.objects.create(name="B")
    add_customer(a, "A1")
    add_customer(b, "B1")
    assert list(customer_table(a).customer_ref) == ["A1"]
    assert list(customer_table(b).customer_ref) == ["B1"]
    assert list(customer_table(a).customer_ref) == ["A1"]   # both now cached, still apart
    rebuild_ledger(b)                                       # a change for B does not touch A's entry
    assert list(customer_table(a).customer_ref) == ["A1"]


# ---------------------------------------------------------------- mark_data_changed and the transaction
def test_mark_data_changed_renews_the_token_at_once_and_schedules_one_more_renewal(django_capture_on_commit_callbacks):
    a = Merchant.objects.create(name="A")
    before = data_generation(a)
    with django_capture_on_commit_callbacks(execute=False) as pending:
        with transaction.atomic():
            mark_data_changed(a)
            during = data_generation(a)
    assert during != before                              # immediate: reads inside the transaction see a new token
    assert len(pending) == 1                             # and exactly one renewal waits for the commit
    pending[0]()
    assert data_generation(a) not in (before, during)


@pytest.mark.django_db(transaction=True)                 # real commits and rollbacks, not the test's wrapper
def test_a_commit_renews_the_token_again():
    a = Merchant.objects.create(name="A")
    with transaction.atomic():
        mark_data_changed(a)
        during = data_generation(a)
    assert data_generation(a) != during                  # the on_commit callback ran after the COMMIT


@pytest.mark.django_db(transaction=True)
def test_a_rollback_skips_the_second_renewal():
    a = Merchant.objects.create(name="A")
    before = data_generation(a)
    with pytest.raises(RuntimeError):
        with transaction.atomic():
            mark_data_changed(a)
            during = data_generation(a)
            raise RuntimeError("load failed")
    assert during != before                              # the immediate renewal had already happened (harmless)
    assert data_generation(a) == during                  # the on_commit callback never ran


@pytest.mark.django_db(transaction=True)
def test_rebuild_ledger_inside_an_upload_renews_only_after_the_outer_commit():
    """rebuild_ledger is atomic itself, but inside CommitView it is nested: its savepoint ending must not count
    as the commit. The second renewal waits for the outermost transaction."""
    a = Merchant.objects.create(name="A")
    with transaction.atomic():                           # the upload's transaction
        rebuild_ledger(a)                                # inner atomic block: a savepoint, not a commit
        after_inner = data_generation(a)
        add_customer(a, "A1")                            # more writes after the rebuild, still uncommitted
        assert data_generation(a) == after_inner         # nothing renewed yet
    assert data_generation(a) != after_inner             # renewed once the outer transaction committed


def test_changing_the_returned_table_does_not_change_the_cache():
    a = Merchant.objects.create(name="A")
    add_customer(a, "A1")
    first = customer_table(a)
    first.loc[:, "customer_ref"] = "CHANGED"            # change the returned rows in place
    first["extra"] = 1
    again = customer_table(a)
    assert list(again.customer_ref) == ["A1"] and "extra" not in again.columns
