import hashlib
from datetime import date
from functools import wraps
from django.core.cache import cache
from django.http import JsonResponse
from django.utils import timezone
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import InvalidToken, AuthenticationFailed
from .models import FreeUsage, APIKey, APIRequestLog
from .plan_config import get_plan_limits


def get_client_ip(request):
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        return x_forwarded_for.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR')


def _check_api_key_total_limit(request):
    """X-API-Key header -> validate key -> check TOTAL calls (lifetime, not daily)."""
    raw_key = request.META.get('HTTP_X_API_KEY', '')
    if not raw_key:
        return True, None

    key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
    try:
        api_key = APIKey.objects.select_related('customer').get(key_hash=key_hash, is_active=True)
    except APIKey.DoesNotExist:
        return False, JsonResponse({"error": "Invalid or revoked API key"}, status=401)

    customer = api_key.customer
    if not customer.is_active:
        return False, JsonResponse({"error": "Account inactive"}, status=403)

    limits = get_plan_limits(customer.plan)
    total_allowed = limits["total_calls"]

    total_used = APIRequestLog.objects.filter(api_key=api_key).count()
    if total_used >= total_allowed:
        return False, JsonResponse({
            "error": "API key has reached its lifetime call limit",
            "detail": f"Free plan allows {total_allowed} total calls. Register a new account for additional calls.",
            "used": total_used,
            "limit": total_allowed,
        }, status=429)

    request._wa_api_key = api_key
    request._wa_limits = limits
    request._wa_total_used = total_used
    return True, None


def _check_jwt_total_limit(request):
    """JWT token found -> user ke total calls check karo (no API key)."""
    auth_header = request.META.get('HTTP_AUTHORIZATION', '')
    if not auth_header.startswith('Bearer '):
        return True, None

    try:
        token = JWTAuthentication().get_validated_token(auth_header.split(' ')[1])
        user_id = token.get('user_id')
    except (InvalidToken, AuthenticationFailed):
        return True, None

    if not user_id:
        return True, None

    limits = get_plan_limits("free")
    total_allowed = limits["total_calls"]

    total_key = f"jwt_total:{user_id}"
    total_used = cache.get(total_key, 0)

    if total_used >= total_allowed:
        return False, JsonResponse({
            "error": "Free account call limit reached",
            "detail": f"Free plan allows {total_allowed} total calls. Register a new account for additional calls.",
            "used": total_used,
            "limit": total_allowed,
        }, status=429)

    cache.set(total_key, total_used + 1, timeout=None)
    return True, None


def free_usage_limit(endpoint_name, max_free=100):
    """
    3-step rate limiting for website views:
    1. X-API-Key header -> total-calls limit (free=100 lifetime)
    2. JWT token (no API key) -> total-calls limit (100 lifetime per user)
    3. Anonymous -> IP-based daily limit (max_free/day)
    """
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            # Step 1: API key check (total calls lifetime)
            allowed, response = _check_api_key_total_limit(request)
            if not allowed:
                return response
            if hasattr(request, '_wa_api_key'):
                api_key = request._wa_api_key
                resp = view_func(request, *args, **kwargs)
                APIRequestLog.objects.create(
                    api_key=api_key, endpoint=request.path,
                    status_code=resp.status_code
                )
                api_key.last_used_at = timezone.now()
                api_key.save(update_fields=['last_used_at'])
                remaining = max(0, request._wa_limits["total_calls"] - request._wa_total_used - 1)
                resp["X-RateLimit-Total"] = str(request._wa_limits["total_calls"])
                resp["X-RateLimit-Remaining"] = str(remaining)
                return resp

            # Step 2: JWT check (total calls lifetime)
            allowed, response = _check_jwt_total_limit(request)
            if not allowed:
                return response

            # Step 3: IP-based daily fallback
            ip = get_client_ip(request)
            usage, created = FreeUsage.objects.get_or_create(
                ip_address=ip, endpoint=endpoint_name, date=date.today(),
                defaults={'count': 1}
            )
            if not created:
                if usage.count >= max_free:
                    return JsonResponse({
                        "error": "Daily free limit reached. Register to continue.",
                        "register_url": "/api/auth/register/"
                    }, status=429)
                usage.count += 1
                usage.save()

            return view_func(request, *args, **kwargs)
        return wrapper
    return decorator
