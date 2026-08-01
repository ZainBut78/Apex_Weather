from django.urls import path
from . import views

urlpatterns = [
    path("current/", views.current_weather_view, name="current_weather"),
    path("history/", views.get_historical_overview, name="historical_overview"),
]
