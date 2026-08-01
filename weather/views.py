import json
import requests
import statistics
from collections import defaultdict
from datetime import date

from django.db.models import Avg, Count
from django.http import HttpResponse, JsonResponse
from django.shortcuts import render, get_object_or_404
from django.views.decorators.http import require_GET
from .services import get_current_and_forecast
from trip_planner.services import get_city
from .models import City, HistoricalWeather
from .utils.narrative import generate_narrative

ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"
HEADERS = {"User-Agent": "WeatherApex-HistoryFetch/1.0 (contact: dev@weathervibe.com)"}

MONTH_NAMES = ["January", "February", "March", "April", "May", "June",
               "July", "August", "September", "October", "November", "December"]


@require_GET
def current_weather_view(request):
    city_query = request.GET.get("city", "").strip()
    if not city_query:
        return JsonResponse({"error": "city parameter required"}, status=400)

    city = get_city(city_query)
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
        "current": data["current"],
        "forecast_7day": data["forecast_7day"],
        "hourly_today": data["hourly_today"],
    })


def fetch_and_store_historical(city, years_back=10):
    """
    Naye city ke liye ON-DEMAND fetch — sirf years_back saal ka
    data, taake response fast rahe. Same HistoricalWeather table
    mein store hota hai jo bulk job bhi use karta hai.
    """
    end_year = date.today().year - 1
    start_year = end_year - years_back + 1

    params = {
        "latitude": city.latitude,
        "longitude": city.longitude,
        "start_date": f"{start_year}-01-01",
        "end_date": f"{end_year}-12-31",
        "daily": "temperature_2m_max,temperature_2m_min,precipitation_sum,"
                 "sunshine_duration,relative_humidity_2m_mean",
        "timezone": "auto",
    }

    try:
        resp = requests.get(ARCHIVE_URL, params=params, headers=HEADERS, timeout=60)
    except requests.exceptions.RequestException:
        return False

    if resp.status_code != 200:
        return False

    data = resp.json()
    daily = data.get("daily", {})
    dates = daily.get("time", [])
    temp_max = daily.get("temperature_2m_max", [])
    temp_min = daily.get("temperature_2m_min", [])
    rainfall = daily.get("precipitation_sum", [])
    sunshine = daily.get("sunshine_duration", [])
    humidity = daily.get("relative_humidity_2m_mean", [])

    # Year+month ke hisaab se group karke store karo
    grouped = defaultdict(lambda: {"tmax": [], "tmin": [], "rain": [], "sun": [], "hum": []})

    for i, d in enumerate(dates):
        dt = date.fromisoformat(d)
        key = (dt.year, dt.month)
        if i < len(temp_max) and temp_max[i] is not None: grouped[key]["tmax"].append(temp_max[i])
        if i < len(temp_min) and temp_min[i] is not None: grouped[key]["tmin"].append(temp_min[i])
        if i < len(rainfall) and rainfall[i] is not None: grouped[key]["rain"].append(rainfall[i])
        if i < len(sunshine) and sunshine[i] is not None: grouped[key]["sun"].append(sunshine[i])
        if i < len(humidity) and humidity[i] is not None: grouped[key]["hum"].append(humidity[i])

    for (year, month), vals in grouped.items():
        rainy_count = sum(1 for r in vals["rain"] if r > 1.0)
        HistoricalWeather.objects.update_or_create(
            city=city, year=year, month=month,
            defaults={
                "avg_temp_max": round(statistics.mean(vals["tmax"]), 1) if vals["tmax"] else 0,
                "avg_temp_min": round(statistics.mean(vals["tmin"]), 1) if vals["tmin"] else 0,
                "avg_rainfall": round(statistics.mean(vals["rain"]), 1) if vals["rain"] else 0,
                "rainy_days": round(rainy_count / len(vals["rain"]) * 30) if vals["rain"] else 0,
                "sunshine_hours": round(statistics.mean(vals["sun"]) / 3600, 1) if vals["sun"] else 0,
                "avg_humidity": round(statistics.mean(vals["hum"]), 1) if vals["hum"] else 0,
            }
        )

    return True


@require_GET
def get_historical_overview(request):
    city_query = request.GET.get("city", "").strip()
    if not city_query:
        return JsonResponse({"error": "city parameter required"}, status=400)

    city = get_city(city_query)  # DB check + geocoding fallback (existing function)
    if not city:
        return JsonResponse({"error": "City not found"}, status=404)

    # STEP A — Check: is city ka kitna historical data DB mein hai?
    existing_months = HistoricalWeather.objects.filter(city=city).values("month").distinct().count()

    if existing_months < 12:
        # DB mein incomplete/missing hai — ON-DEMAND fetch karo
        success = fetch_and_store_historical(city, years_back=10)
        if not success:
            return JsonResponse({"error": "Could not fetch historical data"}, status=503)

    # STEP B — Ab DB se aggregate karke response banao
    monthly_data = []
    for month in range(1, 13):
        agg = HistoricalWeather.objects.filter(city=city, month=month).aggregate(
            avg_high=Avg("avg_temp_max"),
            avg_low=Avg("avg_temp_min"),
            avg_rainfall=Avg("avg_rainfall"),
            avg_rainy_days=Avg("rainy_days"),
            avg_sunshine=Avg("sunshine_hours"),
            avg_humidity=Avg("avg_humidity"),
        )
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

    # Pehle DB check karo (jaisa lazy-fetch API mein tha)
    existing_months = HistoricalWeather.objects.filter(city=city).values("month").distinct().count()
    if existing_months < 12:
        fetch_and_store_historical(city, years_back=10)

    monthly_data = []
    for month_num in range(1, 13):
        agg = HistoricalWeather.objects.filter(city=city, month=month_num).aggregate(
            avg_high=Avg("avg_temp_max"),
            avg_low=Avg("avg_temp_min"),
            avg_rainfall=Avg("avg_rainfall"),
            avg_rainy_days=Avg("rainy_days"),
        )
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
    cities = City.objects.all()
    xml_parts = ['<?xml version="1.0" encoding="UTF-8"?>']
    xml_parts.append('<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">')

    xml_parts.append('<url><loc>https://weatherapex.com/</loc></url>')

    for city in cities:
        xml_parts.append(f'<url><loc>https://weatherapex.com/weather/{city.slug}/</loc></url>')

    xml_parts.append('</urlset>')

    return HttpResponse(''.join(xml_parts), content_type="application/xml")
