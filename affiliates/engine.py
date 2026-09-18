import logging

from .models import AffiliateRule, AffiliateProduct

logger = logging.getLogger(__name__)

OPERATORS = {
    "gt": lambda val, threshold: val > threshold,
    "lt": lambda val, threshold: val < threshold,
    "gte": lambda val, threshold: val >= threshold,
    "lte": lambda val, threshold: val <= threshold,
}


def evaluate_rules_against_trip(days):
    rules = AffiliateRule.objects.filter(is_active=True)
    category_matches = {}

    for rule in rules:
        op_func = OPERATORS.get(rule.operator)
        if not op_func:
            continue

        matched_days = 0
        severity_sum = 0

        for day in days:
            value = day.get(rule.condition_field)
            if value is None:
                continue
            if op_func(value, rule.threshold):
                matched_days += 1
                severity_sum += abs(value - rule.threshold)

        if matched_days > 0:
            existing = category_matches.get(rule.category)
            if not existing or matched_days > existing["match_count"]:
                category_matches[rule.category] = {
                    "match_count": matched_days,
                    "severity": severity_sum,
                    "rule": rule,
                }

    sorted_categories = sorted(
        category_matches.items(),
        key=lambda x: (x[1]["match_count"], x[1]["severity"]),
        reverse=True
    )
    return sorted_categories


def get_products_by_category(category, max_items=2):
    products = (
        AffiliateProduct.objects
        .filter(category=category, is_active=True)
        .order_by("-priority")[:max_items]
    )
    return [
        {
            "name": p.name,
            "category": p.category,
            "affiliate_url": p.affiliate_url,
            "image_url": p.image_url,
            "price_display": p.price_display,
            "product_id": p.id,
        }
        for p in products
    ]


def get_products_by_categories(categories, max_items=2):
    """Kai categories ke products EK query mein.

    Pehle trip-planner ke per-day loop ke andar get_products_by_category()
    call hota tha — 20-din ke trip pe 20 alag DB queries. Ab saari
    categories ek `category__in` query se aati hain.
    Return shape har category ke liye get_products_by_category() jaisa hi hai.
    """
    categories = list(dict.fromkeys(categories))
    if not categories:
        return {}

    grouped = {c: [] for c in categories}
    products = (
        AffiliateProduct.objects
        .filter(category__in=categories, is_active=True)
        .order_by("category", "-priority", "id")
    )
    for p in products:
        bucket = grouped.get(p.category)
        if bucket is None or len(bucket) >= max_items:
            continue
        bucket.append({
            "name": p.name,
            "category": p.category,
            "affiliate_url": p.affiliate_url,
            "image_url": p.image_url,
            "price_display": p.price_display,
            "product_id": p.id,
        })
    return grouped


def get_product_recommendations(days, max_items=3):
    total_days = len(days)
    matched_categories = evaluate_rules_against_trip(days)

    recommendations = []
    for category, data in matched_categories[:max_items]:
        product = (
            AffiliateProduct.objects
            .filter(category=category, is_active=True)
            .order_by("-priority")
            .first()
        )
        if not product:
            continue

        # reason_template admin se editable hai. Agar usme koi unknown
        # placeholder ho ({foo}) to .format() KeyError deta tha aur poora
        # trip-planner response 500 ho jata tha.
        try:
            reason = data["rule"].reason_template.format(
                match_count=data["match_count"],
                total_days=total_days
            )
        except (KeyError, IndexError, ValueError):
            logger.warning(
                "AffiliateRule id=%s ka reason_template invalid hai: %r",
                data["rule"].id, data["rule"].reason_template,
            )
            reason = f"Recommended for {data['match_count']} of {total_days} days"

        recommendations.append({
            "item": product.name,
            "reason": reason,
            "affiliate_url": product.affiliate_url,
            "image_url": product.image_url,
            "price_display": product.price_display,
            "affiliate_product_id": product.id,
            "match_count": data["match_count"],
            "total_days": total_days,
        })

    return recommendations


def get_default_packing_recommendations(days, max_items=3):
    """Rule match na ho to bhi hamesha kuch useful recommend karo —
    taake frontend par 'Packing Recommendations' section kabhi khaali na rahe."""
    total_days = len(days)
    if not days:
        return []

    avg_max = sum((d.get("temp_max") or 0) for d in days) / total_days
    avg_min = sum((d.get("temp_min") or 0) for d in days) / total_days
    max_wind = max((d.get("wind_kmh") or 0) for d in days)

    wanted = []
    rainy_days = sum(1 for d in days if (d.get("rain_probability") or 0) >= 30)
    if rainy_days:
        wanted.append(("rain_gear", f"Light rain possible on {rainy_days} of {total_days} days"))
    if avg_max >= 27:
        wanted.append(("sun_protection", f"Warm conditions with highs around {round(avg_max)}°C"))
    if avg_min <= 12:
        wanted.append(("travel_umbrella_raincoat", f"Cool and chilly conditions — pack a rain jacket for your {total_days}-day trip"))
    if max_wind is not None and max_wind >= 20:
        wanted.append(("wind_protection", f"Breezy with gusts up to {round(max_wind)} km/h"))

    if not wanted:
        wanted = [
            ("city_travel_essentials", f"Recommended essentials for your {total_days}-day trip"),
            ("sun_protection", f"Mild sunny days — pack light sunscreen for your {total_days}-day trip"),
        ]

    recommendations = []
    for category, reason in wanted:
        product = (
            AffiliateProduct.objects
            .filter(category=category, is_active=True)
            .order_by("-priority")
            .first()
        )
        if not product:
            continue
        recommendations.append({
            "item": product.name,
            "reason": reason,
            "affiliate_url": product.affiliate_url,
            "image_url": product.image_url,
            "price_display": product.price_display,
            "affiliate_product_id": product.id,
        })
        if len(recommendations) >= max_items:
            break

    return recommendations
