from django.contrib import admin
from .models import APICustomer, APICallLog, OTPVerification, FreeUsage, APIKey, APIRequestLog


@admin.register(APICustomer)
class APICustomerAdmin(admin.ModelAdmin):
    list_display = ("user", "company_name", "plan", "signup_method", "is_active", "created_at")
    list_filter = ("plan", "signup_method", "is_active")
    search_fields = ("user__email", "company_name")


@admin.register(APICallLog)
class APICallLogAdmin(admin.ModelAdmin):
    list_display = ("customer", "endpoint", "timestamp")
    list_filter = ("timestamp",)


@admin.register(OTPVerification)
class OTPVerificationAdmin(admin.ModelAdmin):
    list_display = ("email", "otp_code", "purpose", "is_used", "attempts", "created_at", "expires_at")
    list_filter = ("purpose", "is_used")
    search_fields = ("email",)


@admin.register(FreeUsage)
class FreeUsageAdmin(admin.ModelAdmin):
    list_display = ("ip_address", "endpoint", "date", "count")
    list_filter = ("endpoint", "date")
    search_fields = ("ip_address",)


@admin.register(APIKey)
class APIKeyAdmin(admin.ModelAdmin):
    list_display = ("key_prefix", "customer", "name", "is_active", "created_at", "last_used_at")
    list_filter = ("is_active",)
    search_fields = ("key_prefix", "customer__user__email")


@admin.register(APIRequestLog)
class APIRequestLogAdmin(admin.ModelAdmin):
    list_display = ("api_key", "endpoint", "status_code", "timestamp")
    list_filter = ("status_code",)
