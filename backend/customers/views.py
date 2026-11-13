from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.response import Response

from audit.views import whole_number
from core.models import Customer
from ingestion.validators import hash_phone
from ingestion.views import MerchantAPIView
from ml.score import MOBILE

from .profiles import SEGMENTS, as_row, customer_table, profile, segment_summary

SORTS = {"returned": "returned", "rto_rate": "rto_rate_pct", "orders": "orders", "value": "delivered_value",
         "recent": "last_order"}
MAX_LIMIT = 500


class CustomerListView(MerchantAPIView):
    """?segment=  ?search= (name, customer ID or pincode)  ?sort=returned|rto_rate|orders|value|recent
    ?limit= (default 50, max 500)  ?offset="""

    def get(self, request):
        q = request.query_params
        segment, sort = q.get("segment"), q.get("sort", "orders")
        if segment and segment not in SEGMENTS:
            raise ValidationError({"segment": f"Must be one of: {', '.join(SEGMENTS)}"})
        if sort not in SORTS:
            raise ValidationError({"sort": f"Must be one of: {', '.join(SORTS)}"})
        limit = whole_number(request, "limit", 50, MAX_LIMIT)
        offset = whole_number(request, "offset", 0)

        t = customer_table(self.merchant())
        if t.empty:
            return Response({"count": 0, "results": []})
        if segment:
            t = t[t.segment == segment]
        if q.get("search"):
            s = q["search"].strip().lower()
            t = t[t["name"].fillna("").str.lower().str.contains(s, regex=False)
                  | t.customer_ref.fillna("").str.lower().str.contains(s, regex=False) | (t.pincode == s)]
        # customer_id breaks every tie, so limit/offset pages never overlap or skip a customer
        t = t.sort_values([SORTS[sort], "parcels", "customer_id"], ascending=[False, False, True],
                          na_position="last", kind="stable")
        return Response({"count": len(t), "results": [as_row(r) for _, r in t.iloc[offset:offset + limit].iterrows()]})


class SegmentView(MerchantAPIView):
    def get(self, request):
        return Response(segment_summary(self.merchant()))


class CustomerLookupView(MerchantAPIView):
    """Find one of this merchant's customers by ?customer_id= or ?phone= (customer_id wins if both are given).
    The phone number is hashed to look the customer up; it is never stored or returned."""

    def get(self, request):
        ref, phone = request.query_params.get("customer_id"), request.query_params.get("phone")
        mine = Customer.objects.for_merchant(self.merchant())
        if ref:
            customer = mine.filter(external_id=ref).first()
        elif phone:
            digits = "".join(ch for ch in phone if ch.isdigit())[-10:]
            if not MOBILE.fullmatch(digits):
                raise ValidationError({"phone": "Enter a 10-digit mobile number starting with 6, 7, 8 or 9."})
            h = hash_phone(digits)
            customer = mine.filter(phone_hash=h).first() or mine.filter(external_id="PH-" + h[:16]).first()
        else:
            raise ValidationError({"detail": "Pass customer_id or phone."})
        if customer is None:
            raise NotFound("No customer with that ID or phone number.")
        return Response(profile(self.merchant(), customer))
