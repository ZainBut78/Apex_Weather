from django.urls import path
from . import views

urlpatterns = [
    path("", views.event_risk_view, name="event_risk"),
]
