import time

import requests
from django.core.management.base import BaseCommand
from django.conf import settings

from weather.historical import (
    DAILY_VARS,
    aggregate_daily_to_monthly,
    store_monthly,
    target_year_range,
)
from weather.models import City

HEADERS = {"User-Agent": f"WeatherApex-HistoryFetch/1.0 (contact: {settings.API_CONTACT_EMAIL})"}


class Command(BaseCommand):
    help = "Ek city ka historical weather fetch karo (default: settings.HISTORICAL_YEARS ki range)"

    def add_arguments(self, parser):
        parser.add_argument("city_name", type=str)
        parser.add_argument("latitude", type=float)
        parser.add_argument("longitude", type=float)
        # Default range ab HISTORICAL_YEARS se aati hai, hardcoded
        # 1940-2025 se nahi (woh har saal purana hota jata tha).
        parser.add_argument("--start", type=str, default=None,
                            help="YYYY-MM-DD (default: target range ka start)")
        parser.add_argument("--end", type=str, default=None,
                            help="YYYY-MM-DD (default: aakhri poora saal)")

    def handle(self, *args, **options):
        city_name = options["city_name"]
        latitude = options["latitude"]
        longitude = options["longitude"]
        _start_year, _end_year = target_year_range()
        start_date = options["start"] or f"{_start_year}-01-01"
        end_date = options["end"] or f"{_end_year}-12-31"

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
            "daily": DAILY_VARS,
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

        # Aggregation ab shared module se — teeno paths ka ek hi formula.
        monthly = aggregate_daily_to_monthly(result.get("daily") or {})
        saved = store_monthly(city, monthly)

        self.stdout.write(self.style.SUCCESS(f"Saved {saved} monthly records for {city_name}"))
