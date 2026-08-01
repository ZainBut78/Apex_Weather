import time
import statistics
from datetime import date

import requests
from django.core.management.base import BaseCommand
from django.db.models import Count
from django.conf import settings

from weather.models import City, HistoricalWeather

HEADERS = {"User-Agent": "WeatherVibe/1.0 (weather research project)"}

CITIES = [
    # EUROPE - United Kingdom
    {"name": "London", "country": "United Kingdom", "region": "europe", "lat": 51.5074, "lon": -0.1278},
    {"name": "Manchester", "country": "United Kingdom", "region": "europe", "lat": 53.4808, "lon": -2.2426},
    {"name": "Birmingham", "country": "United Kingdom", "region": "europe", "lat": 52.4862, "lon": -1.8904},
    {"name": "Edinburgh", "country": "United Kingdom", "region": "europe", "lat": 55.9533, "lon": -3.1883},
    {"name": "Glasgow", "country": "United Kingdom", "region": "europe", "lat": 55.8642, "lon": -4.2518},

    # EUROPE - France
    {"name": "Paris", "country": "France", "region": "europe", "lat": 48.8566, "lon": 2.3522},
    {"name": "Lyon", "country": "France", "region": "europe", "lat": 45.7640, "lon": 4.8357},
    {"name": "Marseille", "country": "France", "region": "europe", "lat": 43.2965, "lon": 5.3698},
    {"name": "Toulouse", "country": "France", "region": "europe", "lat": 43.6047, "lon": 1.4442},
    {"name": "Nice", "country": "France", "region": "europe", "lat": 43.7102, "lon": 7.2620},

    # EUROPE - Germany
    {"name": "Berlin", "country": "Germany", "region": "europe", "lat": 52.5200, "lon": 13.4050},
    {"name": "Munich", "country": "Germany", "region": "europe", "lat": 48.1351, "lon": 11.5820},
    {"name": "Hamburg", "country": "Germany", "region": "europe", "lat": 53.5511, "lon": 9.9937},
    {"name": "Frankfurt", "country": "Germany", "region": "europe", "lat": 50.1109, "lon": 8.6821},
    {"name": "Cologne", "country": "Germany", "region": "europe", "lat": 50.9375, "lon": 6.9603},

    # EUROPE - Spain
    {"name": "Madrid", "country": "Spain", "region": "europe", "lat": 40.4168, "lon": -3.7038},
    {"name": "Barcelona", "country": "Spain", "region": "europe", "lat": 41.3874, "lon": 2.1686},
    {"name": "Valencia", "country": "Spain", "region": "europe", "lat": 39.4699, "lon": -0.3763},
    {"name": "Seville", "country": "Spain", "region": "europe", "lat": 37.3891, "lon": -5.9845},
    {"name": "Bilbao", "country": "Spain", "region": "europe", "lat": 43.2630, "lon": -2.9350},

    # EUROPE - Italy
    {"name": "Rome", "country": "Italy", "region": "europe", "lat": 41.9028, "lon": 12.4964},
    {"name": "Milan", "country": "Italy", "region": "europe", "lat": 45.4642, "lon": 9.1900},
    {"name": "Naples", "country": "Italy", "region": "europe", "lat": 40.8518, "lon": 14.2681},
    {"name": "Turin", "country": "Italy", "region": "europe", "lat": 45.0703, "lon": 7.6869},
    {"name": "Florence", "country": "Italy", "region": "europe", "lat": 43.7696, "lon": 11.2558},

    # EUROPE - Netherlands
    {"name": "Amsterdam", "country": "Netherlands", "region": "europe", "lat": 52.3676, "lon": 4.9041},
    {"name": "Rotterdam", "country": "Netherlands", "region": "europe", "lat": 51.9244, "lon": 4.4777},
    {"name": "The Hague", "country": "Netherlands", "region": "europe", "lat": 52.0705, "lon": 4.3007},

    # EUROPE - Austria
    {"name": "Vienna", "country": "Austria", "region": "europe", "lat": 48.2082, "lon": 16.3738},
    {"name": "Salzburg", "country": "Austria", "region": "europe", "lat": 47.8095, "lon": 13.0550},

    # EUROPE - Belgium
    {"name": "Brussels", "country": "Belgium", "region": "europe", "lat": 50.8503, "lon": 4.3517},
    {"name": "Antwerp", "country": "Belgium", "region": "europe", "lat": 51.2194, "lon": 4.4025},

    # EUROPE - Ireland
    {"name": "Dublin", "country": "Ireland", "region": "europe", "lat": 53.3498, "lon": -6.2603},
    {"name": "Cork", "country": "Ireland", "region": "europe", "lat": 51.8985, "lon": -8.4756},

    # EUROPE - Portugal
    {"name": "Lisbon", "country": "Portugal", "region": "europe", "lat": 38.7223, "lon": -9.1393},
    {"name": "Porto", "country": "Portugal", "region": "europe", "lat": 41.1579, "lon": -8.6291},

    # EUROPE - Sweden
    {"name": "Stockholm", "country": "Sweden", "region": "europe", "lat": 59.3293, "lon": 18.0686},
    {"name": "Gothenburg", "country": "Sweden", "region": "europe", "lat": 57.7089, "lon": 11.9746},

    # EUROPE - Norway
    {"name": "Oslo", "country": "Norway", "region": "europe", "lat": 59.9139, "lon": 10.7522},
    {"name": "Bergen", "country": "Norway", "region": "europe", "lat": 60.3913, "lon": 5.3221},
    {"name": "Trondheim", "country": "Norway", "region": "europe", "lat": 63.4305, "lon": 10.3951},

    # EUROPE - Denmark
    {"name": "Copenhagen", "country": "Denmark", "region": "europe", "lat": 55.6761, "lon": 12.5683},
    {"name": "Aarhus", "country": "Denmark", "region": "europe", "lat": 56.1629, "lon": 10.2039},

    # EUROPE - Finland
    {"name": "Helsinki", "country": "Finland", "region": "europe", "lat": 60.1699, "lon": 24.9384},
    {"name": "Tampere", "country": "Finland", "region": "europe", "lat": 61.4978, "lon": 23.7610},

    # EUROPE - Poland
    {"name": "Warsaw", "country": "Poland", "region": "europe", "lat": 52.2297, "lon": 21.0122},
    {"name": "Krakow", "country": "Poland", "region": "europe", "lat": 50.0647, "lon": 19.9450},
    {"name": "Gdansk", "country": "Poland", "region": "europe", "lat": 54.3520, "lon": 18.6466},

    # EUROPE - Czech Republic
    {"name": "Prague", "country": "Czech Republic", "region": "europe", "lat": 50.0755, "lon": 14.4378},
    {"name": "Brno", "country": "Czech Republic", "region": "europe", "lat": 49.1951, "lon": 16.6068},

    # EUROPE - Hungary
    {"name": "Budapest", "country": "Hungary", "region": "europe", "lat": 47.4979, "lon": 19.0402},

    # EUROPE - Greece
    {"name": "Athens", "country": "Greece", "region": "europe", "lat": 37.9838, "lon": 23.7275},
    {"name": "Thessaloniki", "country": "Greece", "region": "europe", "lat": 40.6401, "lon": 22.9444},

    # EUROPE - Turkey
    {"name": "Istanbul", "country": "Turkey", "region": "other", "lat": 41.0082, "lon": 28.9784},
    {"name": "Ankara", "country": "Turkey", "region": "other", "lat": 39.9334, "lon": 32.8597},
    {"name": "Antalya", "country": "Turkey", "region": "other", "lat": 36.8969, "lon": 30.7133},

    # EUROPE - Switzerland
    {"name": "Zurich", "country": "Switzerland", "region": "europe", "lat": 47.3769, "lon": 8.5417},
    {"name": "Geneva", "country": "Switzerland", "region": "europe", "lat": 46.2044, "lon": 6.1432},

    # RUSSIA
    {"name": "Moscow", "country": "Russia", "region": "other", "lat": 55.7558, "lon": 37.6173},
    {"name": "Saint Petersburg", "country": "Russia", "region": "other", "lat": 59.9343, "lon": 30.3351},
    {"name": "Kazan", "country": "Russia", "region": "other", "lat": 55.8304, "lon": 49.0661},
    {"name": "Sochi", "country": "Russia", "region": "other", "lat": 43.6028, "lon": 39.7342},

    # AZERBAIJAN
    {"name": "Baku", "country": "Azerbaijan", "region": "other", "lat": 40.4093, "lon": 49.8671},

    # USA
    {"name": "New York", "country": "USA", "region": "usa", "lat": 40.7128, "lon": -74.0060},
    {"name": "Los Angeles", "country": "USA", "region": "usa", "lat": 34.0522, "lon": -118.2437},
    {"name": "Chicago", "country": "USA", "region": "usa", "lat": 41.8781, "lon": -87.6298},
    {"name": "Houston", "country": "USA", "region": "usa", "lat": 29.7604, "lon": -95.3698},
    {"name": "Phoenix", "country": "USA", "region": "usa", "lat": 33.4484, "lon": -112.0740},
    {"name": "Philadelphia", "country": "USA", "region": "usa", "lat": 39.9526, "lon": -75.1652},
    {"name": "San Antonio", "country": "USA", "region": "usa", "lat": 29.4241, "lon": -98.4936},
    {"name": "San Diego", "country": "USA", "region": "usa", "lat": 32.7157, "lon": -117.1611},
    {"name": "Dallas", "country": "USA", "region": "usa", "lat": 32.7767, "lon": -96.7970},
    {"name": "Austin", "country": "USA", "region": "usa", "lat": 30.2672, "lon": -97.7431},
    {"name": "San Francisco", "country": "USA", "region": "usa", "lat": 37.7749, "lon": -122.4194},
    {"name": "Seattle", "country": "USA", "region": "usa", "lat": 47.6062, "lon": -122.3321},
    {"name": "Denver", "country": "USA", "region": "usa", "lat": 39.7392, "lon": -104.9903},
    {"name": "Washington DC", "country": "USA", "region": "usa", "lat": 38.9072, "lon": -77.0369},
    {"name": "Boston", "country": "USA", "region": "usa", "lat": 42.3601, "lon": -71.0589},
    {"name": "Nashville", "country": "USA", "region": "usa", "lat": 36.1627, "lon": -86.7816},
    {"name": "Portland", "country": "USA", "region": "usa", "lat": 45.5152, "lon": -122.6784},
    {"name": "Las Vegas", "country": "USA", "region": "usa", "lat": 36.1699, "lon": -115.1398},
    {"name": "Miami", "country": "USA", "region": "usa", "lat": 25.7617, "lon": -80.1918},
    {"name": "Atlanta", "country": "USA", "region": "usa", "lat": 33.7490, "lon": -84.3880},
    {"name": "Detroit", "country": "USA", "region": "usa", "lat": 42.3314, "lon": -83.0458},
    {"name": "Minneapolis", "country": "USA", "region": "usa", "lat": 44.9778, "lon": -93.2650},
    {"name": "Salt Lake City", "country": "USA", "region": "usa", "lat": 40.7608, "lon": -111.8910},
    {"name": "Orlando", "country": "USA", "region": "usa", "lat": 28.5383, "lon": -81.3792},
    {"name": "New Orleans", "country": "USA", "region": "usa", "lat": 29.9511, "lon": -90.0715},
    {"name": "Pittsburgh", "country": "USA", "region": "usa", "lat": 40.4406, "lon": -79.9959},
    {"name": "Honolulu", "country": "USA", "region": "usa", "lat": 21.3069, "lon": -157.8583},

    # CANADA
    {"name": "Toronto", "country": "Canada", "region": "other", "lat": 43.6532, "lon": -79.3832},
    {"name": "Vancouver", "country": "Canada", "region": "other", "lat": 49.2827, "lon": -123.1207},
    {"name": "Montreal", "country": "Canada", "region": "other", "lat": 45.5017, "lon": -73.5673},
    {"name": "Calgary", "country": "Canada", "region": "other", "lat": 51.0447, "lon": -114.0719},

    # PAKISTAN
    {"name": "Lahore", "country": "Pakistan", "region": "other", "lat": 31.5204, "lon": 74.3587},
    {"name": "Karachi", "country": "Pakistan", "region": "other", "lat": 24.8607, "lon": 67.0011},
    {"name": "Islamabad", "country": "Pakistan", "region": "other", "lat": 33.6844, "lon": 73.0479},
    {"name": "Peshawar", "country": "Pakistan", "region": "other", "lat": 34.0151, "lon": 71.5249},
    {"name": "Quetta", "country": "Pakistan", "region": "other", "lat": 30.1798, "lon": 66.9750},

    # INDIA
    {"name": "Mumbai", "country": "India", "region": "other", "lat": 19.0760, "lon": 72.8777},
    {"name": "Delhi", "country": "India", "region": "other", "lat": 28.7041, "lon": 77.1025},
    {"name": "Bangalore", "country": "India", "region": "other", "lat": 12.9716, "lon": 77.5946},
    {"name": "Chennai", "country": "India", "region": "other", "lat": 13.0827, "lon": 80.2707},
    {"name": "Kolkata", "country": "India", "region": "other", "lat": 22.5726, "lon": 88.3639},

    # BANGLADESH
    {"name": "Dhaka", "country": "Bangladesh", "region": "other", "lat": 23.8103, "lon": 90.4125},
    {"name": "Chittagong", "country": "Bangladesh", "region": "other", "lat": 22.3569, "lon": 91.7832},

    # NEPAL
    {"name": "Kathmandu", "country": "Nepal", "region": "other", "lat": 27.7172, "lon": 85.3240},
    {"name": "Pokhara", "country": "Nepal", "region": "other", "lat": 28.2096, "lon": 83.9856},

    # SRI LANKA
    {"name": "Colombo", "country": "Sri Lanka", "region": "other", "lat": 6.9271, "lon": 79.8612},

    # PHILIPPINES
    {"name": "Manila", "country": "Philippines", "region": "other", "lat": 14.5995, "lon": 120.9842},
    {"name": "Cebu", "country": "Philippines", "region": "other", "lat": 10.3157, "lon": 123.8854},

    # MALAYSIA
    {"name": "Kuala Lumpur", "country": "Malaysia", "region": "other", "lat": 3.1390, "lon": 101.6869},

    # VIETNAM
    {"name": "Hanoi", "country": "Vietnam", "region": "other", "lat": 21.0278, "lon": 105.8342},
    {"name": "Ho Chi Minh City", "country": "Vietnam", "region": "other", "lat": 10.8231, "lon": 106.6297},

    # MYANMAR
    {"name": "Yangon", "country": "Myanmar", "region": "other", "lat": 16.8661, "lon": 96.1951},

    # IRAN
    {"name": "Tehran", "country": "Iran", "region": "other", "lat": 35.6892, "lon": 51.3890},
    {"name": "Isfahan", "country": "Iran", "region": "other", "lat": 32.6546, "lon": 51.6680},
    {"name": "Shiraz", "country": "Iran", "region": "other", "lat": 29.5918, "lon": 52.5836},

    # CHINA
    {"name": "Beijing", "country": "China", "region": "other", "lat": 39.9042, "lon": 116.4074},
    {"name": "Shanghai", "country": "China", "region": "other", "lat": 31.2304, "lon": 121.4737},
    {"name": "Guangzhou", "country": "China", "region": "other", "lat": 23.1291, "lon": 113.2644},
    {"name": "Chengdu", "country": "China", "region": "other", "lat": 30.5728, "lon": 104.0668},
    {"name": "Shenzhen", "country": "China", "region": "other", "lat": 22.5431, "lon": 114.0579},
    {"name": "Hong Kong", "country": "China", "region": "other", "lat": 22.3193, "lon": 114.1694},

    # JAPAN
    {"name": "Tokyo", "country": "Japan", "region": "other", "lat": 35.6762, "lon": 139.6503},
    {"name": "Osaka", "country": "Japan", "region": "other", "lat": 34.6937, "lon": 135.5023},
    {"name": "Kyoto", "country": "Japan", "region": "other", "lat": 35.0116, "lon": 135.7681},

    # SOUTH KOREA
    {"name": "Seoul", "country": "South Korea", "region": "other", "lat": 37.5665, "lon": 126.9780},
    {"name": "Busan", "country": "South Korea", "region": "other", "lat": 35.1796, "lon": 129.0756},

    # INDONESIA
    {"name": "Bali", "country": "Indonesia", "region": "other", "lat": -8.3405, "lon": 115.0920},
    {"name": "Jakarta", "country": "Indonesia", "region": "other", "lat": -6.2088, "lon": 106.8456},

    # AUSTRALIA
    {"name": "Sydney", "country": "Australia", "region": "other", "lat": -33.8688, "lon": 151.2093},
    {"name": "Melbourne", "country": "Australia", "region": "other", "lat": -37.8136, "lon": 144.9631},
    {"name": "Brisbane", "country": "Australia", "region": "other", "lat": -27.4698, "lon": 153.0251},
    {"name": "Perth", "country": "Australia", "region": "other", "lat": -31.9505, "lon": 115.8605},

    # UAE
    {"name": "Dubai", "country": "UAE", "region": "other", "lat": 25.2048, "lon": 55.2708},
    {"name": "Abu Dhabi", "country": "UAE", "region": "other", "lat": 24.4539, "lon": 54.3773},

    # BRAZIL
    {"name": "Sao Paulo", "country": "Brazil", "region": "other", "lat": -23.5505, "lon": -46.6333},
    {"name": "Rio de Janeiro", "country": "Brazil", "region": "other", "lat": -22.9068, "lon": -43.1729},

    # MEXICO
    {"name": "Mexico City", "country": "Mexico", "region": "other", "lat": 19.4326, "lon": -99.1332},
    {"name": "Cancun", "country": "Mexico", "region": "other", "lat": 21.1619, "lon": -86.8515},

    # SOUTH AFRICA
    {"name": "Cape Town", "country": "South Africa", "region": "other", "lat": -33.9249, "lon": 18.4241},
    {"name": "Johannesburg", "country": "South Africa", "region": "other", "lat": -26.2041, "lon": 28.0473},

    # THAILAND
    {"name": "Bangkok", "country": "Thailand", "region": "other", "lat": 13.7563, "lon": 100.5018},
    {"name": "Phuket", "country": "Thailand", "region": "other", "lat": 7.8804, "lon": 98.3923},

    # EGYPT
    {"name": "Cairo", "country": "Egypt", "region": "other", "lat": 30.0444, "lon": 31.2357},

    # NIGERIA
    {"name": "Lagos", "country": "Nigeria", "region": "other", "lat": 6.5244, "lon": 3.3792},

    # ARGENTINA
    {"name": "Buenos Aires", "country": "Argentina", "region": "other", "lat": -34.6037, "lon": -58.3816},

    # NEW ZEALAND
    {"name": "Auckland", "country": "New Zealand", "region": "other", "lat": -36.8485, "lon": 174.7633},
    {"name": "Wellington", "country": "New Zealand", "region": "other", "lat": -41.2865, "lon": 174.7762},

    # COLOMBIA
    {"name": "Bogota", "country": "Colombia", "region": "other", "lat": 4.7110, "lon": -74.0721},
    {"name": "Medellin", "country": "Colombia", "region": "other", "lat": 6.2476, "lon": -75.5658},

    # ECUADOR
    {"name": "Quito", "country": "Ecuador", "region": "other", "lat": -0.1807, "lon": -78.4678},

    # COSTA RICA
    {"name": "San Jose", "country": "Costa Rica", "region": "other", "lat": 9.9281, "lon": -84.0907},
]

BATCH_SIZE = 5

START_DATE = "1991-01-01"
END_DATE = "2025-12-31"
EXPECTED_RECORDS = 420


class Command(BaseCommand):
    help = "Fetch 1991-2025 historical weather — single range, auto-cleanup of old chunk data"

    def add_arguments(self, parser):
        parser.add_argument("--batch-size", type=int, default=BATCH_SIZE)

    def handle(self, *args, **options):
        batch_size = options["batch_size"]

        # Step 1 — Cleanup: delete old/incomplete chunk data for cities we'll re-fetch
        affected_slugs = []
        for c in CITIES:
            slug = c["name"].lower().replace(" ", "-").replace(",", "")
            count = HistoricalWeather.objects.filter(city__slug=slug).count()
            if count != EXPECTED_RECORDS:
                affected_slugs.append(slug)

        if affected_slugs:
            deleted, _ = HistoricalWeather.objects.filter(city__slug__in=affected_slugs).delete()
            self.stdout.write(self.style.WARNING(f"Cleanup: {deleted} old records deleted from {len(affected_slugs)} cities"))

        # Step 2 — Find cities needing fetch
        done_slugs = set(
            City.objects.annotate(record_count=Count("historical_data"))
            .filter(record_count__gte=EXPECTED_RECORDS)
            .values_list("slug", flat=True)
        )
        remaining = [
            c for c in CITIES
            if c["name"].lower().replace(" ", "-").replace(",", "") not in done_slugs
        ]

        self.stdout.write(self.style.WARNING(
            f"Total: {len(CITIES)} | Done: {len(CITIES) - len(remaining)} | Remaining: {len(remaining)}"
        ))

        if not remaining:
            self.stdout.write(self.style.SUCCESS("Sab cities ka data complete hai!"))
            return

        batches = [remaining[i:i + batch_size] for i in range(0, len(remaining), batch_size)]

        for batch_num, batch in enumerate(batches, 1):
            self.stdout.write(f"\nBatch {batch_num}/{len(batches)} ({len(batch)} cities)...")
            results = self.fetch_batch(batch, START_DATE, END_DATE)

            if results is None:
                self.stdout.write(self.style.ERROR(
                    "  Stopping. Saved data safe hai — next run resume karega."
                ))
                return

            if isinstance(results, dict):
                results = [results]

            for city_data, result in zip(batch, results):
                try:
                    self.save_city(city_data, result)
                except Exception as e:
                    self.stdout.write(self.style.ERROR(f"    Failed to save {city_data['name']}: {e}"))

            time.sleep(15)

        self.stdout.write(self.style.SUCCESS("\nSab cities — complete!"))

    def fetch_batch(self, batch, start_date, end_date, retries=3):
        url = settings.OPEN_METEO_ARCHIVE_URL
        params = {
            "latitude": ",".join(str(c["lat"]) for c in batch),
            "longitude": ",".join(str(c["lon"]) for c in batch),
            "start_date": start_date,
            "end_date": end_date,
            "daily": "temperature_2m_max,temperature_2m_min,precipitation_sum,"
                     "rain_sum,sunshine_duration,relative_humidity_2m_mean",
            "timezone": "auto",
        }

        for attempt in range(retries):
            try:
                resp = requests.get(url, params=params, headers=HEADERS, timeout=120)
            except requests.exceptions.RequestException as e:
                self.stdout.write(self.style.ERROR(f"    Network error: {e}"))
                time.sleep(10 * (attempt + 1))
                continue

            if resp.status_code == 200:
                return resp.json()

            if resp.status_code == 429:
                body_text = resp.text
                self.stdout.write(self.style.ERROR(f"    429 — body: {body_text[:300]}"))

                lower_body = body_text.lower()
                if "hour" in lower_body or "daily" in lower_body or "tomorrow" in lower_body:
                    self.stdout.write(self.style.ERROR(
                        "    Hourly/Daily quota khatam — is run mein retry karna bekar hai. Stopping."
                    ))
                    return None

                wait = 65
                self.stdout.write(f"    Minutely limit — {wait}s wait (retry {attempt + 1}/{retries})...")
                time.sleep(wait)
                continue

            self.stdout.write(self.style.ERROR(f"    {resp.status_code} — body: {resp.text[:300]}"))
            return None

        return None

    def save_city(self, city_data, result):
        name = city_data["name"]
        slug = name.lower().replace(" ", "-").replace(",", "")
        city, _ = City.objects.get_or_create(
            slug=slug,
            defaults={
                "name": name, "country": city_data["country"], "region": city_data["region"],
                "latitude": city_data["lat"], "longitude": city_data["lon"],
            },
        )

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

        self.stdout.write(self.style.SUCCESS(f"    {name} - {saved} records"))
