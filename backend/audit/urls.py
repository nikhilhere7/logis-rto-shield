from django.urls import path

from .views import DisputeFileView, FindingsView, RunView, SummaryView

# mounted under "api/" in config/urls.py
urlpatterns = [
    path("audit/run/", RunView.as_view()),
    path("audit/summary/", SummaryView.as_view()),
    path("audit/findings/", FindingsView.as_view()),
    path("audit/disputes.csv", DisputeFileView.as_view()),
]
