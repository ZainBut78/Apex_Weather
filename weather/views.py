import json
import logging

from django.conf import settings
from django.db.models import Avg
from django.http import HttpResponse, JsonResponse
from django.shortcuts import render, get_object_or_404
from django.views.decorators.http import require_GET
from .services import get_current_and_forecast, get_or_fetch_city_image, log_service_request
from trip_planner.services import get_city
from .models import City, HistoricalWeather
from .utils.narrative import generate_narrative
# Archive fetch + aggregation ab weather/historical.py mein hai (ek hi
# formula saare paths ke liye), is liye yahan ARCHIVE_URL/HEADERS aur
# requests/statistics/defaultdict ki zaroorat nahi rahi.
from .historical import (
    ensure_history,
    has_any_history,
    latest_complete_year,
    target_year_range,
)
from api_subscription.decorators import free_usage_limit

MONTH_NAMES = ["January", "February", "March", "April", "May", "June",
               "July", "August", "September", "October", "November", "December"]

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────────
# Weather dikhana = site ka BASIC BROWSING. Is par "3 free calls phir
# signup" wala feature quota NAHI lagta.
#
# Kyun: landing page khud load hote waqt is endpoint ko 17 dafa call
# karta hai (hero card + 16 popular-destination cards). 3-per-din ka
# quota lagane ka natija yeh tha ke anonymous visitor ko home page hi
# 429 de deta tha — site khulti hi nahi thi.
#
# Is ki jagah ek kushada per-IP-per-minute burst guard hai
# (WEATHER_ANON_PER_MINUTE, default 600). Aam visitor kabhi nahi
# takrayega; scraper takrayega.
#
# 3-free-then-signup model SIRF features par hai: trip planner,
# country recommend, event risk. Wahan waise hi lagta hai.
# ──────────────────────────────────────────────────────────────────────

@require_GET
@free_usage_limit(
    endpoint_name="weather_current",
    anon_per_minute=getattr(settings, "WEATHER_ANON_PER_MINUTE", 600),
)
def current_weather_view(request):
    city_query = request.GET.get("city", "").strip()
    if not city_query:
        return JsonResponse({"error": "city parameter required"}, status=400)

    city = get_city(city_query, feature="weather")
    if not city:
        return JsonResponse({"error": "City not found"}, status=404)

    data = get_current_and_forecast(city)
    if data is None:
        return JsonResponse({"error": "Could not fetch weather data"}, status=503)

    return JsonResponse({
        "city": city.name,
        "country": city.country,
        "latitude": city.latitude,
        "longitude": city.longitude,
        "image_url": get_or_fetch_city_image(city),
        "current": data["current"],
        "forecast_7day": data["forecast_7day"],
        "hourly_today": data["hourly_today"],
        "hourly_forecast": data.get("hourly_forecast", {}),
    })


def fetch_and_store_historical(city, years_back=None):
    """DEPRECATED — ab weather.historical.ensure_history() use karo.

    Yeh sirf backwards compatibility ke liye bacha hai. Purana version
    apna alag aggregation karta tha jisme `avg_rainfall` mahine ka TOTAL
    ke bajaye ROZ ka AVERAGE bharta tha — bulk commands se 30x farq.
    Ab sab kuch weather/historical.py ke ek hi formula se guzarta hai.

    years_back diya jaye to sirf utne saal, warna settings.HISTORICAL_YEARS.
    """
    if years_back:
        end_year = latest_complete_year()
        start_year = end_year - years_back + 1
    else:
        start_year, end_year = target_year_range()

    info = ensure_history(city, feature="weather",
                          start_year=start_year, end_year=end_year)
    return info["complete"]


@require_GET
@free_usage_limit(
    endpoint_name="weather_history",
    anon_per_minute=getattr(settings, "WEATHER_ANON_PER_MINUTE", 600),
)
def get_historical_overview(request):
    city_query = request.GET.get("city", "").strip()
    if not city_query:
        return JsonResponse({"error": "city parameter required"}, status=400)

    city = get_city(city_query, feature="weather")  # DB check + geocoding fallback (existing function)
    if not city:
        return JsonResponse({"error": "City not found"}, status=404)

    # STEP A — DB pehle. Sirf woh SAAL Open-Meteo se maango jo DB mein
    # complete nahi hain (incremental). Pehle yahan check tha
    # `distinct months < 12` — woh months ginta tha, saal nahi, is liye
    # ek saal ka data bhi "complete" lagta tha aur baqi 19 saal kabhi
    # nahi aate the. Aur fetch bhi sirf 10 saal ka hota tha.
    info = ensure_history(city, feature="weather")

    if info["api_calls"]:
        log_service_request("weather", "external", city.name)
    else:
        log_service_request("weather", "database", city.name)

    # Jo data maujood hai woh serve karo, chahe ek saal fetch fail hua ho.
    # 503 sirf tab jab bilkul kuch bhi na ho.
    if not has_any_history(city):
        return JsonResponse({"error": "Could not fetch historical data"}, status=503)

    # STEP B — Ab DB se aggregate karke response banao.
    # Pehle yeh loop 12 alag aggregate queries chalata tha (har month ke
    # liye ek). Ab ek hi GROUP BY month query se sab aa jata hai.
    by_month = {
        row["month"]: row
        for row in HistoricalWeather.objects.filter(city=city)
        .values("month")
        .annotate(
            avg_high=Avg("avg_temp_max"),
            avg_low=Avg("avg_temp_min"),
            avg_rainfall=Avg("avg_rainfall"),
            avg_rainy_days=Avg("rainy_days"),
            avg_sunshine=Avg("sunshine_hours"),
            avg_humidity=Avg("avg_humidity"),
        )
    }
    EMPTY_AGG = {
        "avg_high": None, "avg_low": None, "avg_rainfall": None,
        "avg_rainy_days": None, "avg_sunshine": None, "avg_humidity": None,
    }

    monthly_data = []
    for month in range(1, 13):
        agg = by_month.get(month, EMPTY_AGG)
        monthly_data.append({
            "month": month,
            "avg_high": round(agg["avg_high"], 1) if agg["avg_high"] else None,
            "avg_low": round(agg["avg_low"], 1) if agg["avg_low"] else None,
            "avg_rainfall": round(agg["avg_rainfall"], 1) if agg["avg_rainfall"] else None,
            "rainy_days": round(agg["avg_rainy_days"]) if agg["avg_rainy_days"] else None,
            "sunshine_hours": round(agg["avg_sunshine"], 1) if agg["avg_sunshine"] else None,
            "humidity": round(agg["avg_humidity"]) if agg["avg_humidity"] else None,
        })

    return JsonResponse({
        "city": city.name,
        "country": city.country,
        "monthly_data": monthly_data,
    })


def historical_page_view(request, city_slug):
    city = get_object_or_404(City, slug=city_slug)

    # Wahi incremental logic jo API endpoint use karta hai.
    info = ensure_history(city, feature="weather")
    if info["api_calls"]:
        log_service_request("weather", "external", city.name)
    else:
        log_service_request("weather", "database", city.name)

    # Yahan bhi 12 queries ki jagah ek GROUP BY month query.
    by_month = {
        row["month"]: row
        for row in HistoricalWeather.objects.filter(city=city)
        .values("month")
        .annotate(
            avg_high=Avg("avg_temp_max"),
            avg_low=Avg("avg_temp_min"),
            avg_rainfall=Avg("avg_rainfall"),
            avg_rainy_days=Avg("rainy_days"),
        )
    }
    EMPTY_AGG = {"avg_high": None, "avg_low": None,
                 "avg_rainfall": None, "avg_rainy_days": None}

    monthly_data = []
    for month_num in range(1, 13):
        agg = by_month.get(month_num, EMPTY_AGG)
        monthly_data.append({
            "month_name": MONTH_NAMES[month_num - 1],
            "avg_high": round(agg["avg_high"], 1) if agg["avg_high"] else "-",
            "avg_low": round(agg["avg_low"], 1) if agg["avg_low"] else "-",
            "avg_rainfall": round(agg["avg_rainfall"], 1) if agg["avg_rainfall"] else "-",
            "rainy_days": round(agg["avg_rainy_days"]) if agg["avg_rainy_days"] else "-",
        })

    narrative_text = generate_narrative(city.name, monthly_data)

    chart_months = [
        {
            "month": m["month_name"],
            "high": m["avg_high"] if m["avg_high"] != "-" else None,
            "low": m["avg_low"] if m["avg_low"] != "-" else None,
            "rain": m["avg_rainfall"] if m["avg_rainfall"] != "-" else None,
        }
        for m in monthly_data
    ]

    good_months = [
        m["month_name"] for m in monthly_data
        if m["avg_high"] != "-"
        and 17 <= m["avg_high"] <= 28
        and (m["avg_rainfall"] == "-" or m["avg_rainfall"] <= 80)
    ]
    best_months = ", ".join(good_months[:3]) if good_months else "varies by preference"

    packing = ["Light layers and comfortable walking shoes"]
    valid = [m for m in monthly_data if m["avg_high"] != "-"]
    if valid:
        wettest = max(valid, key=lambda m: m["avg_rainfall"] if m["avg_rainfall"] != "-" else 0)
        hottest = max(valid, key=lambda m: m["avg_high"])
        coldest = min(valid, key=lambda m: m["avg_high"])
        if wettest["avg_rainfall"] != "-" and wettest["avg_rainfall"] > 60:
            packing.append("A rain jacket or compact umbrella")
        if hottest["avg_high"] > 30:
            packing.append("Sunscreen, a sun hat and a refillable water bottle")
        if coldest["avg_high"] < 10:
            packing.append("A warm jacket or layers for cooler evenings")

    context = {
        "city": city,
        "monthly_data": monthly_data,
        "narrative_text": narrative_text,
        "years_of_data": 10,
        "chart_json": json.dumps(chart_months),
        "best_months": best_months,
        "packing": packing,
        "wettest_name": max((m for m in monthly_data if m["avg_rainfall"] != "-"), key=lambda m: m["avg_rainfall"])["month_name"] if any(m["avg_rainfall"] != "-" for m in monthly_data) else "",
        "hottest_name": max((m for m in monthly_data if m["avg_high"] != "-"), key=lambda m: m["avg_high"])["month_name"] if any(m["avg_high"] != "-" for m in monthly_data) else "",
        "coldest_name": min((m for m in monthly_data if m["avg_high"] != "-"), key=lambda m: m["avg_high"])["month_name"] if any(m["avg_high"] != "-" for m in monthly_data) else "",
    }
    return render(request, "weather/historical.html", context)


def sitemap_view(request):
    from blog.models import BlogPost
    # Domain hardcoded tha (3 jagah). Ab settings.SITE_URL se aata hai —
    # .env ki ek line badalne se poora sitemap update ho jata hai.
    base = settings.SITE_URL
    cities = City.objects.all()
    posts = BlogPost.objects.filter(is_published=True)
    xml_parts = ['<?xml version="1.0" encoding="UTF-8"?>']
    xml_parts.append('<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">')

    xml_parts.append(f'<url><loc>{base}/</loc></url>')

    for city in cities:
        xml_parts.append(f'<url><loc>{base}/weather/{city.slug}/</loc></url>')

    for post in posts:
        xml_parts.append(f'<url><loc>{base}/blog/{post.slug}/</loc></url>')

    xml_parts.append('</urlset>')

    return HttpResponse(''.join(xml_parts), content_type="application/xml")
