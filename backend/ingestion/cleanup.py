"""Removing data a merchant has uploaded.

Rows are not tied to the upload that brought them in (a second upload of the same orders updates the
same rows), so data is removed one kind at a time: all the orders, all the shipments, and so on.
Afterwards the ledger and the audit are rebuilt, so every page and report reflects what is left.
Nothing outside the given merchant is ever touched."""
from django.db import transaction

from audit.engine import run_audit
from core.models import CodRemittance, Courier, Customer, InvoiceLine, PincodeZone, Product, RateCard, Shipment
from ledger.build import rebuild_ledger
from ml.models import RiskModel

from .models import UploadBatch

# kind of data -> (the rows to delete, a sentence on what else goes with them)
KINDS = {
    "orders": "Also removes every shipment linked to these orders, and the customers found in them.",
    "shipments": "Orders stay. Courier invoices and COD payments stay, but can no longer be matched to a parcel.",
    "invoices": "",
    "remittances": "",
    "rate_card": "The billing audit needs a rate card, so it stops until a new one is uploaded.",
    "pincode_zones": "Zones and city tiers disappear from the analysis until a new file is uploaded.",
}


def _delete(merchant, kind):
    """Delete one kind of data. Returns how many rows went (not counting rows removed with them)."""
    if kind == "orders":
        # Deleting the customers deletes their orders, the order items, the shipments and tracking events with them.
        n = Customer.objects.for_merchant(merchant).count()
        Customer.objects.for_merchant(merchant).delete()
        Product.objects.for_merchant(merchant).delete()
        return n
    model = {"shipments": Shipment, "invoices": InvoiceLine, "remittances": CodRemittance,
             "rate_card": RateCard, "pincode_zones": PincodeZone}[kind]
    rows = model.objects.for_merchant(merchant)
    n = rows.count()  # counted first: delete() also counts the rows removed along with them
    rows.delete()
    return n


def _drop_unused_couriers(merchant):
    """A courier with nothing left pointing at it is removed, so it stops appearing in lists."""
    used = set()
    for model in (Shipment, InvoiceLine, CodRemittance, RateCard):
        used |= set(model.objects.for_merchant(merchant).values_list("courier_id", flat=True).distinct())
    Courier.objects.for_merchant(merchant).exclude(id__in=used).delete()


def delete_file_after_commit(field):
    """Delete a stored file only once the surrounding transaction has committed. If anything fails and the
    database rolls back, the rows come back and so must their files, so nothing is deleted before then."""
    if field and field.name:
        storage, name = field.storage, field.name
        transaction.on_commit(lambda: storage.delete(name))


def _forget_uploads(merchant, kinds, keep=None):
    """The upload history of a removed kind goes too, with the stored files. `keep` is an upload to spare."""
    for b in UploadBatch.objects.for_merchant(merchant).filter(dataset_type__in=kinds).exclude(id=keep):
        delete_file_after_commit(b.file)
        b.delete()


def clear(merchant, kinds, rebuild=True, keep=None):
    """Remove the given kinds of data for one merchant, inside one transaction.

    When orders or shipments go, the trained risk model was trained on data that no longer exists,
    so it is switched off and orders are scored by rules until it is trained again."""
    kinds = [k for k in KINDS if k in set(kinds)]
    removed = {}
    with transaction.atomic():
        for kind in kinds:
            removed[kind] = _delete(merchant, kind)
        _drop_unused_couriers(merchant)
        # Removing orders removes their shipments too, so the shipment uploads leave the history with them.
        _forget_uploads(merchant, kinds + (["shipments"] if "orders" in kinds else []), keep=keep)
        model_off = False
        if {"orders", "shipments"} & set(kinds):
            model_off = RiskModel.objects.for_merchant(merchant).filter(is_active=True).update(is_active=False) > 0
        result = {"removed": removed, "risk_model_switched_off": model_off}
        if rebuild:
            result["ledger"] = rebuild_ledger(merchant)
            result["audit"] = run_audit(merchant)
    return result


def clear_everything(merchant):
    """Start over: every kind of data, the whole upload history and every trained model, as one transaction.
    Either all of it goes or none of it does; stored files are deleted only after the commit."""
    with transaction.atomic():
        result = clear(merchant, list(KINDS))
        for run in RiskModel.objects.for_merchant(merchant):
            delete_file_after_commit(run.artifact)
        RiskModel.objects.for_merchant(merchant).delete()
        for b in UploadBatch.objects.for_merchant(merchant):
            delete_file_after_commit(b.file)
            b.delete()
    return result
