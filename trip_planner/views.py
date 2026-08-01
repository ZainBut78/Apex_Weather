from datetime import date
from django.http import JsonResponse
from django.views.decorators.http import require_GET

from .services import get_city, fetch_forecast, fetch_hourly_forecast, get_historical_estimate
from .scoring import calculate_day_score, calculate_day_parts
from .activity import recommend_daily_activity, ACTIVITY_TO_AFFILIATE_CATEGORY
from affiliates.engine import get_product_recommendations, get_products_by_category
from api_subscription.decorators import free_usage_limit


def build_trip_plan_response(city_query, start_str, end_str):
    """Pure function — HTTP se independent, dict return karta hai."""
    if not city_query:
        return {"error": "City parameter is required", "status": 400}
    if not start_str or not end_str:
        return {"error": "Start and end date parameters are required", "status": 400}

    try:
        start_date = date.fromisoformat(start_str)
        end_date = date.fromisoformat(end_str)
    except ValueError:
        return {"error": "Invalid date format. Use YYYY-MM-DD", "status": 400}

    if end_date < start_date:
        return {"error": "end_date must be after start_date", "status": 400}

    total_days = (end_date - start_date).days + 1
    if total_days > 20:
        return {"error": "Max 20 days supported for now", "status": 400}

    city = get_city(city_query)
    if city is None:
        return {"error": "City not found", "status": 404}

    today = date.today()
    days_until_end = (end_date - today).days

    if days_until_end <= 16:
        data_source = "forecast"
        raw = fetch_forecast(city.latitude, city.longitude, start_str, end_str)
    else:
        data_source = "historical_estimate"
        raw = get_historical_estimate(city, start_date, end_date)

    if raw is None:
        return {"error": "Could not fetch weather data", "status": 503}

    hourly_raw = None
    if data_source == "forecast":
        hourly_raw = fetch_hourly_forecast(city.latitude, city.longitude, start_str, end_str)

    days = []
    dates = raw.get("time", [])
    temp_max = raw.get("temperature_2m_max", [])
    temp_min = raw.get("temperature_2m_min", [])
    rain_prob = raw.get("precipitation_probability_max", [])
    wind = raw.get("wind_speed_10m_max", [])
    weather_codes = raw.get("weather_code", [])

    for i, d in enumerate(dates):
        t_max = temp_max[i] if i < len(temp_max) else 0
        t_min = temp_min[i] if i < len(temp_min) else 0
        rp = rain_prob[i] if i < len(rain_prob) else 0
        w = wind[i] if i < len(wind) else None
        wc = weather_codes[i] if i < len(weather_codes) else 0

        score = calculate_day_score(rp, w, t_max, t_min)

        activity = recommend_daily_activity(
            rp, w, t_max, city.is_coastal, city.has_hiking_trails
        )
        affiliate_category = ACTIVITY_TO_AFFILIATE_CATEGORY[activity]
        day_products = get_products_by_category(affiliate_category)

        days.append({
            "date": d,
            "score": score,
            "rain_probability": rp,
            "wind_kmh": w,
            "temp_max": t_max,
            "temp_min": t_min,
            "weather_code": wc,
            "recommended_activity": activity,
            "affiliate_products": day_products,
            "day_parts": calculate_day_parts(hourly_raw, d) if hourly_raw else None,
        })

    overall = round(sum(d["score"] for d in days) / len(days), 1) if days else 0

    all_scores = [d["score"] for d in days]
    if len(set(all_scores)) == 1:
        best = None
        worst = None
        note = "All days have similar conditions"
    else:
        best = max(days, key=lambda d: (d["score"], -d["rain_probability"]))["date"]
        worst = min(days, key=lambda d: (d["score"], -d["rain_probability"]))["date"]
        note = None

    return {
        "city": city.name,
        "country": city.country,
        "data_source": data_source,
        "start_date": start_str,
        "end_date": end_str,
        "overall_score": overall,
        "days": days,
        "best_day": best,
        "worst_day": worst,
        "packing_suggestions": get_product_recommendations(days),
        "note": note,
    }


@require_GET
@free_usage_limit(endpoint_name="trip_planner")
def trip_plan_view(request):
    city_query = request.GET.get("city", "").strip()
    start_str = request.GET.get("start", "").strip()
    end_str = request.GET.get("end", "").strip()

    result = build_trip_plan_response(city_query, start_str, end_str)
    if "error" in result:
        return JsonResponse(result, status=result.pop("status", 400))
    return JsonResponse(result)


@require_GET
def city_search_view(request):
    q = request.GET.get("q", "").strip()
    if len(q) < 2:
        return JsonResponse({"results": []})
    from weather.models import City
    cities = City.objects.filter(name__icontains=q)[:8]
    results = [
        {"name": c.name, "slug": c.slug, "country": c.country}
        for c in cities
    ]
    return JsonResponse({"results": results})


@require_GET
def country_recommend_view(request):
    country = request.GET.get("country", "").strip()
    start = request.GET.get("start", "").strip()
    end = request.GET.get("end", "").strip()

    if not country or not start or not end:
        return JsonResponse({"error": "country, start, end required"}, status=400)

    from weather.models import City
    cities = list(City.objects.filter(country__iexact=country)[:10])
    if not cities:
        return JsonResponse({"error": f"No cities found for country: {country}"}, status=404)

    from .services import fetch_forecast_batch
    batch = fetch_forecast_batch(cities, start, end)

    ranked = []
    if batch:
        for idx, city in enumerate(cities):
            raw = batch[idx] if idx < len(batch) else None
            if raw is None:
                continue
            dates = raw.get("time", [])
            if not dates:
                continue

            temp_max = raw.get("temperature_2m_max", [])
            temp_min = raw.get("temperature_2m_min", [])
            rain_prob = raw.get("precipitation_probability_max", [])
            wind = raw.get("wind_speed_10m_max", [])

            day_scores = []
            for i in range(len(dates)):
                t = temp_max[i] if i < len(temp_max) else 0
                tmin = temp_min[i] if i < len(temp_min) else 0
                rp = rain_prob[i] if i < len(rain_prob) else 0
                w = wind[i] if i < len(wind) else None
                day_scores.append(calculate_day_score(rp, w, t, tmin))

            if not day_scores:
                continue

            avg_score = round(sum(day_scores) / len(day_scores), 1)
            ranked.append({
                "city": city.name,
                "slug": city.slug,
                "country": city.country,
                "average_score": avg_score,
            })
    else:
        for city in cities:
            raw = fetch_forecast(city.latitude, city.longitude, start, end)
            if raw is None:
                continue

            dates = raw.get("time", [])
            temp_max = raw.get("temperature_2m_max", [])
            temp_min = raw.get("temperature_2m_min", [])
            rain_prob = raw.get("precipitation_probability_max", [])
            wind = raw.get("wind_speed_10m_max", [])

            day_scores = []
            for i in range(len(dates)):
                t = temp_max[i] if i < len(temp_max) else 0
                tmin = temp_min[i] if i < len(temp_min) else 0
                rp = rain_prob[i] if i < len(rain_prob) else 0
                w = wind[i] if i < len(wind) else None
                day_scores.append(calculate_day_score(rp, w, t, tmin))

            if not day_scores:
                continue

            avg_score = round(sum(day_scores) / len(day_scores), 1)
            ranked.append({
                "city": city.name,
                "slug": city.slug,
                "country": city.country,
                "average_score": avg_score,
            })

    ranked.sort(key=lambda x: x["average_score"], reverse=True)

    return JsonResponse({
        "country": country,
        "start": start,
        "end": end,
        "cities": ranked[:5],
    })
