from django.db import models


class City(models.Model):
    REGION_CHOICES = [
        ("europe", "Europe"),
        ("usa", "USA"),
        ("other", "Other"),
    ]

    name = models.CharField(max_length=100)
    slug = models.SlugField(max_length=100, unique=True, db_index=True)
    country = models.CharField(max_length=100)
    region = models.CharField(max_length=20, choices=REGION_CHOICES, default="other")
    latitude = models.FloatField()
    longitude = models.FloatField()
    is_coastal = models.BooleanField(default=False)
    has_hiking_trails = models.BooleanField(default=False)
    image_url = models.URLField(blank=True, null=True)

    def __str__(self):
        return f"{self.name}, {self.country}"


class HistoricalWeather(models.Model):
    city = models.ForeignKey(City, on_delete=models.CASCADE, related_name="historical_data")
    year = models.IntegerField(default=0)
    month = models.IntegerField()
    avg_temp_max = models.FloatField()
    avg_temp_min = models.FloatField()
    avg_rainfall = models.FloatField()
    rainy_days = models.IntegerField()
    sunshine_hours = models.FloatField()
    avg_humidity = models.FloatField()

    class Meta:
        unique_together = ("city", "year", "month")

    def __str__(self):
        return f"{self.city.name} - {self.year}/{self.month}"


class ServiceRequestLog(models.Model):
    FEATURE_CHOICES = [
        ("weather", "Weather"),
        ("trip_planner", "Trip Planner"),
        ("event_risk", "Event Risk"),
        ("other", "Other"),
    ]
    SOURCE_CHOICES = [
        ("cache", "Cache (memory)"),
        ("database", "Database"),
        ("external", "Open-Meteo API"),
    ]
    feature = models.CharField(max_length=20, choices=FEATURE_CHOICES)
    data_source = models.CharField(max_length=20, choices=SOURCE_CHOICES)
    city_query = models.CharField(max_length=100, blank=True)
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-timestamp"]
        indexes = [
            models.Index(fields=["timestamp"]),
            models.Index(fields=["feature", "data_source", "timestamp"]),
        ]

    def __str__(self):
        return f"{self.get_feature_display()} | {self.get_data_source_display()} | {self.timestamp:%Y-%m-%d %H:%M}"


class ExternalAPICallLog(models.Model):
    API_TYPES = [
        ("forecast", "Live Forecast"),
        ("archive", "Historical Archive"),
        ("geocoding", "Geocoding"),
        # services.py `log_external_call("images", ...)` likhta tha magar
        # yeh choice list mein nahi tha — admin filter mein Pexels calls
        # dikhti hi nahi thi.
        ("images", "City Images (Pexels)"),
    ]
    api_type = models.CharField(max_length=20, choices=API_TYPES)
    city_query = models.CharField(max_length=100, blank=True)
    success = models.BooleanField(default=True)
    status_code = models.IntegerField(null=True)
    timestamp = models.DateTimeField(auto_now_add=True)
    feature = models.CharField(max_length=20, choices=ServiceRequestLog.FEATURE_CHOICES, default="other")

    class Meta:
        ordering = ["-timestamp"]
        indexes = [
            models.Index(fields=["timestamp"]),
            models.Index(fields=["api_type", "timestamp"]),
            models.Index(fields=["feature", "timestamp"]),
        ]

    def __str__(self):
        return f"{self.get_api_type_display()} | {self.city_query or '-'} | {self.status_code} | {self.timestamp:%Y-%m-%d %H:%M}"
