from django.db import models


class EventTypeWeight(models.Model):
    event_type = models.CharField(max_length=50, unique=True)
    rain_weight = models.FloatField(default=1.0)
    wind_weight = models.FloatField(default=1.0)
    heat_weight = models.FloatField(default=1.0)
    humidity_weight = models.FloatField(default=1.0)

    def __str__(self):
        return self.event_type
