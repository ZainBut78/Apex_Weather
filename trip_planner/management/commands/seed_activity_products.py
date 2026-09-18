from django.core.management.base import BaseCommand
from affiliates.models import AffiliateProduct

PRODUCTS = [
    {"name": "Quick-Dry Beach Towel", "category": "swimwear_sunscreen",
     "affiliate_url": "https://amazon.com/placeholder-1", "image_url": "https://placehold.co/400x400/png?text=Towel",
     "price_display": "$19.99", "priority": 10},
    {"name": "SPF 50 Reef-Safe Sunscreen", "category": "swimwear_sunscreen",
     "affiliate_url": "https://amazon.com/placeholder-2", "image_url": "https://placehold.co/400x400/png?text=Sunscreen",
     "price_display": "$14.99", "priority": 8},
    {"name": "Foldable Picnic Blanket", "category": "picnic_gear",
     "affiliate_url": "https://amazon.com/placeholder-3", "image_url": "https://placehold.co/400x400/png?text=Blanket",
     "price_display": "$22.50", "priority": 10},
    {"name": "Insulated Picnic Backpack", "category": "picnic_gear",
     "affiliate_url": "https://amazon.com/placeholder-4", "image_url": "https://placehold.co/400x400/png?text=Backpack",
     "price_display": "$34.99", "priority": 8},
    {"name": "Lightweight Hiking Daypack", "category": "hiking_gear",
     "affiliate_url": "https://amazon.com/placeholder-5", "image_url": "https://placehold.co/400x400/png?text=Daypack",
     "price_display": "$39.99", "priority": 10},
    {"name": "Trekking Poles (Pair)", "category": "hiking_gear",
     "affiliate_url": "https://amazon.com/placeholder-6", "image_url": "https://placehold.co/400x400/png?text=Poles",
     "price_display": "$45.00", "priority": 8},
    {"name": "Travel Guidebook", "category": "travel_books_umbrella",
     "affiliate_url": "https://amazon.com/placeholder-7", "image_url": "https://placehold.co/400x400/png?text=Guidebook",
     "price_display": "$16.95", "priority": 10},
    {"name": "Compact Travel Umbrella", "category": "travel_umbrella_raincoat",
     "affiliate_url": "https://amazon.com/placeholder-8", "image_url": "https://placehold.co/400x400/png?text=Umbrella",
     "price_display": "$24.99", "priority": 10},
    {"name": "Packable Rain Jacket", "category": "travel_umbrella_raincoat",
     "affiliate_url": "https://amazon.com/placeholder-9", "image_url": "https://placehold.co/400x400/png?text=RainJacket",
     "price_display": "$59.99", "priority": 8},
    {"name": "Wide-Brim Sun Hat", "category": "sun_protection_hats",
     "affiliate_url": "https://amazon.com/placeholder-10", "image_url": "https://placehold.co/400x400/png?text=SunHat",
     "price_display": "$15.99", "priority": 10},
    {"name": "City Travel Essentials Kit", "category": "city_travel_essentials",
     "affiliate_url": "https://amazon.com/placeholder-11", "image_url": "https://placehold.co/400x400/png?text=Essentials",
     "price_display": "$29.99", "priority": 10},
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
                    "image_url": p["image_url"],
                    "price_display": p["price_display"],
                    "priority": p["priority"],
                    "is_active": True,
                }
            )
            if was_created:
                created += 1
        self.stdout.write(self.style.SUCCESS(f"Created {created} products"))
