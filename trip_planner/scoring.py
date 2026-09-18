def calculate_day_score(rain_prob, wind_kmh, temp_max, temp_min):
    # Open-Meteo kabhi kabhi null values deta hai (khaas kar forecast
    # horizon ke kinare pe). events/scoring.py mein yeh guard pehle se
    # tha, yahan nahi — None > 20 comparison TypeError deta tha.
    rain_prob = rain_prob or 0
    temp_max = temp_max if temp_max is not None else 0
    temp_min = temp_min if temp_min is not None else 0

    score = 10.0

    if rain_prob > 20:
        rain_penalty = 0.5 + ((rain_prob - 20) / 80) * 4.5
        score -= min(rain_penalty, 5)

    if wind_kmh is not None and wind_kmh > 20:
        wind_penalty = min((wind_kmh - 20) / 10 * 0.5, 2)
        score -= wind_penalty

    if temp_max > 38 or temp_min < 0:
        score -= 2
    elif temp_max > 32 or temp_min < 5:
        score -= 1

    return max(1, round(score, 1))


def get_packing_suggestions(days):
    items = []
    if any(d["rain_probability"] > 40 for d in days):
        items.append({"item": "Umbrella / Raincoat", "reason": "Rain expected on one or more days"})
    if any(d["temp_max"] > 30 for d in days):
        items.append({"item": "Sunscreen", "reason": "High temperatures expected"})
    if any(d["temp_min"] < 10 for d in days):
        items.append({"item": "Light Jacket", "reason": "Cool temperatures on some days"})
    return items


def calculate_day_parts(hourly_data, target_date):
    times = hourly_data.get("time", [])
    temps = hourly_data.get("temperature_2m", [])
    rains = hourly_data.get("precipitation_probability", [])
    winds = hourly_data.get("wind_speed_10m", [])

    parts = {
        "morning": {"hours": range(6, 12), "temps": [], "rains": [], "winds": []},
        "afternoon": {"hours": range(12, 18), "temps": [], "rains": [], "winds": []},
        "evening": {"hours": range(18, 22), "temps": [], "rains": [], "winds": []},
    }

    for i, t in enumerate(times):
        if not t.startswith(target_date):
            continue
        hour = int(t.split("T")[1].split(":")[0])
        for part_name, part_data in parts.items():
            if hour in part_data["hours"]:
                part_data["temps"].append(temps[i])
                part_data["rains"].append(rains[i])
                part_data["winds"].append(winds[i])

    result = {}
    for part_name, part_data in parts.items():
        if part_data["temps"]:
            result[part_name] = {
                "temp": round(sum(part_data["temps"]) / len(part_data["temps"]), 1),
                "rain_probability": round(sum(part_data["rains"]) / len(part_data["rains"])),
                "wind_kmh": round(sum(part_data["winds"]) / len(part_data["winds"]), 1),
            }
        else:
            result[part_name] = None

    return result
