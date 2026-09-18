import logging
import unicodedata
import os
import requests
from datetime import date, timedelta
from django.conf import settings
from django.db.models import Avg
from django.core.cache import cache
from weather.cache_policy import forecast_ttl
from django.utils.text import slugify
from weather.models import City, HistoricalWeather
from weather.services import log_external_call, log_service_request

logger = logging.getLogger(__name__)

# CACHE_TIMEOUT ab sirf FALLBACK hai. Asal TTL weather.cache_policy se
# aata hai, jo us jagah ke model run ke hisaab se hota hai (USA 1 ghanta,
# Europe 3, baqi 6). Yeh sirf tab chalta hai jab mulk maloom na ho.
CACHE_TIMEOUT = int(os.getenv("FORECAST_CACHE_SECONDS", 10800))

HEADERS = {"User-Agent": f"WeatherApex-TripPlanner/1.0 (contact: {settings.API_CONTACT_EMAIL})"}

FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"


def get_city_local(city_query):
    """Sirf APNE database mein dhoondo — koi external call NAHI.

    Yeh alag function is liye hai ke views pehle sasta local check kar
    sakein: agar city hamare paas already hai to woh request Open-Meteo
    ko kuch cost nahi karti, aur us par anonymous visitor ka free quota
    kharch karna ghalat hai.
    """
    city_query = (city_query or "").strip()
    if not city_query:
        return None

    city = City.objects.filter(slug__iexact=city_query).first()
    if city:
        return city

    city = City.objects.filter(name__iexact=city_query).first()
    if city:
        return city

    return City.objects.filter(name__icontains=city_query).first()


# ══════════════════════════════════════════════════════════════════════
# "pakistan" jaisa MULK ka naam shehar samajh liya jata tha
#
# Pehle yeh function geocoding ko `count=1` ke sath call karta tha aur
# JO PEHLA result aata, usay shehar maan leta tha. "pakistan" par
# Open-Meteo ka pehla result yeh hai:
#
#     { "name": "Pakistan", "feature_code": "PCLI",
#       "latitude": 30.0, "longitude": 70.0, "population": 212215030 }
#
# PCLI ka matlab hai "poora mulk", aur 30.0/70.0 Cholistan ke registan
# mein ek nuqta hai — kisi shehar ka pata nahi. Nateeja:
#
#   * Event Risk us registan ka mausam nikalta: barish 0%, hawa halki,
#     garmi 30 degree -> risk score 0.0. Yani "Pakistan ka score 0",
#     jo bebunyaad hai — mulk mein sainkron shehar hain, sab ka mausam
#     alag hai.
#   * Aur DB mein "Pakistan" naam ki ek JUNK city ban jati thi. (Isi
#     tarah pehle "france" ki junk row bani thi.)
#
# Ab sirf ASLI abaadi wali jaghein (GeoNames feature_code "PPL*")
# qubool hoti hain. Mulk (PCLI...) ya soobe (ADM1...) par hum koi city
# nahi banate — view ko batate hain ke user ko shehar poochho.
#
# EK PECHEEDAGI: sirf "abaadi wali jagah chun lo" kaafi nahi nikla.
# Punjab mein "Pakistan" naam ka ek GAON bhi hai (feature_code PPL,
# population maloom nahi). Us par bharosa karein to user "pakistan"
# likhe aur usay ek gumnaam gaon ka mausam mil jaye — pehle se behtar,
# magar phir bhi ghalat.
#
# Asli signal yeh hai: jo mulk apne shehar ke naam ka hai (Singapore,
# Monaco, Luxembourg, Kuwait) un ke liye Open-Meteo **PPLC** deta hai,
# yani "kisi mulk ka darul hukoomat" — aur wohi asli shehar hai:
#
#   singapore -> PPLC Singapore (5,638,700)  +  PCLI Singapore
#   monaco    -> PPLC Monaco    (32,965)     +  PCLI Monaco
#   pakistan  -> PCLI Pakistan  (212m)       +  PPL  "Pakistan" (gaon)
#
# Is liye tarteeb yeh hai:
#   1. Query ke naam ka PPLC mila?         -> SHEHAR (Singapore, Monaco)
#   2. Query ke naam ka mulk/soobа mila?   -> MULK/SOOBA (Pakistan, Punjab)
#   3. Warna sab se bari abaadi wala PPL   -> SHEHAR (Lahore, Paris)
#
# GeoNames feature codes:
#   PPLC                       -> darul hukoomat                    ✓✓
#   PPL, PPLA, PPLA2...        -> abaadi wali jagah (shehar/qasba)  ✓
#   PCLI, PCLD, PCLS, PCLF     -> mulk                              ✗
#   ADM1, ADM2, ADM3...        -> soobа / zila                      ✗
#   CONT                       -> barr-e-azam                       ✗
# ══════════════════════════════════════════════════════════════════════

KIND_CITY = "city"
KIND_COUNTRY = "country"
KIND_REGION = "region"
KIND_NONE = "none"

_COUNTRY_CODES = {"PCLI", "PCLD", "PCLS", "PCLF", "PCLIX", "PCL", "TERR"}


def _place_kind(feature_code):
    fc = (feature_code or "").upper()
    if fc.startswith("PPL"):
        return KIND_CITY
    if fc in _COUNTRY_CODES:
        return KIND_COUNTRY
    if fc.startswith("ADM") or fc == "CONT":
        return KIND_REGION
    return KIND_NONE


def _norm(text):
    """Naam ka moqabla karne ke liye — chhote huroof, bina accent, bina extra space."""
    text = unicodedata.normalize("NFKD", str(text or ""))
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return " ".join(text.lower().split())


def lookup_place(place_query, feature="other"):
    """Query ko hal karo aur BATAO ke woh kya nikli.

    Returns dict:
        kind      -> "city" | "country" | "region" | "none"
        city      -> City object (sirf kind == "city" par)
        label     -> jo naam geocoding ne diya ("Pakistan")
        country   -> us jagah ka mulk
        suggestions -> kind country/region par: usi mulk ke hamare
                       database ke shehar (City objects)
    """
    place_query = (place_query or "").strip()
    if not place_query:
        return {"kind": KIND_NONE, "city": None, "label": "", "country": "", "suggestions": []}

    # 1) Apna database pehle — yahan jo hai woh pehle se shehar hai
    city = get_city_local(place_query)
    if city:
        return {"kind": KIND_CITY, "city": city, "label": city.name,
                "country": city.country, "suggestions": []}

    # 2) Geocoding — ab count=10, taake mulk ke neeche se asli shehar
    #    chun sakein (count=1 par sirf mulk hi milta tha).
    try:
        resp = requests.get(GEOCODING_URL, params={"name": place_query, "count": 10},
                            headers=HEADERS, timeout=10)
        log_external_call("geocoding", place_query, success=(resp.status_code == 200),
                          status_code=resp.status_code, feature=feature)
        results = resp.json().get("results", []) or []
    except requests.exceptions.RequestException as e:
        log_external_call("geocoding", place_query, success=False, status_code=None, feature=feature)
        logger.error(f"Geocoding API failed: {e}")
        return {"kind": KIND_NONE, "city": None, "label": place_query,
                "country": "", "suggestions": []}
    except ValueError:
        logger.error("Geocoding API ne valid JSON nahi diya: %s", place_query, exc_info=True)
        return {"kind": KIND_NONE, "city": None, "label": place_query,
                "country": "", "suggestions": []}

    if not results:
        return {"kind": KIND_NONE, "city": None, "label": place_query,
                "country": "", "suggestions": []}

    wanted = _norm(place_query)
    cities = [r for r in results if _place_kind(r.get("feature_code")) == KIND_CITY]

    # 1) Query ke naam ka darul hukoomat (PPLC)? Woh yaqeeni shehar hai.
    #    Singapore/Monaco/Luxembourg jaise mulk isi se theek handle hote
    #    hain, warna woh "mulk" mein chale jate.
    capital = next(
        (r for r in results
         if (r.get("feature_code") or "").upper() == "PPLC"
         and _norm(r.get("name")) == wanted),
        None,
    )

    # 2) Query ke naam ka MULK ya SOOBA? To user ka matlab wohi tha —
    #    chahe usi naam ka koi gumnaam gaon bhi maujood ho.
    admin_match = next(
        (r for r in results
         if _place_kind(r.get("feature_code")) in (KIND_COUNTRY, KIND_REGION)
         and _norm(r.get("name")) == wanted),
        None,
    )

    if capital is None and admin_match is not None:
        kind = _place_kind(admin_match.get("feature_code"))
        country_name = admin_match.get("country") or admin_match.get("name") or ""
        return {
            "kind": kind, "city": None,
            "label": admin_match.get("name") or place_query,
            "country": country_name,
            "suggestions": list(
                City.objects.filter(country__iexact=country_name).order_by("name")[:8]
            ),
        }

    # 3) Warna sab se bari abaadi wala shehar.
    if capital is not None or cities:
        best = capital or max(cities, key=lambda r: r.get("population") or 0)
        name = best.get("name") or place_query
        new_city, _ = City.objects.get_or_create(
            slug=slugify(name),
            defaults={
                "name": name,
                "country": best.get("country", ""),
                "latitude": best.get("latitude"),
                "longitude": best.get("longitude"),
            }
        )
        return {"kind": KIND_CITY, "city": new_city, "label": new_city.name,
                "country": new_city.country, "suggestions": []}

    # Sirf mulk/soobа mila — koi City NAHI banani.
    top = results[0]
    kind = _place_kind(top.get("feature_code"))
    if kind == KIND_NONE:
        kind = KIND_REGION          # kuch aur nikla (jheel, pahar...) — city nahi
    country_name = top.get("country") or top.get("name") or ""

    # Usi mulk ke woh shehar jo hamare paas pehle se hain — user ko
    # seedha chunne ke liye. (Bari abaadi pehle.)
    suggestions = list(
        City.objects.filter(country__iexact=country_name).order_by("name")[:8]
    )

    return {"kind": kind, "city": None, "label": top.get("name") or place_query,
            "country": country_name, "suggestions": suggestions}


# ── Mulk/soobа ka naam aaya to seedha jawab, andaza nahi ────────────
def country_not_a_city_error(place, status=400):
    """Standard error jab user ne shehar ki jagah mulk ka naam likha ho.

    `suggestions` frontend ko clickable chips dikhane ke liye hain.
    """
    label = place.get("label") or "Yeh"
    kind = place.get("kind")
    what = "a country" if kind == KIND_COUNTRY else "a region"
    names = [c.name for c in place.get("suggestions") or []]
    detail = (
        f"{label} is {what}, not a city — and weather is different in every "
        f"city within it, so a single score would be misleading."
    )
    if names:
        detail += f" Try one of these instead: {', '.join(names)}."
    else:
        detail += " Please enter a city name."
    return {
        "error": f"Please enter a city, not {what}",
        "detail": detail,
        "kind": kind,
        "place": label,
        "country": place.get("country") or "",
        "suggestions": [{"name": c.name, "slug": c.slug, "country": c.country}
                        for c in place.get("suggestions") or []],
        "status": status,
    }


def get_city(city_query, feature="other"):
    """Sirf City ya None — purana interface, purane callers ke liye."""
    return lookup_place(city_query, feature=feature)["city"]


def fetch_forecast(latitude, longitude, start_date, end_date, feature="trip_planner",
                   country=None):
    cache_key = f"forecast:{latitude}:{longitude}:{start_date}:{end_date}"
    cached = cache.get(cache_key)
    if cached:
        log_service_request(feature, "cache", f"{latitude},{longitude}")
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

        log_external_call("forecast", f"{latitude},{longitude}", success=(resp.status_code == 200), status_code=resp.status_code, feature=feature)

        if resp.status_code == 200:
            result = resp.json().get("daily", {})
            cache.set(cache_key, result, timeout=forecast_ttl(country=country))
            log_service_request(feature, "external", f"{latitude},{longitude}")
            return result
    except requests.exceptions.RequestException as e:
        log_external_call("forecast", f"{latitude},{longitude}", success=False, status_code=None, feature=feature)
        logger.error(f"Forecast API failed: {e}")

    return None


def fetch_forecast_batch(city_list, start_date, end_date, feature="trip_planner"):
    if not city_list:
        return []

    cache_key = f"forecast_batch:{','.join(str(c.id) for c in city_list)}:{start_date}:{end_date}"
    cached = cache.get(cache_key)
    if cached:
        log_service_request(feature, "cache", ",".join(c.name for c in city_list))
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

        log_external_call("forecast", ",".join(str(c.name) for c in city_list), success=(resp.status_code == 200), status_code=resp.status_code, feature=feature)

        if resp.status_code == 200:
            data = resp.json()
            if isinstance(data, list):
                result = [item.get("daily", {}) for item in data]
            else:
                result = [data.get("daily", {})]
            # Batch mein kai mulk ho sakte hain — sab se CHHOTA TTL lo,
            # warna tez update hone wale mulk (jaise USA) ka data
            # sust wale (jaise Pakistan) ke sath basi reh jayega.
            ttl = min((forecast_ttl(country=c.country) for c in city_list),
                      default=CACHE_TIMEOUT)
            cache.set(cache_key, result, timeout=ttl)
            log_service_request(feature, "external", ",".join(c.name for c in city_list))
            return result
    except requests.exceptions.RequestException as e:
        log_external_call("forecast", ",".join(str(c.name) for c in city_list), success=False, status_code=None, feature=feature)
        logger.error(f"Batch forecast API failed: {e}")

    return None


def fetch_hourly_forecast(latitude, longitude, start_date, end_date, feature="trip_planner",
                          country=None):
    cache_key = f"hourly_forecast:{latitude}:{longitude}:{start_date}:{end_date}"
    cached = cache.get(cache_key)
    if cached:
        log_service_request(feature, "cache", f"{latitude},{longitude}")
        return cached

    try:
        resp = requests.get(FORECAST_URL, params={
            "latitude": latitude,
            "longitude": longitude,
            "start_date": start_date,
            "end_date": end_date,
            # is_day = us jagah ke asli sunrise/sunset ke hisaab se 1/0
            "hourly": "temperature_2m,precipitation_probability,"
                      "wind_speed_10m,relative_humidity_2m,weather_code,is_day",
            "timezone": "auto",
        }, headers=HEADERS, timeout=30)

        log_external_call("forecast", f"{latitude},{longitude}", success=(resp.status_code == 200), status_code=resp.status_code, feature=feature)

        if resp.status_code == 200:
            result = resp.json().get("hourly", {})
            cache.set(cache_key, result, timeout=forecast_ttl(country=country))
            log_service_request(feature, "external", f"{latitude},{longitude}")
            return result
    except requests.exceptions.RequestException as e:
        log_external_call("forecast", f"{latitude},{longitude}", success=False, status_code=None, feature=feature)
        logger.error(f"Hourly forecast API failed: {e}")

    return None


def get_historical_estimate(city, start_date, end_date, feature="trip_planner"):
    if isinstance(start_date, str):
        start_date = date.fromisoformat(start_date)
    if isinstance(end_date, str):
        end_date = date.fromisoformat(end_date)

    unique_months = set()
    current = start_date
    while current <= end_date:
        unique_months.add(current.month)
        current += timedelta(days=1)

    # Pehle har unique month ke liye ek alag aggregate query chalti thi.
    # Ab ek GROUP BY month query.
    month_averages = {
        row["month"]: row
        for row in HistoricalWeather.objects.filter(
            city=city, month__in=unique_months
        )
        .values("month")
        .annotate(
            avg_max=Avg("avg_temp_max"),
            avg_min=Avg("avg_temp_min"),
            avg_rain=Avg("avg_rainfall"),
            avg_rainy=Avg("rainy_days"),
        )
    }
    # Jis month ka data DB mein nahi hai uske liye None-values wala row
    # (purana .aggregate() bhi None deta tha, is liye behaviour same hai).
    EMPTY_AGG = {"avg_max": None, "avg_min": None,
                 "avg_rain": None, "avg_rainy": None}

    daily = {"time": [], "temperature_2m_max": [], "temperature_2m_min": [],
             "precipitation_probability_max": [], "wind_speed_10m_max": [], "weather_code": []}

    current = start_date
    while current <= end_date:
        daily["time"].append(current.isoformat())
        avg_data = month_averages.get(current.month, EMPTY_AGG)

        daily["temperature_2m_max"].append(round(avg_data["avg_max"], 1) if avg_data["avg_max"] else 0)
        daily["temperature_2m_min"].append(round(avg_data["avg_min"], 1) if avg_data["avg_min"] else 0)

        rainy = avg_data["avg_rainy"] if avg_data["avg_rainy"] else 0
        rain_prob = min(round((rainy / 30) * 100), 100)
        daily["precipitation_probability_max"].append(rain_prob)

        daily["wind_speed_10m_max"].append(None)
        daily["weather_code"].append(0)

        current += timedelta(days=1)

    log_service_request(feature, "database", city.name)
    return daily
