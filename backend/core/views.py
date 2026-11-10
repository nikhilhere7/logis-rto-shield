from rest_framework.decorators import api_view
from rest_framework.response import Response

from .models import Merchant


@api_view(["GET"])
def health(request):
    return Response({"status": "ok", "merchants": Merchant.objects.count()})
