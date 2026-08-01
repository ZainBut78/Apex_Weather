from django.core.management.base import BaseCommand
from affiliates.models import AffiliateProduct, AffiliateRule


class Command(BaseCommand):
    help = "Seed affiliate rules and products"

    def handle(self, *args, **options):
        rules = [
            {
                "name": "Heavy Rain",
                "condition_field": "rain_probability",
                "operator": "gt",
                "threshold": 60,
                "category": "rain_gear",
                "reason_template": "Rain expected on {match_count} of {total_days} days",
            },
            {
                "name": "High Heat",
                "condition_field": "temp_max",
                "operator": "gt",
                "threshold": 30,
                "category": "sun_protection",
                "reason_template": "High temperatures on {match_count} of {total_days} days",
            },
            {
                "name": "Cold Weather",
                "condition_field": "temp_min",
                "operator": "lt",
                "threshold": 10,
                "category": "cold_weather",
                "reason_template": "Cool temperatures expected on {match_count} of {total_days} days",
            },
            {
                "name": "Strong Wind",
                "condition_field": "wind_kmh",
                "operator": "gt",
                "threshold": 25,
                "category": "wind_protection",
                "reason_template": "Strong winds on {match_count} of {total_days} days",
            },
        ]

        products = [
            {
                "name": "Compact Travel Umbrella",
                "category": "rain_gear",
                "affiliate_url": "https://amazon.com/dp/B000BN41CS",
                "priority": 10,
            },
            {
                "name": "SPF 50 Sunscreen",
                "category": "sun_protection",
                "affiliate_url": "https://amazon.com/dp/B001ECSG7Y",
                "priority": 10,
            },
            {
                "name": "Lightweight Travel Jacket",
                "category": "cold_weather",
                "affiliate_url": "https://amazon.com/dp/B07ABC1234",
                "priority": 10,
            },
            {
                "name": "Windproof Fleece Scarf",
                "category": "wind_protection",
                "affiliate_url": "https://amazon.com/dp/B08DEF5678",
                "priority": 10,
            },
        ]

        created_rules = 0
        for r in rules:
            _, created = AffiliateRule.objects.get_or_create(
                name=r["name"], defaults=r
            )
            if created:
                created_rules += 1

        created_products = 0
        for p in products:
            _, created = AffiliateProduct.objects.get_or_create(
                name=p["name"], defaults=p
            )
            if created:
                created_products += 1

        self.stdout.write(self.style.SUCCESS(
            f"Seeded: {created_rules} rules, {created_products} products"
        ))
