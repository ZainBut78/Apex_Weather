from datetime import date, timedelta
from django.http import JsonResponse
from django.views.decorators.http import require_GET
from trip_planner.services import get_city, fetch_hourly_forecast
from .models import EventTypeWeight
from .scoring import (
    calculate_risk_score,
    get_risk_level,
    get_recommendation,
    find_best_window,
    get_day_summary,
)
from api_subscription.decorators import free_usage_limit


def get_hour_index(hourly_times, target_date, target_hour):
    target_str = f"{target_date}T{target_hour:02d}:00"
    try:
        return hourly_times.index(target_str)
    except ValueError:
        return None


def build_event_risk_response(city_query, event_date_str, event_type, time_str):
    """Pure function — HTTP se independent, dict return karta hai."""
    if not city_query or not event_date_str:
        return {"error": "city and date parameters required", "status": 400}

    try:
        event_date = date.fromisoformat(event_date_str)
    except ValueError:
        return {"error": "Invalid date format. Use YYYY-MM-DD", "status": 400}

    event_hour = None
    if time_str:
        try:
            event_hour = int(time_str)
            if not (0 <= event_hour <= 23):
                raise ValueError
        except ValueError:
            return {"error": "time must be 0-23 (24-hour format)", "status": 400}

    city = get_city(city_query)
    if city is None:
        return {"error": "City not found", "status": 404}

    weights = EventTypeWeight.objects.filter(event_type=event_type).first()
    if not weights:
        weights = EventTypeWeight.objects.filter(event_type="sports").first()

    today = date.today()
    days_until = (event_date - today).days
    if days_until > 10:
        return {"error": "Event date too far for forecast — max 10 days ahead supported", "status": 400}
    if days_until < 0:
        return {"error": "Event date cannot be in the past", "status": 400}

    range_end = min(event_date + timedelta(days=7), today + timedelta(days=15))
    city_lat, city_lon = city.latitude, city.longitude

    raw = fetch_hourly_forecast(city_lat, city_lon, event_date.isoformat(), range_end.isoformat())
    if raw is None:
        return {"error": "Could not fetch weather data", "status": 503}

    hourly_times = raw.get("time", [])

    # CASE A: User ne specific time diya hai
    if event_hour is not None:
        idx = get_hour_index(hourly_times, event_date.isoformat(), event_hour)
        if idx is None:
            return {"error": "Requested time not found in forecast data", "status": 503}

        target_temp = raw["temperature_2m"][idx]
        target_rain = raw["precipitation_probability"][idx]
        target_wind = raw["wind_speed_10m"][idx]
        target_humidity = raw["relative_humidity_2m"][idx]

        risk_score = calculate_risk_score(target_rain, target_wind, target_temp, target_humidity, weights)
        risk_level = get_risk_level(risk_score)
        recommendation = get_recommendation(risk_level, target_rain)

        alternates = []
        current_date = event_date + timedelta(days=1)
        while current_date <= range_end:
            alt_idx = get_hour_index(hourly_times, current_date.isoformat(), event_hour)
            if alt_idx is not None:
                alt_score = calculate_risk_score(
                    raw["precipitation_probability"][alt_idx],
                    raw["wind_speed_10m"][alt_idx],
                    raw["temperature_2m"][alt_idx],
                    raw["relative_humidity_2m"][alt_idx],
                    weights
                )
                alternates.append({
                    "date": current_date.isoformat(),
                    "risk_score": alt_score,
                    "rain_probability": raw["precipitation_probability"][alt_idx],
                    "wind_kmh": raw["wind_speed_10m"][alt_idx],
                    "temperature_c": raw["temperature_2m"][alt_idx],
                })
            current_date += timedelta(days=1)

        alternates = sorted(alternates, key=lambda x: x["risk_score"])[:5]

        return {
            "city": city.name,
            "country": city.country,
            "event_type": event_type,
            "event_date": event_date_str,
            "event_time": f"{event_hour:02d}:00",
            "risk_score": risk_score,
            "risk_level": risk_level,
            "rain_probability": target_rain,
            "wind_kmh": target_wind,
            "temperature_c": target_temp,
            "humidity_pct": target_humidity,
            "recommendation": recommendation,
            "alternate_dates": alternates,
        }

    # CASE B: User ne time NAHI diya — best time of day suggest karo
    else:
        hourly_times = raw.get("time", [])
        temps = raw.get("temperature_2m", [])
        rains = raw.get("precipitation_probability", [])
        winds = raw.get("wind_speed_10m", [])
        humidity = raw.get("relative_humidity_2m", [])

        full_breakdown = []
        for i, t in enumerate(hourly_times):
            if not t.startswith(event_date.isoformat()):
                continue
            hour = int(t.split("T")[1].split(":")[0])
            if hour < 6 or hour > 22:
                continue
            full_breakdown.append({
                "hour": hour,
                "risk_score": calculate_risk_score(rains[i], winds[i], temps[i], humidity[i], weights),
                "rain_probability": rains[i],
                "wind_kmh": winds[i],
                "temperature_c": temps[i],
                "humidity_pct": humidity[i],
            })

        best_window = find_best_window(raw, event_date.isoformat(), weights)
        if not best_window:
            return {"error": "No forecast data available for this date", "status": 503}

        start_time = f"{best_window['start_hour']:02d}:00"
        end_time = f"{best_window['end_hour']:02d}:00"
        risk_score = best_window["avg_risk_score"]
        risk_level = get_risk_level(risk_score)

        humidity_by_hour = {h["hour"]: h["humidity_pct"] for h in full_breakdown}
        window_details = best_window["hours_detail"]
        window_rains = [h["rain"] for h in window_details]
        window_temps = [h["temp"] for h in window_details]
        window_winds = [h["wind"] for h in window_details]
        window_humidity = [
            humidity_by_hour.get(h["hour"]) for h in window_details
        ]
        window_humidity = [h for h in window_humidity if h is not None]

        day_context = get_day_summary([
            {
                "hour": h["hour"],
                "score": h["risk_score"],
                "rain": h["rain_probability"],
                "temp": h["temperature_c"],
                "wind": h["wind_kmh"],
            }
            for h in full_breakdown
        ])

        recommendation = get_recommendation(risk_level, max(window_rains), day_context)

        alternates = []
        current_date = event_date + timedelta(days=1)
        while current_date <= range_end:
            day_scores = []
            for i, t in enumerate(hourly_times):
                if not t.startswith(current_date.isoformat()):
                    continue
                hour = int(t.split("T")[1].split(":")[0])
                if hour < 6 or hour > 22:
                    continue
                day_scores.append({
                    "risk_score": calculate_risk_score(rains[i], winds[i], temps[i], humidity[i], weights),
                    "rain_probability": rains[i],
                    "wind_kmh": winds[i],
                    "temperature_c": temps[i],
                })
            if day_scores:
                best_day = min(day_scores, key=lambda x: x["risk_score"])
                alternates.append({
                    "date": current_date.isoformat(),
                    "risk_score": best_day["risk_score"],
                    "rain_probability": best_day["rain_probability"],
                    "wind_kmh": best_day["wind_kmh"],
                    "temperature_c": best_day["temperature_c"],
                })
            current_date += timedelta(days=1)

        alternates = sorted(alternates, key=lambda x: x["risk_score"])[:5]

        return {
            "city": city.name,
            "country": city.country,
            "event_type": event_type,
            "event_date": event_date_str,
            "note": "No specific time given — showing best time window of day and top recommendations",
            "best_window": {
                "start_time": start_time,
                "end_time": end_time,
                "duration_hours": best_window["end_hour"] - best_window["start_hour"] + 1,
                "risk_score": risk_score,
                "risk_level": risk_level,
            },
            "best_time": start_time,
            "risk_score": risk_score,
            "risk_level": risk_level,
            "rain_probability": max(window_rains) if window_rains else 0,
            "wind_kmh": max(window_winds) if window_winds else 0,
            "temperature_c": round(sum(window_temps) / len(window_temps), 1) if window_temps else 0,
            "humidity_pct": round(sum(window_humidity) / len(window_humidity)) if window_humidity else None,
            "day_context": day_context,
            "recommendation": recommendation,
            "hourly_breakdown": full_breakdown,
            "alternate_dates": alternates,
        }


@require_GET
@free_usage_limit(endpoint_name="event_risk")
def event_risk_view(request):
    city_query = request.GET.get("city", "").strip()
    event_date_str = request.GET.get("date", "").strip()
    event_type = request.GET.get("type", "general").strip().lower()
    time_str = request.GET.get("time", "").strip()

    result = build_event_risk_response(city_query, event_date_str, event_type, time_str)
    if "error" in result:
        return JsonResponse(result, status=result.pop("status", 400))
    return JsonResponse(result)
