from django.contrib import admin

from .models import City, HistoricalWeather, ExternalAPICallLog, ServiceRequestLog


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


@admin.register(ExternalAPICallLog)
class ExternalAPICallLogAdmin(admin.ModelAdmin):
    list_display = ("api_type", "feature", "city_query", "success", "status_code", "timestamp")
    list_filter = ("api_type", "feature", "success")
    search_fields = ("city_query",)
    date_hierarchy = "timestamp"


@admin.register(ServiceRequestLog)
class ServiceRequestLogAdmin(admin.ModelAdmin):
    list_display = ("feature", "data_source", "city_query", "timestamp")
    list_filter = ("feature", "data_source")
    search_fields = ("city_query",)
    date_hierarchy = "timestamp"
