import hashlib
from datetime import date
from functools import wraps
from django.core.cache import cache
from django.http import JsonResponse
from django.utils import timezone
from .models import APIKey, APIRequestLog
from .plan_config import UNLIMITED, get_plan_limits


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

            # Lifetime total-calls limit. Yeh check pehle sirf website
            # decorator (decorators.py) mein tha, is liye free plan ki key
            # /api/v1/ endpoints pe apni 100-call lifetime limit ke baghair
            # chal jati thi (daily_calls free plan ke liye 999999 hai).
            total_allowed = limits["total_calls"]
            if total_allowed < UNLIMITED:
                total_used = APIRequestLog.objects.filter(api_key=api_key).count()
                if total_used >= total_allowed:
                    return JsonResponse({
                        "error": "API key has reached its lifetime call limit",
                        "detail": f"{customer.plan.title()} plan allows {total_allowed} total calls.",
                        "used": total_used,
                        "limit": total_allowed,
                    }, status=429)

            # Per-minute burst limit — ATOMIC (cache.add + cache.incr).
            # Pehle get-then-set tha: do parallel requests same value
            # padh kar dono allow ho jati thi.
            minute_key = f"ratelimit:minute:{api_key.id}:{timezone.now().strftime('%Y%m%d%H%M')}"
            cache.add(minute_key, 0, timeout=120)
            try:
                minute_count = cache.incr(minute_key)
            except ValueError:
                # Key add ke baad expire ho gayi — dobara seed karo.
                cache.set(minute_key, 1, timeout=120)
                minute_count = 1
            if minute_count > limits["requests_per_minute"]:
                return JsonResponse({
                    "error": "Rate limit exceeded",
                    "detail": f"Max {limits['requests_per_minute']} requests per minute for {customer.plan} plan"
                }, status=429)

            # Daily quota — bhi atomic. Cache miss pe ek dafa DB se seed.
            today_key = f"daily_quota:{api_key.id}:{date.today().isoformat()}"
            if cache.get(today_key) is None:
                seed = APIRequestLog.objects.filter(
                    api_key=api_key, timestamp__date=date.today()
                ).count()
                cache.add(today_key, seed, timeout=86400)
            try:
                today_count = cache.incr(today_key)
            except ValueError:
                cache.set(today_key, 1, timeout=86400)
                today_count = 1

            if today_count > limits["daily_calls"]:
                return JsonResponse({
                    "error": "Daily quota exceeded",
                    "detail": f"Daily limit of {limits['daily_calls']} calls reached for {customer.plan} plan",
                    "upgrade_url": "/api/pricing/"
                }, status=429)

            # Log this request + update last_used
            response = view_func(request, *args, **kwargs)
            APIRequestLog.objects.create(
                api_key=api_key, endpoint=request.path,
                status_code=response.status_code
            )
            api_key.last_used_at = timezone.now()
            api_key.save(update_fields=['last_used_at'])

            # Rate limit info headers (industry standard)
            remaining = max(0, limits["daily_calls"] - today_count)
            response["X-RateLimit-Limit"] = str(limits["daily_calls"])
            response["X-RateLimit-Remaining"] = str(remaining)
            response["X-RateLimit-Plan"] = customer.plan

            return response
        return wrapper
    return decorator
