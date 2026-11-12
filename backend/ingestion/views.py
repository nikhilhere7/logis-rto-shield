from django.db import transaction
from rest_framework import status
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.generics import get_object_or_404
from rest_framework.parsers import JSONParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from audit.engine import run_audit
from ledger.build import rebuild_ledger

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
        kind, f = request.data.get("dataset_type"), request.FILES.get("file")
        if kind not in SPECS:
            raise ValidationError({"dataset_type": f"Must be one of: {', '.join(SPECS)}"})
        if f is None or not f.name.lower().endswith((".csv", ".xlsx", ".xls")):
            raise ValidationError({"file": "Upload a .csv or .xlsx file."})
        b = UploadBatch.objects.create(merchant=self.merchant(), dataset_type=kind, file=f,
                                       original_filename=f.name, uploaded_by=request.user)
        try:
            raw = read_file(b.file.path)
        except Exception as e:
            b.status = UploadBatch.Status.FAILED
            b.save(update_fields=["status"])
            raise ValidationError({"file": f"Could not read the file: {e}"})
        spec = SPECS[kind]
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
        b = self.batch(pk)
        if b.status == UploadBatch.Status.LOADED:
            raise ValidationError("This upload is already loaded.")
        mapping = {**b.column_mapping, **(request.data.get("mapping") or {})}
        try:
            _, report = run_validation(read_file(b.file.path), b.dataset_type, mapping, b.merchant)
        except MappingError as e:
            raise ValidationError({"mapping": str(e)})
        b.column_mapping, b.quality_report, b.status = mapping, report, UploadBatch.Status.VALIDATED
        b.save()
        return Response(summary(b))


class CommitView(MerchantAPIView):
    """Step 3. Load the valid rows. All of them go in, or none do."""

    def post(self, request, pk):
        b = self.batch(pk)
        if b.status != UploadBatch.Status.VALIDATED:
            raise ValidationError("Validate this upload before committing it.")
        clean, report = run_validation(read_file(b.file.path), b.dataset_type, b.column_mapping, b.merchant)
        if clean.empty:
            raise ValidationError("No valid rows to load.")
        with transaction.atomic():
            b.load_result = LOADERS[b.dataset_type](clean, b.merchant)
            b.quality_report, b.status = report, UploadBatch.Status.LOADED
            b.save()
            ledger = rebuild_ledger(b.merchant)
            audit = run_audit(b.merchant)
        return Response({**summary(b), "ledger": ledger, "audit": audit})
