from django.urls import path
from . import views

urlpatterns = [
    path("", views.trip_plan_view, name="trip_plan"),
    path("recommend/", views.country_recommend_view, name="country_recommend"),
    path("cities/search/", views.city_search_view, name="city_search"),
]
