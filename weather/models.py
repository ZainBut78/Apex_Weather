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
