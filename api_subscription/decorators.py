import hashlib
from datetime import date
from functools import wraps
from django.conf import settings
from django.core.cache import cache
from django.db import IntegrityError, transaction
from django.db.models import F
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


def _check_logged_in_user(request):
    """Website ka logged-in user (JWT) — UNLIMITED access.

    Returns (is_logged_in, error_response).
      is_logged_in True  -> yeh banda logged-in hai; caller ko foran view
                            chala kar RETURN karna hai (IP quota na chhuo)
      error_response      -> sirf tab jab burst guard lag gaya ho

    Pehle yahan 100-calls-LIFETIME limit thi (cache counter mein), jo
    business model ke mutabiq sirf DEVELOPERS (API keys) ke liye honi
    chahiye thi — website ke logged-in user ke liye nahi. Aur woh counter
    LocMemCache mein tha, to restart pe khatam aur har worker mein alag —
    yani woh limit bharosay ke qabil bhi nahi thi.
    """
    auth_header = request.META.get('HTTP_AUTHORIZATION', '')
    if not auth_header.startswith('Bearer '):
        return False, None

    try:
        token = JWTAuthentication().get_validated_token(auth_header.split(' ')[1])
        user_id = token.get('user_id')
    except (InvalidToken, AuthenticationFailed):
        # Kharab/expire token = logged-in nahi. Anonymous ki tarah treat karo.
        return False, None

    if not user_id:
        return False, None

    per_minute = getattr(settings, 'LOGGED_IN_PER_MINUTE', 60)
    if not per_minute:
        return True, None          # 0 = bilkul unlimited, koi guard nahi

    # Atomic burst counter (cache.add + cache.incr) — get-then-set race se bacho.
    minute_key = f"user_minute:{user_id}:{timezone.now().strftime('%Y%m%d%H%M')}"
    cache.add(minute_key, 0, timeout=120)
    try:
        used = cache.incr(minute_key)
    except ValueError:
        cache.set(minute_key, 1, timeout=120)
        used = 1

    if used > per_minute:
        return True, JsonResponse({
            "code": "rate_limited",
            "error": "Too many requests. Please slow down and try again.",
            "detail": f"Max {per_minute} requests per minute per account.",
            "limit_per_minute": per_minute,
        }, status=429)

    return True, None


def free_usage_limit(endpoint_name, max_free=None, anon_per_minute=None):
    """Website endpoints ka access control — teen tarah ke users.

    1. X-API-Key header  -> DEVELOPER. Plan limits (free = 100 LIFETIME).
    2. Bearer JWT token  -> WEBSITE KA LOGGED-IN USER. UNLIMITED, sirf
                            settings.LOGGED_IN_PER_MINUTE ka burst guard.
    3. Kuch nahi         -> ANONYMOUS VISITOR. settings.FREE_DAILY_LIMIT
                            calls per din per IP, phir "signup karo".

    Har layer apna faisla kar ke RETURN karti hai — neeche wali layer ka
    quota nahi khaati.

    anon_per_minute: BROWSING endpoints ke liye. Set ho to anonymous
        visitor par 3-per-DIN wala feature quota NAHI lagta; us ki jagah
        ek kushada per-IP-per-MINUTE burst guard lagta hai.

        Kyun zaroorat pesh aayi: landing page khud load hote waqt
        /weather/current/ ko 17 dafa call karta hai (hero card + 16
        popular-destination cards). Un par 3-per-din ka feature quota
        lagane ka natija yeh tha ke anonymous visitor ko home page hi
        429 de deta tha — site khulti hi nahi thi.

        Site ka basic browsing (weather dikhana) kabhi quota par nahi
        hona chahiye. 3-free-then-signup model SIRF features ke liye
        hai: trip planner, country recommend, event risk.

    .env knobs:  FREE_DAILY_LIMIT=3   LOGGED_IN_PER_MINUTE=60
                 WEATHER_ANON_PER_MINUTE=240
    """
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            # Request ke waqt padho, import ke waqt nahi — testing aur
            # settings override dono theek kaam karte hain.
            limit = settings.FREE_DAILY_LIMIT if max_free is None else max_free
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

            # Step 2: website ka logged-in user -> UNLIMITED.
            # Yahan FORAN return karna zaroori hai. Pehle yeh return nahi
            # karta tha, to logged-in user neeche anonymous wale IP quota
            # mein bhi ginti karwa leta tha — yani login karne se usay ek
            # bhi extra call nahi milti thi.
            logged_in, response = _check_logged_in_user(request)
            if response is not None:
                return response
            if logged_in:
                return view_func(request, *args, **kwargs)

            # Step 3a: BROWSING endpoints — feature quota nahi, sirf
            # burst guard. Ek page load 17 calls karta hai, is liye limit
            # kushada hai: aam visitor kabhi nahi takrayega, scraper
            # takrayega.
            if anon_per_minute is not None:
                ip = get_client_ip(request)
                key = f"anon_browse:{endpoint_name}:{ip}:{timezone.now().strftime('%Y%m%d%H%M')}"
                cache.add(key, 0, timeout=120)
                try:
                    used = cache.incr(key)
                except ValueError:
                    cache.set(key, 1, timeout=120)
                    used = 1
                if used > anon_per_minute:
                    return JsonResponse({
                        "code": "rate_limited",
                        "error": "Too many requests. Please slow down and try again.",
                        "detail": f"Max {anon_per_minute} requests per minute.",
                        "limit_per_minute": anon_per_minute,
                    }, status=429)
                return view_func(request, *args, **kwargs)

            # Step 3b: features ka IP-based daily quota — ATOMIC.
            # Pehle `usage.count += 1; usage.save()` tha: read-modify-write,
            # yani parallel requests mein increments gum ho jate the aur
            # user limit se zyada calls kar sakta tha. Ab single atomic
            # UPDATE ... SET count = count + 1 WHERE count < max_free.
            ip = get_client_ip(request)
            base = FreeUsage.objects.filter(
                ip_address=ip, endpoint=endpoint_name, date=date.today()
            )

            # Ek atomic UPDATE: count badhao SIRF tab jab limit se kam ho.
            # 1 return hua = quota mila, 0 = nahi mila.
            def _claim():
                return base.filter(count__lt=limit).update(count=F('count') + 1)

            granted = _claim()

            if not granted:
                # Do wajah ho sakti hain: (a) row hi nahi hai (is IP ki aaj
                # pehli request), ya (b) limit khatam ho gayi.
                if base.exists():
                    # Row hai. Ya to limit khatam, ya kisi parallel request ne
                    # abhi abhi row banai thi — dobara claim karke confirm karo.
                    granted = _claim()
                else:
                    # NOTE: `date` field auto_now_add hai, is liye explicitly
                    # pass nahi kar rahe (Django use ignore karta hai).
                    try:
                        with transaction.atomic():
                            FreeUsage.objects.create(
                                ip_address=ip, endpoint=endpoint_name, count=1
                            )
                        granted = 1
                    except IntegrityError:
                        # Do parallel "pehli" requests — doosri ne row bana di.
                        granted = _claim()

            if not granted:
                return JsonResponse({
                    # `code` frontend ke liye hai. Pehle sirf angrezi text
                    # tha, aur frontend ko 429 se yeh pata hi nahi chalta
                    # tha ke "signup karo" wali baat hai ya "thora ruk jao"
                    # wali — dono 429 hain. Text par match karna nazuk hai
                    # (text badla to UI toot jaye), is liye alag code.
                    "code": "free_limit_reached",
                    "error": "Daily free limit reached",
                    "detail": f"You get {limit} free "
                              f"{'check' if limit == 1 else 'checks'} per day without "
                              f"an account. Create a free account to continue — "
                              f"it only takes a minute.",
                    "limit": limit,
                    "used": limit,
                    "feature": endpoint_name,
                    "register_url": "/api/auth/register/"
                }, status=429)

            response = view_func(request, *args, **kwargs)

            # Quota WAPIS karo agar request kaamyaab nahi hui. Galat date,
            # missing param (4xx) ya Open-Meteo down (5xx) — in mein user ka
            # koi qusoor nahi aur koi data bhi nahi mila, to unka din ka
            # quota kharch nahi hona chahiye. (Claim pehle hota hai taake
            # parallel requests limit se aage na nikal jayein.)
            if response.status_code >= 400:
                base.filter(count__gt=0).update(count=F('count') - 1)

            return response
        return wrapper
    return decorator
