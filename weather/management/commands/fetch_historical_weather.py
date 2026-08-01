import time
import statistics
from datetime import date

import requests
from django.core.management.base import BaseCommand
from django.conf import settings

from weather.models import City, HistoricalWeather

HEADERS = {"User-Agent": "WeatherVibe/1.0 (weather research project)"}


class Command(BaseCommand):
    help = "Fetch historical weather for a single city (1940-2025)"

    def add_arguments(self, parser):
        parser.add_argument("city_name", type=str)
        parser.add_argument("latitude", type=float)
        parser.add_argument("longitude", type=float)
        parser.add_argument("--start", type=str, default="1940-01-01")
        parser.add_argument("--end", type=str, default="2025-12-31")

    def handle(self, *args, **options):
        city_name = options["city_name"]
        latitude = options["latitude"]
        longitude = options["longitude"]
        start_date = options["start"]
        end_date = options["end"]

        self.stdout.write(f"Fetching: {city_name} ({latitude}, {longitude})")

        slug = city_name.lower().replace(" ", "-")
        city, created = City.objects.get_or_create(
            slug=slug,
            defaults={
                "name": city_name,
                "country": "",
                "region": "other",
                "latitude": latitude,
                "longitude": longitude,
            },
        )

        url = settings.OPEN_METEO_ARCHIVE_URL
        params = {
            "latitude": latitude,
            "longitude": longitude,
            "start_date": start_date,
            "end_date": end_date,
            "daily": "temperature_2m_max,temperature_2m_min,precipitation_sum,"
                     "rain_sum,sunshine_duration,relative_humidity_2m_mean",
            "timezone": "auto",
        }

        result = None
        for attempt in range(3):
            try:
                resp = requests.get(url, params=params, headers=HEADERS, timeout=60)
            except requests.exceptions.RequestException as e:
                self.stdout.write(self.style.ERROR(f"Network error: {e}"))
                time.sleep(10 * (attempt + 1))
                continue

            if resp.status_code == 200:
                result = resp.json()
                break
            elif resp.status_code == 429:
                wait = 30 * (attempt + 1)
                self.stdout.write(self.style.WARNING(f"Rate limited — waiting {wait}s..."))
                time.sleep(wait)
            else:
                self.stdout.write(self.style.ERROR(
                    f"API error {resp.status_code}: {resp.text[:300]}"
                ))
                return

        if result is None:
            self.stdout.write(self.style.ERROR("Failed after retries."))
            return

        daily = result.get("daily", {})
        dates = daily.get("time", [])
        temp_max = daily.get("temperature_2m_max", [])
        temp_min = daily.get("temperature_2m_min", [])
        precip = daily.get("precipitation_sum", [])
        rain = daily.get("rain_sum", [])
        sun = daily.get("sunshine_duration", [])
        humidity = daily.get("relative_humidity_2m_mean", [])

        year_months = {}
        for i, d in enumerate(dates):
            dt = date.fromisoformat(d)
            key = (dt.year, dt.month)
            if key not in year_months:
                year_months[key] = {"tmax": [], "tmin": [], "rain": [], "precip": [], "sun": [], "hum": []}
            ym = year_months[key]
            if i < len(temp_max) and temp_max[i] is not None: ym["tmax"].append(temp_max[i])
            if i < len(temp_min) and temp_min[i] is not None: ym["tmin"].append(temp_min[i])
            if i < len(precip) and precip[i] is not None: ym["precip"].append(precip[i])
            if i < len(rain) and rain[i] is not None and rain[i] > 0.1: ym["rain"].append(1)
            if i < len(sun) and sun[i] is not None: ym["sun"].append(sun[i] / 3600)
            if i < len(humidity) and humidity[i] is not None: ym["hum"].append(humidity[i])

        saved = 0
        for (year, month), ym in sorted(year_months.items()):
            if not ym["tmax"] and not ym["tmin"]:
                continue
            HistoricalWeather.objects.update_or_create(
                city=city, year=year, month=month,
                defaults={
                    "avg_temp_max": round(statistics.mean(ym["tmax"]), 1) if ym["tmax"] else 0,
                    "avg_temp_min": round(statistics.mean(ym["tmin"]), 1) if ym["tmin"] else 0,
                    "avg_rainfall": round(sum(ym["precip"]), 1) if ym["precip"] else 0,
                    "rainy_days": len(ym["rain"]),
                    "sunshine_hours": round(statistics.mean(ym["sun"]), 1) if ym["sun"] else 0,
                    "avg_humidity": round(statistics.mean(ym["hum"]), 1) if ym["hum"] else 50.0,
                },
            )
            saved += 1

        self.stdout.write(self.style.SUCCESS(f"Saved {saved} monthly records for {city_name}"))
