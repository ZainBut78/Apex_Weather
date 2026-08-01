ACTIVITY_TO_AFFILIATE_CATEGORY = {
    "beach_water": "swimwear_sunscreen",
    "picnic_park": "picnic_gear",
    "hiking_outdoor": "hiking_gear",
    "indoor_museum": "travel_books_umbrella",
    "indoor_sheltered": "travel_umbrella_raincoat",
    "indoor_midday": "sun_protection_hats",
    "city_sightseeing": "city_travel_essentials",
}


def recommend_daily_activity(rain_prob, wind_kmh, temp_c, is_coastal, has_hiking_trails):
    if rain_prob > 50:
        return "indoor_museum"
    if wind_kmh is not None and wind_kmh > 30:
        return "indoor_sheltered"
    if temp_c > 32 and is_coastal:
        return "beach_water"
    if temp_c > 32:
        return "indoor_midday"
    if 18 <= temp_c <= 28 and rain_prob < 20 and is_coastal:
        return "beach_water"
    if 18 <= temp_c <= 28 and has_hiking_trails:
        return "hiking_outdoor"
    if 15 <= temp_c <= 26:
        return "picnic_park"
    return "city_sightseeing"
