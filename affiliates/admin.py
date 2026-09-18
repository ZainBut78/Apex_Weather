from django.contrib import admin
from .models import AffiliateProduct, AffiliateRule, AffiliateClick


@admin.register(AffiliateProduct)
class AffiliateProductAdmin(admin.ModelAdmin):
    list_display = ("name", "category", "price_display", "is_active", "priority")
    list_filter = ("category", "is_active")
    search_fields = ("name",)


@admin.register(AffiliateRule)
class AffiliateRuleAdmin(admin.ModelAdmin):
    list_display = ("name", "condition_field", "operator", "threshold", "category", "is_active")
    list_filter = ("condition_field", "category", "is_active")
    search_fields = ("name", "category")


@admin.register(AffiliateClick)
class AffiliateClickAdmin(admin.ModelAdmin):
    list_display = ("product", "source_feature", "timestamp")
    list_filter = ("source_feature", "timestamp")
    search_fields = ("product__name",)
