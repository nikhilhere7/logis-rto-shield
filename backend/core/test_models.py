import pytest
from django.db import IntegrityError

from core.models import Courier, Merchant


@pytest.mark.django_db
def test_same_courier_code_allowed_for_two_merchants():
    a, b = Merchant.objects.create(name="A"), Merchant.objects.create(name="B")
    Courier.objects.create(merchant=a, code="C1", name="X")
    Courier.objects.create(merchant=b, code="C1", name="X")
    assert Courier.objects.for_merchant(a).count() == 1


@pytest.mark.django_db
def test_duplicate_courier_code_blocked_inside_one_merchant():
    a = Merchant.objects.create(name="A")
    Courier.objects.create(merchant=a, code="C1", name="X")
    with pytest.raises(IntegrityError):
        Courier.objects.create(merchant=a, code="C1", name="Y")
