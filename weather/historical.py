"""Historical weather ka SINGLE source of truth.

Pehle historical data teen mukhtalif jagah se store hota tha aur
**teeno ka formula alag tha** — khaas kar `avg_rainfall`:

    fetch_all_cities.py          ->  sum(precip)   = mahine ka TOTAL mm
    fetch_historical_weather.py  ->  sum(precip)   = mahine ka TOTAL mm
    weather/views.py (on-demand) ->  mean(precip)  = ROZ ka average mm

Ek hi column mein do units — ek mahina jisme roz 2mm barish hui, bulk path
se 60.0 store hota tha aur on-demand path se 2.0. Yani 30x ka farq, aur
climate comparison bilkul ghalat.

Ab saare paths yahin se guzarte hain:
    * weather/views.py                    (on-demand, naya city)
    * fetch_all_cities.py                 (bulk, ~250 cities)
    * fetch_historical_weather.py         (single city)
    * sync_historical.py                  (saalana incremental refresh)

INCREMENTAL FETCH: `ensure_history(city)` sirf woh saal Open-Meteo se
maangta hai jo DB mein **complete nahi** hain. Agar DB mein 2006-2025 hai
aur target 2007-2026 hai, to sirf 2026 ke liye ek call jayegi — poora
20-saal ka data dobara nahi aayega.
"""

import logging
import statistics
from datetime import date

import requests
from django.conf import settings
from django.db.models import Count

from .models import HistoricalWeather
from .services import log_external_call

logger = logging.getLogger(__name__)

ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"

# Open-Meteo archive se yeh daily variables maangte hain (saare paths same).
DAILY_VARS = (
    "temperature_2m_max,temperature_2m_min,precipitation_sum,"
    "sunshine_duration,relative_humidity_2m_mean"
)

# "Rain day" ki standard definition — 1mm ya zyada barish wala din.
RAIN_DAY_THRESHOLD_MM = 1.0

# Adhoore mahine store na karo. Yeh khaas kar ab zaroori hai kyunke
# avg_rainfall ek TOTAL hai: agar mahine ke sirf 5 din ka data mile to
# total jhoot bolega (bohot kam lagega). Poora mahina chhod dena behtar hai.
MIN_DAYS_FOR_MONTH = 20

MONTHS_IN_YEAR = 12


# ──────────────────────────────────────────────────────────────────────
# Year range — .env ke HISTORICAL_YEARS se
# ──────────────────────────────────────────────────────────────────────

def latest_complete_year(today=None):
    """Aakhri POORA saal. Chal raha saal adhoora hai, us ka data nahi lete."""
    today = today or date.today()
    return today.year - 1


def target_year_range(today=None):
    """(start_year, end_year) — settings.HISTORICAL_YEARS ke hisaab se.

    HISTORICAL_YEARS=20 aur aaj 2026 ho to -> (2006, 2025).
    Agla saal (2027) aane par khud (2007, 2026) ban jayega, aur
    ensure_history sirf 2026 fetch karega.
    """
    end = latest_complete_year(today)
    years = getattr(settings, "HISTORICAL_YEARS", 20)
    start = end - years + 1
    return start, end


# ──────────────────────────────────────────────────────────────────────
# Aggregation — EK formula, saare paths ke liye
# ──────────────────────────────────────────────────────────────────────

def aggregate_daily_to_monthly(daily):
    """Open-Meteo ka daily block -> {(year, month): row_dict}.

    Formula (ab sab jagah yehi):
        avg_temp_max   = us mahine ke daily max ka average       (degC)
        avg_temp_min   = us mahine ke daily min ka average       (degC)
        avg_rainfall   = us mahine ki KUL barish (TOTAL)         (mm)   <-- total, average nahi
        rainy_days     = un dinon ki GINTI jinme >= 1mm barish hui
        sunshine_hours = roz ki average sunshine                 (hours)
        avg_humidity   = us mahine ki average humidity           (%)
    """
    dates = daily.get("time") or []
    temp_max = daily.get("temperature_2m_max") or []
    temp_min = daily.get("temperature_2m_min") or []
    precip = daily.get("precipitation_sum") or []
    sunshine = daily.get("sunshine_duration") or []
    humidity = daily.get("relative_humidity_2m_mean") or []

    buckets = {}
    for i, d in enumerate(dates):
        try:
            dt = date.fromisoformat(d)
        except (ValueError, TypeError):
            continue
        b = buckets.setdefault(
            (dt.year, dt.month),
            {"days": 0, "tmax": [], "tmin": [], "precip": [], "rain_days": 0,
             "sun": [], "hum": []},
        )
        b["days"] += 1

        if i < len(temp_max) and temp_max[i] is not None:
            b["tmax"].append(temp_max[i])
        if i < len(temp_min) and temp_min[i] is not None:
            b["tmin"].append(temp_min[i])
        if i < len(precip) and precip[i] is not None:
            b["precip"].append(precip[i])
            if precip[i] >= RAIN_DAY_THRESHOLD_MM:
                b["rain_days"] += 1
        if i < len(sunshine) and sunshine[i] is not None:
            b["sun"].append(sunshine[i] / 3600.0)
        if i < len(humidity) and humidity[i] is not None:
            b["hum"].append(humidity[i])

    monthly = {}
    for key, b in buckets.items():
        if b["days"] < MIN_DAYS_FOR_MONTH:
            continue          # adhoora mahina — total galat hoga
        if not b["tmax"] and not b["tmin"]:
            continue          # temperature hi nahi, row bekaar hai
        monthly[key] = {
            "avg_temp_max": round(statistics.mean(b["tmax"]), 1) if b["tmax"] else 0,
            "avg_temp_min": round(statistics.mean(b["tmin"]), 1) if b["tmin"] else 0,
            "avg_rainfall": round(sum(b["precip"]), 1) if b["precip"] else 0,
            "rainy_days": b["rain_days"],
            "sunshine_hours": round(statistics.mean(b["sun"]), 1) if b["sun"] else 0,
            "avg_humidity": round(statistics.mean(b["hum"]), 1) if b["hum"] else 50.0,
        }
    return monthly


def store_monthly(city, monthly):
    """Monthly rows ek hi bulk upsert mein likho (Postgres ON CONFLICT)."""
    if not monthly:
        return 0
    rows = [
        HistoricalWeather(city=city, year=year, month=month, **vals)
        for (year, month), vals in sorted(monthly.items())
    ]
    HistoricalWeather.objects.bulk_create(
        rows,
        update_conflicts=True,
        unique_fields=["city", "year", "month"],
        update_fields=["avg_temp_max", "avg_temp_min", "avg_rainfall",
                       "rainy_days", "sunshine_hours", "avg_humidity"],
    )
    return len(rows)


# ──────────────────────────────────────────────────────────────────────
# Incremental — sirf woh saal jo DB mein complete nahi
# ──────────────────────────────────────────────────────────────────────

def complete_years(city):
    """Woh saal jinke poore 12 mahine DB mein maujood hain."""
    rows = (
        HistoricalWeather.objects
        .filter(city=city)
        .values("year")
        .annotate(n=Count("month"))
        .filter(n__gte=MONTHS_IN_YEAR)
        .values_list("year", flat=True)
    )
    return set(rows)


def missing_year_blocks(city, start_year=None, end_year=None):
    """Missing saal, lagatar blocks mein — taake kam se kam API calls jayein.

    Misaal: 2026 missing hai -> [(2026, 2026)]  = 1 call
            2006-2025 missing -> [(2006, 2025)] = 1 call (20 saal, ek call)
            2010 aur 2026 missing -> [(2010, 2010), (2026, 2026)] = 2 calls
    """
    if start_year is None or end_year is None:
        start_year, end_year = target_year_range()

    have = complete_years(city)
    blocks = []
    for year in range(start_year, end_year + 1):
        if year in have:
            continue
        if blocks and blocks[-1][1] == year - 1:
            blocks[-1][1] = year
        else:
            blocks.append([year, year])
    return [tuple(b) for b in blocks]


def fetch_years(city, start_year, end_year, feature="weather"):
    """Ek Open-Meteo archive call se {start_year}-{end_year} ka data lao + store karo.

    Returns (ok: bool, rows_saved: int).
    """
    params = {
        "latitude": city.latitude,
        "longitude": city.longitude,
        "start_date": f"{start_year}-01-01",
        "end_date": f"{end_year}-12-31",
        "daily": DAILY_VARS,
        "timezone": "auto",
    }
    headers = {
        "User-Agent": f"WeatherApex-HistoryFetch/1.0 "
                      f"(contact: {settings.API_CONTACT_EMAIL})"
    }

    try:
        resp = requests.get(ARCHIVE_URL, params=params, headers=headers, timeout=90)
    except requests.exceptions.RequestException as exc:
        log_external_call("archive", city.name, success=False, status_code=None, feature=feature)
        logger.error("Archive API fail: city=%s %s-%s: %s", city.name, start_year, end_year, exc)
        return False, 0

    log_external_call("archive", city.name, success=(resp.status_code == 200),
                      status_code=resp.status_code, feature=feature)

    if resp.status_code != 200:
        logger.error("Archive API ne %s diya: city=%s %s-%s",
                     resp.status_code, city.name, start_year, end_year)
        return False, 0

    try:
        data = resp.json()
    except ValueError:
        logger.error("Archive API ne valid JSON nahi diya: city=%s", city.name, exc_info=True)
        return False, 0

    monthly = aggregate_daily_to_monthly(data.get("daily") or {})
    if not monthly:
        logger.warning("Archive API se koi usable mahina nahi mila: city=%s %s-%s",
                       city.name, start_year, end_year)
        return False, 0

    return True, store_monthly(city, monthly)


def ensure_history(city, feature="weather", start_year=None, end_year=None):
    """City ka historical data target range tak poora karo — INCREMENTALLY.

    Jo saal DB mein already complete hain unke liye Open-Meteo ko call
    NAHI jati. Sirf missing saal fetch hote hain.

    Returns dict:
        {"complete": bool, "api_calls": int, "rows_saved": int,
         "fetched_years": [...], "missing_after": [...]}
    """
    if start_year is None or end_year is None:
        start_year, end_year = target_year_range()

    blocks = missing_year_blocks(city, start_year, end_year)
    if not blocks:
        return {"complete": True, "api_calls": 0, "rows_saved": 0,
                "fetched_years": [], "missing_after": []}

    api_calls = 0
    rows_saved = 0
    fetched = []
    for y1, y2 in blocks:
        ok, n = fetch_years(city, y1, y2, feature=feature)
        api_calls += 1
        if ok:
            rows_saved += n
            fetched.extend(range(y1, y2 + 1))

    still_missing = missing_year_blocks(city, start_year, end_year)
    return {
        "complete": not still_missing,
        "api_calls": api_calls,
        "rows_saved": rows_saved,
        "fetched_years": fetched,
        "missing_after": still_missing,
    }


def has_any_history(city):
    return HistoricalWeather.objects.filter(city=city).exists()


# ──────────────────────────────────────────────────────────────────────
# Purana ghalat-unit data dhoondne ke liye (rainfall daily-average tha)
# ──────────────────────────────────────────────────────────────────────

# Monthly TOTAL rainfall itni kam (poore saal mein) hone ka matlab aam tor
# par yeh hai ke woh rows daily-AVERAGE formula se store hui thin.
# (Sirf sachmuch sookhe sehra — Aswan, Arica — is se neeche aa sakte hain,
#  is liye yeh sirf ek shubha hai, faisla nahi.)
SUSPICIOUS_MAX_MONTHLY_MM = 15.0


def cities_with_suspicious_rainfall(start_year=None, end_year=None):
    """Woh cities jinka rainfall daily-average lagta hai (purana formula)."""
    from django.db.models import Max
    if start_year is None or end_year is None:
        start_year, end_year = target_year_range()
    rows = (
        HistoricalWeather.objects
        .filter(year__gte=start_year, year__lte=end_year)
        .values("city_id", "city__name", "city__slug")
        .annotate(max_rain=Max("avg_rainfall"))
        .filter(max_rain__lt=SUSPICIOUS_MAX_MONTHLY_MM)
        .order_by("city__slug")
    )
    return list(rows)
