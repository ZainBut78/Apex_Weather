from django.urls import path
from . import views

urlpatterns = [
    path("click/<int:product_id>/", views.affiliate_click_redirect, name="affiliate_click"),
]
