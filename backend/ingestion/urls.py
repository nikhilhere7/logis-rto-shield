from django.urls import path

from .views import CommitView, DataView, UploadDetailView, UploadView, ValidateView

urlpatterns = [
    path("uploads/", UploadView.as_view()),
    path("uploads/<int:pk>/", UploadDetailView.as_view()),
    path("uploads/<int:pk>/validate/", ValidateView.as_view()),
    path("uploads/<int:pk>/commit/", CommitView.as_view()),
    path("data/remove/", DataView.as_view()),
]
