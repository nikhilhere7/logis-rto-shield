from django.urls import path

from .views import CustomerListView, CustomerLookupView, SegmentView

urlpatterns = [
    path("customers/", CustomerListView.as_view()),
    path("customers/segments/", SegmentView.as_view()),
    path("customers/lookup/", CustomerLookupView.as_view()),
]
