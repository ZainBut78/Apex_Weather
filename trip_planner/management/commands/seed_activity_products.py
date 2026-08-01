from django.core.management.base import BaseCommand
from affiliates.models import AffiliateProduct

PRODUCTS = [
    {"name": "Quick-Dry Beach Towel", "category": "swimwear_sunscreen",
     "affiliate_url": "https://amazon.com/placeholder-1", "priority": 10},
    {"name": "SPF 50 Reef-Safe Sunscreen", "category": "swimwear_sunscreen",
     "affiliate_url": "https://amazon.com/placeholder-2", "priority": 8},
    {"name": "Foldable Picnic Blanket", "category": "picnic_gear",
     "affiliate_url": "https://amazon.com/placeholder-3", "priority": 10},
    {"name": "Insulated Picnic Backpack", "category": "picnic_gear",
     "affiliate_url": "https://amazon.com/placeholder-4", "priority": 8},
    {"name": "Lightweight Hiking Daypack", "category": "hiking_gear",
     "affiliate_url": "https://amazon.com/placeholder-5", "priority": 10},
    {"name": "Trekking Poles (Pair)", "category": "hiking_gear",
     "affiliate_url": "https://amazon.com/placeholder-6", "priority": 8},
    {"name": "Travel Guidebook", "category": "travel_books_umbrella",
     "affiliate_url": "https://amazon.com/placeholder-7", "priority": 10},
    {"name": "Compact Travel Umbrella", "category": "travel_umbrella_raincoat",
     "affiliate_url": "https://amazon.com/placeholder-8", "priority": 10},
    {"name": "Packable Rain Jacket", "category": "travel_umbrella_raincoat",
     "affiliate_url": "https://amazon.com/placeholder-9", "priority": 8},
    {"name": "Wide-Brim Sun Hat", "category": "sun_protection_hats",
     "affiliate_url": "https://amazon.com/placeholder-10", "priority": 10},
    {"name": "City Travel Essentials Kit", "category": "city_travel_essentials",
     "affiliate_url": "https://amazon.com/placeholder-11", "priority": 10},
]

class Command(BaseCommand):
    help = "Seed affiliate products for daily activity recommendations"

    def handle(self, *args, **kwargs):
        created = 0
        for p in PRODUCTS:
            _, was_created = AffiliateProduct.objects.get_or_create(
                name=p["name"],
                defaults={
                    "category": p["category"],
                    "affiliate_url": p["affiliate_url"],
                    "priority": p["priority"],
                    "is_active": True,
                }
            )
            if was_created:
                created += 1
        self.stdout.write(self.style.SUCCESS(f"Created {created} products"))
