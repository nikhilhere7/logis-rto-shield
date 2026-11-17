"""The timing lines: one per measured request, with the expected steps, and never anything sensitive."""
import io
import logging

import pytest
from django.core.cache import cache
from rest_framework.test import APIClient

from core.models import Merchant, User
from core.perf import RequestTimer

PASSWORD = "weave-9-looms"
EMAIL = "perf.owner@example.com"
ORDERS = """Order Number,Created At,Phone,Customer Name,Shipping Zip,Address,Payment Method,Total
P1,2025-03-01 10:00:00,9876543210,Asha Patil,411001,"Flat 2, FC Road",COD,500
"""


def perf_lines(caplog, op):
    return [r.getMessage() for r in caplog.records
            if r.name == "logis.perf" and r.getMessage().startswith(f"perf op={op} ")]


@pytest.fixture
def api(db):
    cache.clear()  # throttle counters live in the cache
    return APIClient()


def test_signup_and_login_are_timed_without_secrets(api, caplog):
    caplog.set_level(logging.INFO, logger="logis.perf")
    r = api.post("/api/auth/signup/", {"business_name": "Perf Co", "name": "Asha Patil",
                                       "email": EMAIL, "password": PASSWORD}, format="json")
    assert r.status_code == 201
    login = api.post("/api/auth/login/", {"email": EMAIL, "password": PASSWORD}, format="json")
    assert login.status_code == 200
    bad = api.post("/api/auth/login/", {"email": EMAIL, "password": "wrong"}, format="json")
    assert bad.status_code == 401

    [signup] = perf_lines(caplog, "signup")
    assert "status=ok" in signup
    for step in ("total_ms=", "validate_ms=", "merchant_insert_ms=", "user_create_ms=", "transaction_ms=", "token_ms="):
        assert step in signup
    ok, failed = perf_lines(caplog, "login")
    assert "status=ok" in ok and "lookup_ms=" in ok and "authenticate_ms=" in ok
    assert "status=error" in failed and "error=AuthenticationFailed" in failed  # still a 401, still logged

    logged = "\n".join(r.getMessage() for r in caplog.records)
    for secret in (PASSWORD, EMAIL, "Asha", "Perf Co", r.json()["access"], login.json()["access"],
                   login.json()["refresh"]):
        assert secret not in logged


def test_upload_validate_and_commit_are_timed(db, settings, tmp_path, caplog):
    settings.MEDIA_ROOT = tmp_path
    caplog.set_level(logging.INFO, logger="logis.perf")
    m = Merchant.objects.create(name="Perf Merchant")
    c = APIClient()
    c.force_authenticate(User.objects.create_user("perf-owner", password="x", merchant=m))

    f = io.BytesIO(ORDERS.encode())
    f.name = "orders.csv"
    bid = c.post("/api/ingestion/uploads/", {"dataset_type": "orders", "file": f}, format="multipart").json()["id"]
    assert c.post(f"/api/ingestion/uploads/{bid}/validate/", {}, format="json").status_code == 200
    assert c.post(f"/api/ingestion/uploads/{bid}/commit/").status_code == 200

    [upload] = perf_lines(caplog, "upload")
    [validate] = perf_lines(caplog, "validate")
    [commit] = perf_lines(caplog, "commit")
    for step in ("create_and_store_ms=", "download_ms=", "parse_ms=", f"batch_id={bid}", "rows=1", "file_bytes="):
        assert step in upload
    for step in ("download_ms=", "parse_ms=", "validate_ms=", "valid_rows=1"):
        assert step in validate
    for step in ("download_ms=", "parse_ms=", "validate_ms=", "load_ms=", "rebuild_ledger_ms=", "run_audit_ms=",
                 "transaction_ms=", "status=ok", "dataset_type=orders"):
        assert step in commit

    logged = "\n".join(r.getMessage() for r in caplog.records)
    for secret in ("9876543210", "Asha", "FC Road", "orders.csv"):  # no file contents or file names
        assert secret not in logged


def test_a_failing_step_is_logged_and_the_exception_still_propagates(caplog):
    caplog.set_level(logging.INFO, logger="logis.perf")
    with pytest.raises(KeyError):
        with RequestTimer("demo") as t:
            with t.step("work"):
                raise KeyError("customer 9876543210")
    [line] = perf_lines(caplog, "demo")
    assert "status=error" in line and "error=KeyError" in line and "work_ms=" in line
    assert "9876543210" not in line  # the exception message is never logged
