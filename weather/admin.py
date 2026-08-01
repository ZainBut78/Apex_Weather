from django.contrib import admin

from .models import City, HistoricalWeather


@admin.register(City)
class CityAdmin(admin.ModelAdmin):
    list_display = ("name", "country", "region", "latitude", "longitude")
    list_filter = ("region", "country")
    search_fields = ("name", "country")
    prepopulated_fields = {"slug": ("name",)}


@admin.register(HistoricalWeather)
class HistoricalWeatherAdmin(admin.ModelAdmin):
    list_display = ("city", "year", "month", "avg_temp_max", "avg_temp_min", "rainy_days")
    list_filter = ("year", "month")
    search_fields = ("city__name",)
