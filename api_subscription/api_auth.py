import hashlib
from datetime import date
from functools import wraps
from django.core.cache import cache
from django.http import JsonResponse
from django.utils import timezone
from .models import APIKey, APIRequestLog
from .plan_config import get_plan_limits


def require_api_key(feature=None):
    """
    B2B API endpoints ke liye — X-API-Key header check karta hai,
    plan ke hisaab se daily + per-minute rate limit lagata hai.
    Agar feature diya gaya ho toh key ke allowed_features check karta hai.
    """
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            raw_key = request.META.get('HTTP_X_API_KEY', '')
            if not raw_key:
                return JsonResponse({
                    "error": "Missing API key",
                    "detail": "Include your API key in the X-API-Key header"
                }, status=401)

            key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
            try:
                api_key = APIKey.objects.select_related('customer').get(key_hash=key_hash, is_active=True)
            except APIKey.DoesNotExist:
                return JsonResponse({"error": "Invalid or revoked API key"}, status=401)

            if feature and api_key.allowed_features and feature not in api_key.allowed_features:
                return JsonResponse({
                    "error": f"This API key does not have access to the '{feature}' feature",
                    "detail": "Generate a new API key with this feature enabled",
                }, status=403)

            customer = api_key.customer
            if not customer.is_active:
                return JsonResponse({"error": "Account inactive"}, status=403)

            limits = get_plan_limits(customer.plan)

            # Per-minute burst limit (cache-based, fast)
            minute_key = f"ratelimit:minute:{api_key.id}:{timezone.now().strftime('%Y%m%d%H%M')}"
            minute_count = cache.get(minute_key, 0)
            if minute_count >= limits["requests_per_minute"]:
                return JsonResponse({
                    "error": "Rate limit exceeded",
                    "detail": f"Max {limits['requests_per_minute']} requests per minute for {customer.plan} plan"
                }, status=429)
            cache.set(minute_key, minute_count + 1, timeout=60)

            # Daily quota (cache-based, sirf din mein ek baar DB query)
            today_key = f"daily_quota:{api_key.id}:{date.today().isoformat()}"
            today_count = cache.get(today_key)

            if today_count is None:
                today_count = APIRequestLog.objects.filter(
                    api_key=api_key, timestamp__date=date.today()
                ).count()

            if today_count >= limits["daily_calls"]:
                return JsonResponse({
                    "error": "Daily quota exceeded",
                    "detail": f"Daily limit of {limits['daily_calls']} calls reached for {customer.plan} plan",
                    "upgrade_url": "/api/pricing/"
                }, status=429)

            cache.set(today_key, today_count + 1, timeout=86400)

            # Log this request + update last_used
            response = view_func(request, *args, **kwargs)
            APIRequestLog.objects.create(
                api_key=api_key, endpoint=request.path,
                status_code=response.status_code
            )
            api_key.last_used_at = timezone.now()
            api_key.save(update_fields=['last_used_at'])

            # Rate limit info headers (industry standard)
            remaining = max(0, limits["daily_calls"] - today_count - 1)
            response["X-RateLimit-Limit"] = str(limits["daily_calls"])
            response["X-RateLimit-Remaining"] = str(remaining)
            response["X-RateLimit-Plan"] = customer.plan

            return response
        return wrapper
    return decorator
