from .models import AffiliateRule, AffiliateProduct

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
        {"name": p.name, "category": p.category, "affiliate_url": p.affiliate_url, "product_id": p.id}
        for p in products
    ]


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

        reason = data["rule"].reason_template.format(
            match_count=data["match_count"],
            total_days=total_days
        )

        recommendations.append({
            "item": product.name,
            "reason": reason,
            "affiliate_product_id": product.id,
            "match_count": data["match_count"],
            "total_days": total_days,
        })

    return recommendations
