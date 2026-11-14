from django.contrib import admin
from django.urls import include, path

from core.views import WorkspaceStatusView, health

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/health/", health),
    path("api/workspace/status/", WorkspaceStatusView.as_view()),
    path("api/ingestion/", include("ingestion.urls")),
    path("api/", include("ledger.urls")),
    path("api/", include("audit.urls")),
    path("api/", include("ml.urls")),
    path("api/", include("customers.urls")),
    path("api/", include("accounts.urls")),
    path("api/", include("reports.urls")),
]
