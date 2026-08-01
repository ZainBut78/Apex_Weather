EVENT_DURATION_HOURS = 3  # config-level constant, future mein user se bhi le sakte hain


def calculate_risk_score(rain_prob, wind_kmh, temp_c, humidity_pct, weights):
    rain_prob = rain_prob or 0
    temp_c = temp_c or 0

    rain_component = (rain_prob / 10) * weights.rain_weight
    wind_component = wind_penalty(wind_kmh) * weights.wind_weight
    heat_component = heat_penalty(temp_c) * weights.heat_weight
    humidity_component = humidity_penalty(humidity_pct) * weights.humidity_weight

    total = rain_component + wind_component + heat_component + humidity_component
    return min(10, round(total, 1))


def wind_penalty(wind_kmh):
    if wind_kmh is None:
        return 0
    if wind_kmh > 40:
        return 4
    elif wind_kmh > 25:
        return 2
    elif wind_kmh > 15:
        return 1
    return 0


def heat_penalty(temp_c):
    if temp_c > 38:
        return 4
    elif temp_c > 32:
        return 2
    elif temp_c < 5:
        return 3
    elif temp_c < 10:
        return 1
    return 0


def humidity_penalty(humidity_pct):
    if humidity_pct is None:
        return 0
    if humidity_pct > 80:
        return 2
    elif humidity_pct > 60:
        return 1
    return 0


def get_risk_level(score):
    if score <= 3:
        return "low"
    elif score <= 6:
        return "moderate"
    return "high"


def get_recommendation(risk_level, rain_prob, day_context=None):
    if risk_level == "low":
        msg = "Safe to proceed with outdoor plans."
    elif risk_level == "moderate":
        msg = "Some risk present."
        if rain_prob > 40:
            msg += " Consider a backup indoor plan for rain."
    else:
        msg = "High risk — strongly consider rescheduling or indoor backup."

    if day_context and day_context.get("mostly_risky"):
        msg += (
            " Note: most of the day has poor conditions — "
            "this window is a narrow exception. Consider "
            "whether your event duration fits within it."
        )
    return msg


def score_single_hour(temp, rain_prob, wind_kmh, humidity_pct, weights):
    return calculate_risk_score(rain_prob, wind_kmh, temp, humidity_pct, weights)


def find_best_hours(hourly_data, target_date, weights, top_n=3):
    times = hourly_data.get("time", [])
    temps = hourly_data.get("temperature_2m", [])
    rains = hourly_data.get("precipitation_probability", [])
    winds = hourly_data.get("wind_speed_10m", [])
    humidity = hourly_data.get("relative_humidity_2m", [])

    hour_scores = []
    for i, t in enumerate(times):
        if not t.startswith(target_date):
            continue
        hour = int(t.split("T")[1].split(":")[0])
        if hour < 6 or hour > 22:
            continue

        score = score_single_hour(
            temps[i], rains[i], winds[i], humidity[i], weights
        )
        hour_scores.append({
            "hour": hour,
            "risk_score": score,
            "temperature_c": temps[i],
            "rain_probability": rains[i],
            "wind_kmh": winds[i],
        })

    sorted_hours = sorted(hour_scores, key=lambda x: x["risk_score"])
    return sorted_hours[:top_n]


def find_best_window(hourly_data, target_date, weights, duration_hours=EVENT_DURATION_HOURS):
    """
    Har possible starting hour (6 AM - 22-duration) ke liye, us se agle
    'duration_hours' ka AVERAGE score nikalta hai — single hour ka score nahi.
    """
    times = hourly_data.get("time", [])
    temps = hourly_data.get("temperature_2m", [])
    rains = hourly_data.get("precipitation_probability", [])
    winds = hourly_data.get("wind_speed_10m", [])
    humidity = hourly_data.get("relative_humidity_2m", [])

    hourly_scores = []
    for i, t in enumerate(times):
        if not t.startswith(target_date):
            continue
        hour = int(t.split("T")[1].split(":")[0])
        if hour < 6 or hour > 22:
            continue
        score = calculate_risk_score(rains[i], winds[i], temps[i], humidity[i], weights)
        hourly_scores.append({
            "hour": hour, "score": score, "rain": rains[i],
            "temp": temps[i], "wind": winds[i],
        })

    if len(hourly_scores) < duration_hours:
        return None

    windows = []
    for i in range(len(hourly_scores) - duration_hours + 1):
        window_slice = hourly_scores[i:i + duration_hours]
        avg_score = sum(h["score"] for h in window_slice) / duration_hours
        windows.append({
            "start_hour": window_slice[0]["hour"],
            "end_hour": window_slice[-1]["hour"],
            "avg_risk_score": round(avg_score, 1),
            "hours_detail": window_slice,
        })

    windows.sort(key=lambda w: w["avg_risk_score"])
    return windows[0]


def get_day_summary(hourly_scores):
    """Poore din ka honest overview — single best window ka exception nahi."""
    all_scores = [h["score"] for h in hourly_scores]
    if not all_scores:
        return None

    avg = round(sum(all_scores) / len(all_scores), 1)
    risky_count = sum(1 for s in all_scores if s > 6)
    mostly_risky = (risky_count / len(all_scores)) > 0.5

    warning = None
    if mostly_risky:
        warning = (
            f"This day has poor conditions for {risky_count} of "
            f"{len(all_scores)} hours (6 AM-10 PM). Only a narrow "
            f"window is favorable."
        )

    return {
        "day_average_risk": avg,
        "day_worst_risk": max(all_scores),
        "day_best_risk": min(all_scores),
        "mostly_risky": mostly_risky,
        "warning": warning,
    }
