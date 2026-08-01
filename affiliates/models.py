from django.db import models


class AffiliateProduct(models.Model):
    name = models.CharField(max_length=150)
    category = models.CharField(max_length=50)
    affiliate_url = models.URLField()
    priority = models.IntegerField(default=0)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.name} ({self.category})"


class AffiliateRule(models.Model):
    FIELD_CHOICES = [
        ("rain_probability", "Rain Probability"),
        ("temp_max", "Max Temperature"),
        ("temp_min", "Min Temperature"),
        ("wind_kmh", "Wind Speed"),
    ]
    OPERATOR_CHOICES = [
        ("gt", "Greater Than"),
        ("lt", "Less Than"),
        ("gte", "Greater Than or Equal"),
        ("lte", "Less Than or Equal"),
    ]

    name = models.CharField(max_length=100)
    condition_field = models.CharField(max_length=30, choices=FIELD_CHOICES)
    operator = models.CharField(max_length=5, choices=OPERATOR_CHOICES)
    threshold = models.FloatField()
    category = models.CharField(max_length=50)
    reason_template = models.CharField(max_length=200)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return self.name


class AffiliateClick(models.Model):
    product = models.ForeignKey(AffiliateProduct, on_delete=models.CASCADE)
    source_feature = models.CharField(max_length=50)
    timestamp = models.DateTimeField(auto_now_add=True)
