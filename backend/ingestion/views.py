from django.db import transaction
from rest_framework import status
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.generics import get_object_or_404
from rest_framework.parsers import JSONParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from audit.engine import run_audit
from core.perf import RequestTimer
from ledger.build import rebuild_ledger

from .cleanup import KINDS, clear, clear_everything, delete_file_after_commit
from .loaders import LOADERS
from .mapper import suggest_mapping
from .models import UploadBatch
from .schemas import SPECS
from .validators import MappingError, read_file, run_validation


class MerchantAPIView(APIView):
    """Every ingestion endpoint works only inside the logged-in user's merchant."""

    def merchant(self):
        m = getattr(self.request.user, "merchant", None)
        if m is None:
            raise PermissionDenied("This user is not attached to a merchant.")
        return m

    def batch(self, pk):
        return get_object_or_404(UploadBatch.objects.for_merchant(self.merchant()), pk=pk)


def summary(b):
    return {"id": b.id, "dataset_type": b.dataset_type, "file": b.original_filename, "status": b.status,
            "column_mapping": b.column_mapping, "quality_report": b.quality_report, "load_result": b.load_result}


class UploadView(MerchantAPIView):
    """Step 1. POST a file -> get back the columns we found and our best-guess mapping."""
    parser_classes = [MultiPartParser]

    def get(self, request):
        return Response([summary(b) for b in UploadBatch.objects.for_merchant(self.merchant())[:50]])

    def post(self, request):
        # The request body has already been received and parsed by the time post() runs, so total_ms here
        # does not include the browser -> Render transfer.
        with RequestTimer("upload") as t:
            return self._post(request, t)

    def _post(self, request, t):
        kind, f = request.data.get("dataset_type"), request.FILES.get("file")
        if kind not in SPECS:
            raise ValidationError({"dataset_type": f"Must be one of: {', '.join(SPECS)}"})
        if f is None or not f.name.lower().endswith((".csv", ".xlsx", ".xls")):
            raise ValidationError({"file": "Upload a .csv or .xlsx file."})
        t.set(dataset_type=kind, upload_bytes=f.size)
        with t.step("create_and_store"):  # the file goes to storage (Supabase S3 in production), then the INSERT
            b = UploadBatch.objects.create(merchant=self.merchant(), dataset_type=kind, file=f,
                                           original_filename=f.name, uploaded_by=request.user)
        t.set(batch_id=b.pk, merchant_id=b.merchant_id)
        try:
            raw = read_file(b.file, timer=t)
        except Exception as e:
            b.status = UploadBatch.Status.FAILED
            b.save(update_fields=["status"])
            raise ValidationError({"file": f"Could not read the file: {e}"})
        spec = SPECS[kind]
        with t.step("mapping"):
            b.column_mapping = suggest_mapping(raw.columns, spec)
            b.save(update_fields=["column_mapping"])
        return Response({
            **summary(b),
            "rows": len(raw),
            "columns_in_file": list(raw.columns),
            "required_fields": spec.required,
            "unmapped_required": [f for f in spec.required if not b.column_mapping.get(f)],
            "preview": raw.head(5).to_dict(orient="records"),
        }, status=status.HTTP_201_CREATED)


class ValidateView(MerchantAPIView):
    """Step 2. Confirm or correct the mapping -> get the data quality report. Nothing is saved yet."""
    parser_classes = [JSONParser]

    def post(self, request, pk):
        with RequestTimer("validate", batch_id=pk) as t:
            b = self.batch(pk)
            t.set(dataset_type=b.dataset_type, merchant_id=b.merchant_id)
            if b.status == UploadBatch.Status.LOADED:
                raise ValidationError("This upload is already loaded.")
            mapping = {**b.column_mapping, **(request.data.get("mapping") or {})}
            try:
                raw = read_file(b.file, timer=t)
                with t.step("validate"):
                    _, report = run_validation(raw, b.dataset_type, mapping, b.merchant)
            except MappingError as e:
                raise ValidationError({"mapping": str(e)})
            b.column_mapping, b.quality_report, b.status = mapping, report, UploadBatch.Status.VALIDATED
            with t.step("save"):
                b.save()
            t.set(valid_rows=report.get("valid_rows"))
            return Response(summary(b))


class UploadDetailView(MerchantAPIView):
    """Take one upload off the history. Only uploads that were never loaded can go this way:
    a loaded file's rows are in the workspace, and are removed with DataView instead."""

    def delete(self, request, pk):
        b = self.batch(pk)
        if b.status == UploadBatch.Status.LOADED:
            raise ValidationError({"detail": "This file's rows are in your workspace. Remove them with \"Remove data\" for this kind of file."})
        with transaction.atomic():
            delete_file_after_commit(b.file)
            b.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class DataView(MerchantAPIView):
    """Remove uploaded data, one kind at a time or all of it. The body must say "remove" in `confirm`,
    so a stray request cannot wipe a workspace."""
    parser_classes = [JSONParser]

    def post(self, request):
        if request.data.get("confirm") != "remove":
            raise ValidationError({"confirm": 'Send "remove" to confirm.'})
        kinds = request.data.get("kinds")
        if kinds == "all":
            return Response(clear_everything(self.merchant()))
        if not isinstance(kinds, list) or not kinds or any(k not in KINDS for k in kinds):
            raise ValidationError({"kinds": f'Send "all" or a list taken from: {", ".join(KINDS)}'})
        return Response(clear(self.merchant(), kinds))


class CommitView(MerchantAPIView):
    """Step 3. Load the valid rows. All of them go in, or none do.
    With {"replace": true} the rows of this kind already in the workspace are removed first, in the same
    transaction, so the new file takes their place instead of being added to them."""

    def post(self, request, pk):
        with RequestTimer("commit", batch_id=pk) as t:
            b = self.batch(pk)
            t.set(dataset_type=b.dataset_type, merchant_id=b.merchant_id)
            if b.status != UploadBatch.Status.VALIDATED:
                raise ValidationError("Validate this upload before committing it.")
            raw = read_file(b.file, timer=t)
            with t.step("validate"):
                clean, report = run_validation(raw, b.dataset_type, b.column_mapping, b.merchant)
            t.set(valid_rows=len(clean))
            if clean.empty:
                raise ValidationError("No valid rows to load.")
            replace = request.data.get("replace") is True
            t.set(replace=replace)
            with t.step("transaction"):  # every step below plus the COMMIT
                with transaction.atomic():
                    if replace:
                        with t.step("clear"):
                            clear(b.merchant, [b.dataset_type], rebuild=False, keep=b.id)
                    with t.step("load"):  # inserting the rows
                        b.load_result = LOADERS[b.dataset_type](clean, b.merchant)
                    b.quality_report, b.status = report, UploadBatch.Status.LOADED
                    with t.step("save"):
                        b.save()
                    with t.step("rebuild_ledger"):
                        ledger = rebuild_ledger(b.merchant)
                    with t.step("run_audit"):
                        audit = run_audit(b.merchant)
            t.set(ledger_rows=ledger.get("rows"), findings=audit.get("findings"))
            return Response({**summary(b), "ledger": ledger, "audit": audit})
