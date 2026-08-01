def generate_narrative(city_name, monthly_data):
    valid_months = [m for m in monthly_data if m["avg_high"] != "-"]
    if not valid_months:
        return f"Climate data for {city_name} is being processed."

    hottest = max(valid_months, key=lambda m: m["avg_high"])
    coldest = min(valid_months, key=lambda m: m["avg_high"])
    wettest = max(valid_months, key=lambda m: m["avg_rainfall"] if m["avg_rainfall"] != "-" else 0)

    return (
        f"{city_name} experiences its warmest weather in {hottest['month_name']}, "
        f"with average highs reaching {hottest['avg_high']}°C. The coolest month "
        f"is typically {coldest['month_name']}, averaging {coldest['avg_high']}°C. "
        f"Rainfall is heaviest in {wettest['month_name']}, with around "
        f"{wettest['avg_rainfall']}mm of precipitation."
    )
