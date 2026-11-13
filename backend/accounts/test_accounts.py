import pytest
from django.core.cache import cache
from rest_framework.test import APIClient

from core.models import Merchant, User

NEW = {
    "business_name": "Kala  Kurta Co",
    "name": "Meera Joshi",
    "email": "Meera@Example.com",
    "password": "weave-9-looms",
}


@pytest.fixture
def api(db):
    cache.clear()  # throttle counters live in the cache
    return APIClient()


def test_signup_creates_a_merchant_and_logs_the_owner_in(api):
    r = api.post("/api/auth/signup/", NEW, format="json")
    assert r.status_code == 201
    assert r.json()["user"] == {"name": "Meera Joshi", "email": "meera@example.com", "merchant": "Kala Kurta Co"}
    assert r.json()["access"] and r.json()["refresh"]
    user = User.objects.get(username="meera@example.com")
    assert user.merchant == Merchant.objects.get(name="Kala Kurta Co") and user.check_password("weave-9-looms")
    assert not user.is_staff and not user.is_superuser

    api.credentials(HTTP_AUTHORIZATION="Bearer " + r.json()["access"])
    assert api.get("/api/auth/me/").json()["merchant"] == "Kala Kurta Co"
    assert api.get("/api/metrics/overview/").json()["total_shipments"] == 0  # a fresh, empty workspace


def test_signup_refuses_duplicates_and_weak_passwords(api):
    api.post("/api/auth/signup/", NEW, format="json")
    again = api.post("/api/auth/signup/", {**NEW, "business_name": "Other"}, format="json")
    assert again.status_code == 400 and "email" in again.json()
    same_shop = api.post("/api/auth/signup/", {**NEW, "email": "b@example.com", "business_name": "kala kurta co"},
                         format="json")
    assert same_shop.status_code == 400 and "business_name" in same_shop.json()
    weak = api.post("/api/auth/signup/", {**NEW, "email": "c@example.com", "business_name": "C", "password": "12345678"},
                    format="json")
    assert weak.status_code == 400 and "password" in weak.json()
    assert Merchant.objects.count() == 1 and User.objects.count() == 1  # failed attempts leave nothing behind


def test_login_refresh_and_wrong_password(api):
    api.post("/api/auth/signup/", NEW, format="json")
    r = api.post("/api/auth/login/", {"email": "MEERA@example.com", "password": "weave-9-looms"}, format="json")
    assert r.status_code == 200 and r.json()["user"]["merchant"] == "Kala Kurta Co"
    fresh = api.post("/api/auth/refresh/", {"refresh": r.json()["refresh"]}, format="json")
    assert fresh.status_code == 200 and "access" in fresh.json()
    assert api.post("/api/auth/login/", {"email": "meera@example.com", "password": "nope"}, format="json").status_code == 401


def test_admin_made_user_can_log_in_with_username_or_email(api):
    m = Merchant.objects.create(name="Old Shop")
    User.objects.create_user("uploader", email="owner@oldshop.in", password="weave-9-looms", merchant=m)
    for typed in ["uploader", "owner@oldshop.in"]:
        r = api.post("/api/auth/login/", {"email": typed, "password": "weave-9-looms"}, format="json")
        assert r.status_code == 200 and r.json()["user"]["merchant"] == "Old Shop"


def test_api_needs_a_token_and_merchants_stay_separate(api):
    assert api.get("/api/metrics/overview/").status_code == 401
    a = api.post("/api/auth/signup/", NEW, format="json").json()
    b = api.post("/api/auth/signup/", {**NEW, "email": "b@example.com", "business_name": "Second Shop"},
                 format="json").json()
    api.credentials(HTTP_AUTHORIZATION="Bearer " + b["access"])
    assert api.get("/api/auth/me/").json()["merchant"] == "Second Shop" != a["user"]["merchant"]


def test_signup_is_rate_limited(api):
    for i in range(10):
        api.post("/api/auth/signup/", {**NEW, "email": f"u{i}@example.com", "business_name": f"Shop {i}"}, format="json")
    assert api.post("/api/auth/signup/", {**NEW, "email": "x@example.com", "business_name": "X"},
                    format="json").status_code == 429
