from django.urls import path
from . import views, v1_views
from rest_framework_simplejwt.views import TokenRefreshView

urlpatterns = [
    path("register/", views.register_request, name="register"),
    path("verify-otp/", views.verify_registration_otp, name="verify_otp"),
    path("login/", views.login_view, name="login"),
    path("forgot-password/", views.forgot_password_request, name="forgot_password"),
    path("reset-password/", views.forgot_password_confirm, name="reset_password"),
    path("google-login/", views.google_login, name="google_login"),
    path("refresh/", TokenRefreshView.as_view(), name="token_refresh"),
    path("keys/generate/", views.generate_api_key, name="generate_api_key"),
    path("keys/", views.list_api_keys, name="list_api_keys"),
    path("keys/<int:key_id>/revoke/", views.revoke_api_key, name="revoke_api_key"),
]
