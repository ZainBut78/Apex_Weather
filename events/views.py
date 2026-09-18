from datetime import date, timedelta
from django.http import JsonResponse
from django.views.decorators.http import require_GET
from trip_planner.services import (
    KIND_CITY,
    KIND_COUNTRY,
    KIND_REGION,
    country_not_a_city_error,
    fetch_hourly_forecast,
    lookup_place,
)
from .models import EventTypeWeight
from .scoring import (
    DEFAULT_WEIGHTS,
    calculate_risk_score,
    get_risk_level,
    get_recommendation,
    find_best_window,
    get_day_summary,
)
from api_subscription.decorators import free_usage_limit


# ══════════════════════════════════════════════════════════════════════
# weather_code helpers
#
# Masla: fetch_hourly_forecast() Open-Meteo se `weather_code` PEHLE HI
# maangta hai (aur us ka paisa/quota bhi lag chuka hota hai), magar yeh
# view usay response mein bhejta nahi tha. Frontend ke paas koi chaara
# nahi tha, to woh rain probability se code KHUD BANA leta tha:
#
#     rain > 60 -> 61 (barish)      rain > 30 -> 51 (boondaback)
#     warna     -> 0  (saaf aasman)
#
# Is ka nateeja seedha bharosay ka masla tha:
#   * 35% barish ke imkaan wale DHOOP wale din par boondaback ka icon
#   * asli TOOFAN (code 95) jis ka imkaan 20% ho -> SURAJ ka icon
#   * barf (71-77) kabhi dikhti hi nahi thi — barf ka koi code hi
#     generate nahi hota tha
#
# Ab asli code jata hai. "Imkaan" aur "kya ho raha hai" do alag cheezein
# hain — icon doosri cheez dikhata hai.
# ══════════════════════════════════════════════════════════════════════

# Shiddat ki tarteeb — jitna bara number, utna shadeed mausam.
# Open-Meteo apne DAILY code ke liye bhi yehi usool use karta hai:
# "the most severe weather condition on a given day".
_CODE_SEVERITY = {
    0: 0,    # clear sky
    1: 1,    # mainly clear
    2: 2,    # partly cloudy
    3: 3,    # overcast
    45: 4, 48: 5,                    # fog
    51: 6, 53: 7, 55: 8,             # drizzle
    56: 9, 57: 10,                   # freezing drizzle
    61: 11, 80: 12,                  # slight rain / showers
    63: 13, 81: 14,                  # moderate rain / showers
    71: 15, 77: 16, 85: 17,          # slight snow / grains / showers
    73: 18,                          # moderate snow
    66: 19,                          # freezing rain light
    65: 20, 82: 21,                  # heavy rain / violent showers
    67: 22,                          # freezing rain heavy
    75: 23, 86: 24,                  # heavy snow / heavy snow showers
    95: 25, 96: 26, 99: 27,          # thunderstorms
}


def _code_at(raw, idx):
    """Us ghante ka asli WMO code. Na mile to None — 0 (saaf aasman) NAHI.

    0 return karna khatarnaak hai: frontend usay "clear sky" samajh kar
    SURAJ dikha deta hai. None se frontend ko pata chalta hai ke data
    nahi hai aur woh neutral icon dikhata hai.
    """
    codes = raw.get("weather_code") or []
    if idx is None or idx >= len(codes):
        return None
    code = codes[idx]
    return int(code) if code is not None else None


def _is_day_at(raw, idx):
    """Us ghante par din hai ya raat — Open-Meteo ke is_day (1/0) se.

    None tab jab Open-Meteo ne is_day na bheja ho; frontend us soorat
    mein apne purane waqt ke andaze par wapis chala jata hai.
    """
    flags = raw.get("is_day") or []
    if idx is None or idx >= len(flags):
        return None
    val = flags[idx]
    return bool(val) if val is not None else None


def _worst_code(codes):
    """Kai ghanton mein se sab se SHADEED mausam ka code.

    Best-window ka ek hi icon dikhana hai, to us window ka sab se
    shadeed ghanta dikhana chahiye — warna 3 ghante ki window mein ek
    ghanta barish ka ho aur hum suraj dikha dein.
    """
    valid = [int(c) for c in codes if c is not None]
    if not valid:
        return None
    return max(valid, key=lambda c: _CODE_SEVERITY.get(c, 0))


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

    place = lookup_place(city_query, feature="event_risk")
    if place["kind"] != KIND_CITY:
        # "pakistan" jaisa mulk ka naam pehle chup-chaap registan ke ek
        # nuqte (30.0, 70.0) ka mausam bana kar score 0 de deta tha.
        if place["kind"] in (KIND_COUNTRY, KIND_REGION):
            return country_not_a_city_error(place)
        return {"error": "City not found", "status": 404}
    city = place["city"]

    weights = EventTypeWeight.objects.filter(event_type=event_type).first()
    if not weights:
        weights = EventTypeWeight.objects.filter(event_type="sports").first()
    if not weights:
        # Table khaali — neutral weights use karo, crash na karo.
        weights = DEFAULT_WEIGHTS

    today = date.today()
    days_until = (event_date - today).days
    if days_until > 10:
        return {"error": "Event date too far for forecast — max 10 days ahead supported", "status": 400}
    if days_until < 0:
        return {"error": "Event date cannot be in the past", "status": 400}

    range_end = min(event_date + timedelta(days=7), today + timedelta(days=15))
    city_lat, city_lon = city.latitude, city.longitude

    raw = fetch_hourly_forecast(city_lat, city_lon, event_date.isoformat(),
                                range_end.isoformat(), feature="event_risk",
                                country=city.country)
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
        # weather_code Open-Meteo se pehle hi aa raha hai (fetch_hourly_forecast
        # usay maangta hai), magar response mein bheja nahi jata tha. Nateeja:
        # frontend rain% se code KHUD BANA leta tha — 35% chance par drizzle ka
        # icon, aur 20% chance wale asli toofan par SURAJ. Ab asli code jata hai.
        target_code = _code_at(raw, idx)
        target_is_day = _is_day_at(raw, idx)

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
                    "weather_code": _code_at(raw, alt_idx),
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
            "weather_code": target_code,
            "is_day": target_is_day,
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
                "weather_code": _code_at(raw, i),
                "is_day": _is_day_at(raw, i),
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
                    "weather_code": _code_at(raw, i),
                })
            if day_scores:
                best_day = min(day_scores, key=lambda x: x["risk_score"])
                alternates.append({
                    "date": current_date.isoformat(),
                    "risk_score": best_day["risk_score"],
                    "rain_probability": best_day["rain_probability"],
                    "wind_kmh": best_day["wind_kmh"],
                    "temperature_c": best_day["temperature_c"],
                    # Us din ke sab se behtar ghante ka ASLI code — kyunke
                    # score bhi usi ghante ka dikhaya ja raha hai.
                    "weather_code": best_day.get("weather_code"),
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
            "weather_code": _worst_code(
                [h.get("weather_code") for h in full_breakdown
                 if best_window["start_hour"] <= h["hour"] <= best_window["end_hour"]]
            ),
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
