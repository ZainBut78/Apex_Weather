import requests
from django.core.cache import cache

HEADERS = {"User-Agent": "WeatherApex-LandingPage/1.0 (contact: dev@weathervibe.com)"}
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
CACHE_TIMEOUT = 10800


def get_current_and_forecast(city):
    cache_key = f"landing_weather:{city.slug}"
    cached = cache.get(cache_key)
    if cached:
        return cached

    try:
        resp = requests.get(FORECAST_URL, params={
            "latitude": city.latitude,
            "longitude": city.longitude,
            "current": "temperature_2m,relative_humidity_2m,"
                       "wind_speed_10m,weather_code,precipitation",
            "daily": "temperature_2m_max,temperature_2m_min,"
                     "precipitation_probability_max,weather_code",
            "hourly": "temperature_2m,precipitation_probability,"
                      "wind_speed_10m,weather_code",
            "forecast_days": 15,
            "timezone": "auto",
        }, headers=HEADERS, timeout=15)

        if resp.status_code != 200:
            return None

        data = resp.json()

        today_str = data.get("daily", {}).get("time", [None])[0]
        hourly_all = data.get("hourly", {})
        hourly_today = {}
        if today_str:
            times = hourly_all.get("time", [])
            start = None
            end = None
            for i, t in enumerate(times):
                if t.startswith(today_str) and start is None:
                    start = i
                if t.startswith(today_str):
                    end = i + 1
            if start is not None:
                hourly_today = {k: v[start:end] for k, v in hourly_all.items()}

        result = {
            "current": data.get("current", {}),
            "forecast_7day": data.get("daily", {}),
            "hourly_today": hourly_today,
        }

        cache.set(cache_key, result, timeout=CACHE_TIMEOUT)
        return result
    except requests.exceptions.RequestException:
        return None
