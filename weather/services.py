import logging
import os
from concurrent.futures import ThreadPoolExecutor

import requests
from django.conf import settings
from django.core.cache import cache
from .cache_policy import forecast_ttl
from .models import ExternalAPICallLog, ServiceRequestLog

logger = logging.getLogger(__name__)

PEXELS_API_KEY = os.getenv("PEXELS_API_KEY", "")
PEXELS_URL = "https://api.pexels.com/v1/search"

HEADERS = {"User-Agent": f"WeatherApex-LandingPage/1.0 (contact: {settings.API_CONTACT_EMAIL})"}
# Pexels ke sath bhi User-Agent bhejo — yeh ek hi call site tha jahan
# custom UA missing tha (bot-detection / rate-limit ke liye zaroori).
PEXELS_HEADERS = {
    "Authorization": PEXELS_API_KEY,
    "User-Agent": f"WeatherApex-CityImages/1.0 (contact: {settings.API_CONTACT_EMAIL})",
}
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
# Fallback — asal TTL cache_policy se (model run ke hisaab se).
# NOTE: pehle yeh 10800 HARDCODE tha jabke trip_planner env var padhta
# tha, to FORECAST_CACHE_SECONDS badalne se sirf aadhi app badalti thi.
CACHE_TIMEOUT = int(os.getenv("FORECAST_CACHE_SECONDS", 10800))


def log_external_call(api_type, city_query="", success=True, status_code=None, feature="other"):
    try:
        ExternalAPICallLog.objects.create(
            api_type=api_type,
            city_query=city_query or "",
            success=success,
            status_code=status_code,
            feature=feature,
        )
    except Exception:
        # Monitoring log likhne mein fail hona request ko todna nahi
        # chahiye — magar chupchap bhi nahi guzarna chahiye.
        logger.warning("ExternalAPICallLog likhne mein fail: api_type=%s city=%s",
                       api_type, city_query, exc_info=True)


def log_service_request(feature, data_source, city_query=""):
    try:
        ServiceRequestLog.objects.create(
            feature=feature,
            data_source=data_source,
            city_query=city_query or "",
        )
    except Exception:
        logger.warning("ServiceRequestLog likhne mein fail: feature=%s source=%s",
                       feature, data_source, exc_info=True)


def get_or_fetch_city_image(city):
    """
    Pehle DB check — agar image_url already hai, wahi return karo.
    Nahi hai to Pexels se fetch karke DB mein save karo.
    """
    if city.image_url:
        return city.image_url

    if not PEXELS_API_KEY:
        return None

    try:
        response = requests.get(
            PEXELS_URL,
            headers=PEXELS_HEADERS,
            params={"query": f"{city.name} city skyline", "per_page": 1},
            timeout=10,
        )
        log_external_call("images", city.name, success=(response.status_code == 200), status_code=response.status_code, feature="other")
        if response.status_code == 200:
            data = response.json()
            photos = data.get("photos") or []
            if photos:
                # Pexels ka shape badal jaye to KeyError/TypeError se
                # poora request 500 nahi hona chahiye — image optional hai.
                image_url = (photos[0].get("src") or {}).get("landscape")
                if image_url:
                    city.image_url = image_url
                    city.save(update_fields=["image_url"])
                    return image_url
    except requests.exceptions.RequestException:
        log_external_call("images", city.name, success=False, status_code=None, feature="other")
    except (ValueError, KeyError, TypeError, AttributeError):
        logger.warning("Pexels response parse nahi hua: city=%s", city.name, exc_info=True)
        log_external_call("images", city.name, success=False, status_code=None, feature="other")

    return None


def get_current_and_forecast(city):
    cache_key = f"landing_weather:{city.slug}"
    cached = cache.get(cache_key)
    if cached:
        log_service_request("weather", "cache", city.name)
        return cached

    try:
        resp = requests.get(FORECAST_URL, params={
            "latitude": city.latitude,
            "longitude": city.longitude,
            # is_day: Open-Meteo khud us jagah ke sunrise/sunset se
            # batata hai ke abhi din hai (1) ya raat (0). Is se pehle
            # frontend 19:00-06:00 ka fixed andaza lagata tha, jo Oslo ki
            # garmiyon (raat 11 baje bhi roshni) aur sardiyon (shaam 4
            # baje andhera) mein ghalat hota tha.
            "current": "temperature_2m,relative_humidity_2m,"
                       "wind_speed_10m,weather_code,precipitation,is_day",
            "daily": "temperature_2m_max,temperature_2m_min,"
                     "precipitation_probability_max,weather_code",
            "hourly": "temperature_2m,precipitation_probability,"
                      "wind_speed_10m,weather_code,is_day",
            "forecast_days": 15,
            "timezone": "auto",
        }, headers=HEADERS, timeout=15)

        log_external_call("forecast", city.name, success=(resp.status_code == 200), status_code=resp.status_code, feature="weather")

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
            "hourly_forecast": {k: v[:72] for k, v in hourly_all.items()},
        }

        cache.set(cache_key, result, timeout=forecast_ttl(city=city))
        log_service_request("weather", "external", city.name)
        return result
    except requests.exceptions.RequestException:
        log_external_call("forecast", city.name, success=False, status_code=None, feature="weather")
        return None


def fetch_city_images(cities):
    """
    Multiple cities ke liye Pexels images parallel fetch karo
    (country search jaise batch scenarios ke liye).
    """
    if not cities:
        return {}
    with ThreadPoolExecutor(max_workers=6) as pool:
        return {
            city.id: image_url
            for city, image_url in zip(cities, pool.map(get_or_fetch_city_image, cities))
        }
