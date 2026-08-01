import logging
import os
import requests
from datetime import date, timedelta
from django.db.models import Avg
from django.core.cache import cache
from django.utils.text import slugify
from weather.models import City, HistoricalWeather

logger = logging.getLogger(__name__)

CACHE_TIMEOUT = int(os.getenv("FORECAST_CACHE_SECONDS", 10800))

HEADERS = {"User-Agent": "WeatherApex-TripPlanner/1.0 (contact: dev@weathervibe.com)"}

FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"


def get_city(city_query):
    city_query = city_query.strip()

    city = City.objects.filter(slug__iexact=city_query).first()
    if city:
        return city

    city = City.objects.filter(name__iexact=city_query).first()
    if city:
        return city

    city = City.objects.filter(name__icontains=city_query).first()
    if city:
        return city

    try:
        resp = requests.get(GEOCODING_URL, params={"name": city_query, "count": 1},
                            headers=HEADERS, timeout=10)
        results = resp.json().get("results", [])
        if results:
            r = results[0]
            new_city, _ = City.objects.get_or_create(
                slug=slugify(r.get("name", city_query)),
                defaults={
                    "name": r.get("name", city_query),
                    "country": r.get("country", ""),
                    "latitude": r.get("latitude"),
                    "longitude": r.get("longitude"),
                }
            )
            return new_city
    except requests.exceptions.RequestException as e:
        logger.error(f"Geocoding API failed: {e}")

    return None


def fetch_forecast(latitude, longitude, start_date, end_date):
    cache_key = f"forecast:{latitude}:{longitude}:{start_date}:{end_date}"
    cached = cache.get(cache_key)
    if cached:
        return cached

    try:
        resp = requests.get(FORECAST_URL, params={
            "latitude": latitude,
            "longitude": longitude,
            "start_date": start_date,
            "end_date": end_date,
            "daily": "temperature_2m_max,temperature_2m_min,precipitation_probability_max,"
                     "wind_speed_10m_max,weather_code,relative_humidity_2m_mean",
            "timezone": "auto",
        }, headers=HEADERS, timeout=30)

        if resp.status_code == 200:
            result = resp.json().get("daily", {})
            cache.set(cache_key, result, timeout=CACHE_TIMEOUT)
            return result
    except requests.exceptions.RequestException as e:
        logger.error(f"Forecast API failed: {e}")

    return None


def fetch_forecast_batch(city_list, start_date, end_date):
    if not city_list:
        return []

    cache_key = f"forecast_batch:{','.join(str(c.id) for c in city_list)}:{start_date}:{end_date}"
    cached = cache.get(cache_key)
    if cached:
        return cached

    lats = ",".join(str(c.latitude) for c in city_list)
    lngs = ",".join(str(c.longitude) for c in city_list)

    try:
        resp = requests.get(FORECAST_URL, params={
            "latitude": lats,
            "longitude": lngs,
            "start_date": start_date,
            "end_date": end_date,
            "daily": "temperature_2m_max,temperature_2m_min,precipitation_probability_max,"
                     "wind_speed_10m_max,weather_code",
            "timezone": "auto",
        }, headers=HEADERS, timeout=60)

        if resp.status_code == 200:
            data = resp.json()
            if isinstance(data, list):
                result = [item.get("daily", {}) for item in data]
            else:
                result = [data.get("daily", {})]
            cache.set(cache_key, result, timeout=CACHE_TIMEOUT)
            return result
    except requests.exceptions.RequestException as e:
        logger.error(f"Batch forecast API failed: {e}")

    return None


def fetch_hourly_forecast(latitude, longitude, start_date, end_date):
    cache_key = f"hourly_forecast:{latitude}:{longitude}:{start_date}:{end_date}"
    cached = cache.get(cache_key)
    if cached:
        return cached

    try:
        resp = requests.get(FORECAST_URL, params={
            "latitude": latitude,
            "longitude": longitude,
            "start_date": start_date,
            "end_date": end_date,
            "hourly": "temperature_2m,precipitation_probability,"
                      "wind_speed_10m,relative_humidity_2m,weather_code",
            "timezone": "auto",
        }, headers=HEADERS, timeout=30)

        if resp.status_code == 200:
            result = resp.json().get("hourly", {})
            cache.set(cache_key, result, timeout=CACHE_TIMEOUT)
            return result
    except requests.exceptions.RequestException as e:
        logger.error(f"Hourly forecast API failed: {e}")

    return None


def get_historical_estimate(city, start_date, end_date):
    if isinstance(start_date, str):
        start_date = date.fromisoformat(start_date)
    if isinstance(end_date, str):
        end_date = date.fromisoformat(end_date)

    unique_months = set()
    current = start_date
    while current <= end_date:
        unique_months.add(current.month)
        current += timedelta(days=1)

    month_averages = {}
    for month in unique_months:
        month_averages[month] = HistoricalWeather.objects.filter(
            city=city, month=month
        ).aggregate(
            avg_max=Avg("avg_temp_max"),
            avg_min=Avg("avg_temp_min"),
            avg_rain=Avg("avg_rainfall"),
            avg_rainy=Avg("rainy_days"),
        )

    daily = {"time": [], "temperature_2m_max": [], "temperature_2m_min": [],
             "precipitation_probability_max": [], "wind_speed_10m_max": [], "weather_code": []}

    current = start_date
    while current <= end_date:
        daily["time"].append(current.isoformat())
        avg_data = month_averages[current.month]

        daily["temperature_2m_max"].append(round(avg_data["avg_max"], 1) if avg_data["avg_max"] else 0)
        daily["temperature_2m_min"].append(round(avg_data["avg_min"], 1) if avg_data["avg_min"] else 0)

        rainy = avg_data["avg_rainy"] if avg_data["avg_rainy"] else 0
        rain_prob = min(round((rainy / 30) * 100), 100)
        daily["precipitation_probability_max"].append(rain_prob)

        daily["wind_speed_10m_max"].append(None)
        daily["weather_code"].append(0)

        current += timedelta(days=1)

    return daily
