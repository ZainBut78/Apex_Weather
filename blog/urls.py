from django.urls import path

from . import views

urlpatterns = [
    path("posts/", views.blog_list_view, name="blog_list"),
    path("posts/<slug:slug>/", views.blog_detail_view, name="blog_detail"),
]
