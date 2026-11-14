from django.urls import path

from .views import ReportListView, ReportPdfView

urlpatterns = [
    path("reports/", ReportListView.as_view()),
    path("reports/<slug:key>.pdf", ReportPdfView.as_view()),
]
