from django.urls import path

from .views import CodView, DeliveryView, MonthlyView, OverviewView, RebuildView, RtoView

urlpatterns = [
    path("ledger/rebuild/", RebuildView.as_view()),
    path("metrics/overview/", OverviewView.as_view()),
    path("metrics/monthly/", MonthlyView.as_view()),
    path("metrics/rto/", RtoView.as_view()),
    path("metrics/delivery/", DeliveryView.as_view()),
    path("metrics/cod/", CodView.as_view()),
]
