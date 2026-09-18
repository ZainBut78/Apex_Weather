"""Cache kitni der rakhni hai — Open-Meteo ke model runs ke hisaab se.

═══════════════════════════════════════════════════════════════════════
MASLA JO HAL KAR RAHE HAIN
═══════════════════════════════════════════════════════════════════════

Pehle har jagah ek hi flat TTL tha: 3 ghante (CACHE_TIMEOUT = 10800),
chahe woh New York ho ya Karachi. Do taraf se ghalat tha:

  * New York ka data Open-Meteo par HAR GHANTE naya aata hai (HRRR
    model), magar hum 3 ghante purana dikhate rehte the.
  * Karachi ka data 6 ghante mein ek dafa badalta hai (ICON Global),
    magar hum 3 ghante baad dobara call kar dete the — aur bilkul wohi
    data wapas milta tha. Yani aadhi calls bilkul bekaar.

Ab TTL "agla model run kab aayega" se bandha hua hai. Jab Open-Meteo ke
paas naya data aata hai, tab hi hamari cache khatam hoti hai — na pehle
(bekaar call), na baad mein (basi data).

═══════════════════════════════════════════════════════════════════════
KON SA MULK KIS TIER MEIN, AUR KYUN
═══════════════════════════════════════════════════════════════════════

Open-Meteo `best_match` har jagah ke liye sab se behtareen model chunta
hai. Kis mulk par kaun sa model chalta hai, us ka run interval alag hai
(Open-Meteo ki apni docs se):

  TIER 1 — har 1 ghante
      USA / Canada    NOAA HRRR        har ghanta
      UK              UK Met Office    har ghanta
      France          Meteo-France     har ghanta

  TIER 2 — har 3 ghante
      Baqi Europe     DWD ICON-EU      har 3 ghante
      Japan           JMA              har 3 ghante

  TIER 3 — har 6 ghante  (default — Pakistan, India, Middle East,
      Africa, South America, baqi Asia, Australia)
      Kisi maqami model ka coverage nahi, to global model chalta hai:
      DWD ICON Global / NOAA GFS / ECMWF IFS — teeno har 6 ghante.

Yani aap ka andaza (USA 1h / Europe 3h / baqi 6h) docs ke mutabiq
durust tha. Japan is mein istisna hai — woh 6 nahi, 3 ghante hai.

═══════════════════════════════════════════════════════════════════════
"RUN GRID" — sirf ginti nahi, waqt ka hisaab
═══════════════════════════════════════════════════════════════════════

Ahem baat: model run FIXED UTC waqton par hota hai, jab marzi nahi:

    6-ghante wala  ->  00, 06, 12, 18 UTC
    3-ghante wala  ->  00, 03, 06, 09, 12, 15, 18, 21 UTC
    1-ghanta wala  ->  har ghante ke shuru mein

Is liye TTL fix "6 ghante" rakhna theek nahi. Farz karein 05:50 UTC par
call hui — fix 6 ghante ka matlab agli call 11:50 par, halanke naya data
06:00 ke run se (kuch der baad) aa chuka hota hai. Poore 6 ghante purana
data dikhta rehta.

Ab hum "agle run tak kitne second baqi hain" nikalte hain. 05:50 par TTL
sirf ~10 minute + lag banta hai, aur 06:15 par nayi call chali jati hai.

LAG kyun: run 06:00 par SHURU hota hai, magar data process ho kar API
par aane mein waqt lagta hai (global models mein aam tor par gante do
ghante). RUN_LAG_MINUTES usi ka hisaab hai — is se pehle call karne ka
faida nahi, purana hi data milega.

Sab kuch .env se tune ho sakta hai, code chhue baghair:

    CACHE_TIER1_HOURS=1
    CACHE_TIER2_HOURS=3
    CACHE_TIER3_HOURS=6
    CACHE_TIER1_LAG_MINUTES=60
    CACHE_TIER2_LAG_MINUTES=120
    CACHE_TIER3_LAG_MINUTES=210
    CACHE_MIN_SECONDS=600
"""

import logging
import os
from datetime import datetime, timedelta, timezone

logger = logging.getLogger(__name__)


def _env_int(name, default):
    try:
        val = int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default
    return val if val > 0 else default


# Har tier ka run interval (ghante). Run grid inhi se banta hai.
TIER_HOURS = {
    1: _env_int("CACHE_TIER1_HOURS", 1),
    2: _env_int("CACHE_TIER2_HOURS", 3),
    3: _env_int("CACHE_TIER3_HOURS", 6),
}

# Run SHURU hone se data API par pohnchne tak ka waqt.
#
# Yeh har model ka alag hai aur Open-Meteo apni docs mein exact number
# nahi deta, is liye yeh mohtaat andazay hain — aur jaan booch kar ZYADA
# rakhe gaye hain. Wajah:
#
#   lag ZYADA rakha  -> hum thora DER se call karenge. Nuqsan: data kuch
#                       minute purana. Koi call zaya nahi hoti.
#   lag KAM rakha    -> hum data aane se PEHLE call kar baithenge, wahi
#                       purana data dobara cache ho jayega, aur ab agle
#                       POORE interval tak basi rahega. Yani ek zaya call
#                       AUR basi data — dono nuqsan.
#
# Is liye galti karni ho to bari taraf karo.
RUN_LAG_MINUTES = {
    1: _env_int("CACHE_TIER1_LAG_MINUTES", 60),
    2: _env_int("CACHE_TIER2_LAG_MINUTES", 120),
    3: _env_int("CACHE_TIER3_LAG_MINUTES", 210),
}

# Agla run bilkul qareeb ho to itni der to cache rakho — warna har
# request ke sath call jayegi.
MIN_SECONDS = _env_int("CACHE_MIN_SECONDS", 600)

DEFAULT_TIER = 3


# ── Mulk -> tier ───────────────────────────────────────────────────
# Naam lowercase mein; City.country geocoding se aata hai, is liye
# mukhtalif spellings bhi shamil hain.

TIER1_COUNTRIES = {
    "united states", "united states of america", "usa", "us",
    "canada",
    "united kingdom", "uk", "great britain", "england", "scotland", "wales",
    "france",
}

TIER2_COUNTRIES = {
    # ICON-EU ka coverage
    "germany", "italy", "spain", "portugal", "netherlands", "belgium",
    "luxembourg", "switzerland", "austria", "poland", "czechia",
    "czech republic", "slovakia", "slovenia", "hungary", "romania",
    "bulgaria", "croatia", "serbia", "bosnia and herzegovina", "albania",
    "north macedonia", "montenegro", "greece", "ireland", "denmark",
    "norway", "sweden", "finland", "estonia", "latvia", "lithuania",
    "belarus", "ukraine", "moldova", "iceland", "malta", "cyprus",
    "turkey", "turkiye",
    # JMA
    "japan",
}


def tier_for_country(country):
    """Mulk ke naam se tier. Na pehchana jaye to 3 (sab se mehfooz)."""
    name = (country or "").strip().lower()
    if not name:
        return DEFAULT_TIER
    if name in TIER1_COUNTRIES:
        return 1
    if name in TIER2_COUNTRIES:
        return 2
    return DEFAULT_TIER


def tier_for_city(city):
    return tier_for_country(getattr(city, "country", None))


# ── Agle run tak kitna waqt ────────────────────────────────────────

def next_data_arrival(tier=DEFAULT_TIER, now=None):
    """Agla naya data API par kab pohnchega (UTC).

    Tareeqa: har run ka data `run + lag` par milta hai. Hamein wo pehla
    `run + lag` chahiye jo ABHI se aage ho. Us ko seedha nikalne ka
    tareeqa yeh hai ke (now - lag) ke baad wala pehla run boundary lo —
    us ka data yaqeeni tor par abhi tak nahi aaya.

    PEHLE YAHAN BUG THA: main lag ko "agle" run par jorta tha. 06:10 par
    (6-ghante grid, 90 min lag) woh 13:30 deta tha — halanke 06:00 wale
    run ka data 07:30 par aa jata hai. Yani hum 7 ghante tak 00:00 wale
    run ka purana data dikhate rehte. Ab 07:30 nikalta hai.
    """
    interval_h = TIER_HOURS.get(tier, TIER_HOURS[DEFAULT_TIER])
    lag = timedelta(minutes=RUN_LAG_MINUTES.get(tier, RUN_LAG_MINUTES[DEFAULT_TIER]))
    now = now or datetime.now(timezone.utc)

    # Wo lamha jis ke baad wale run ka data abhi tak nahi aaya
    cutoff = now - lag
    midnight = cutoff.replace(hour=0, minute=0, second=0, microsecond=0)
    hours_in = (cutoff - midnight).total_seconds() / 3600

    # cutoff ke BAAD wala pehla run boundary
    next_run_index = int(hours_in // interval_h) + 1
    next_run = midnight + timedelta(hours=next_run_index * interval_h)

    return next_run + lag


def seconds_until_next_run(tier=DEFAULT_TIER, now=None):
    """Cache kitne second rakhni hai — agle naye data tak."""
    now = now or datetime.now(timezone.utc)
    seconds = int((next_data_arrival(tier, now=now) - now).total_seconds())
    return max(seconds, MIN_SECONDS)


def forecast_ttl(country=None, city=None):
    """Us jagah ke liye cache TTL (seconds).

    country ya city — dono na mile to tier 3 (6 ghante ka grid).
    """
    if city is not None:
        tier = tier_for_city(city)
    else:
        tier = tier_for_country(country)
    return seconds_until_next_run(tier)


def describe(country=None, city=None, now=None):
    """Sirf debugging/report ke liye — kya faisla hua aur kyun."""
    tier = tier_for_city(city) if city is not None else tier_for_country(country)
    return {
        "country": getattr(city, "country", country),
        "tier": tier,
        "interval_hours": TIER_HOURS.get(tier, TIER_HOURS[DEFAULT_TIER]),
        "lag_minutes": RUN_LAG_MINUTES.get(tier, RUN_LAG_MINUTES[DEFAULT_TIER]),
        "ttl_seconds": seconds_until_next_run(tier, now=now),
        "next_data_at": next_data_arrival(tier, now=now).isoformat(),
    }
