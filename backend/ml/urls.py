from django.urls import path

from .views import EconomicsView, ModelView, ScoreBatchView, ScoreView, TrainView

# mounted under "api/" in config/urls.py
urlpatterns = [
    path("ml/train/", TrainView.as_view()),
    path("ml/model/", ModelView.as_view()),
    path("ml/economics/", EconomicsView.as_view()),
    path("risk/score/", ScoreView.as_view()),
    path("risk/score-batch/", ScoreBatchView.as_view()),
]
