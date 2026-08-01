from django.core.management.base import BaseCommand
from events.models import EventTypeWeight


WEIGHTS = [
    {"event_type": "wedding", "rain_weight": 1.5, "wind_weight": 1.0,
     "heat_weight": 0.8, "humidity_weight": 0.6},
    {"event_type": "marathon", "rain_weight": 0.7, "wind_weight": 0.8,
     "heat_weight": 1.6, "humidity_weight": 1.4},
    {"event_type": "concert", "rain_weight": 1.0, "wind_weight": 1.5,
     "heat_weight": 0.8, "humidity_weight": 0.6},
    {"event_type": "sports", "rain_weight": 1.2, "wind_weight": 1.0,
     "heat_weight": 1.0, "humidity_weight": 0.8},
]


class Command(BaseCommand):
    help = "Seed event type weights"

    def handle(self, *args, **kwargs):
        for w in WEIGHTS:
            EventTypeWeight.objects.update_or_create(
                event_type=w["event_type"], defaults=w
            )
        self.stdout.write(self.style.SUCCESS("Event weights seeded"))
