from datetime import timedelta

from django.contrib.auth.models import User
from django.db.models import Count, Sum
from django.shortcuts import render
from django.utils import timezone

from api_subscription.models import APIKey, APIRequestLog, FreeUsage
from weather.models import City, ExternalAPICallLog, ServiceRequestLog


def dashboard_view(request):
    today = timezone.now().date()
    week_ago = today - timedelta(days=7)

    om_today = ExternalAPICallLog.objects.filter(timestamp__date=today)
    om_week = ExternalAPICallLog.objects.filter(timestamp__date__gte=week_ago)
    om_success_today = om_today.filter(success=True).count()
    om_total_today = om_today.count()

    b2b_today = APIRequestLog.objects.filter(timestamp__date=today).count()
    b2b_week = APIRequestLog.objects.filter(timestamp__date__gte=week_ago).count()

    free_today = FreeUsage.objects.filter(date=today).aggregate(total=Sum("count"))["total"] or 0
    free_week = FreeUsage.objects.filter(date__gte=week_ago).aggregate(total=Sum("count"))["total"] or 0

    # Pehle yeh loop har feature ke liye 4 COUNT queries chalata tha
    # (4 features = 16 queries). Ab 4 GROUP BY queries se sab aa jata hai.
    def _by_feature(qs):
        return {row["feature"]: row["n"]
                for row in qs.values("feature").annotate(n=Count("id"))}

    svc_today = _by_feature(ServiceRequestLog.objects.filter(
        data_source__in=["cache", "database"], timestamp__date=today))
    svc_week = _by_feature(ServiceRequestLog.objects.filter(
        data_source__in=["cache", "database"], timestamp__date__gte=week_ago))
    ext_today_by_feature = _by_feature(
        ExternalAPICallLog.objects.filter(timestamp__date=today))
    ext_week_by_feature = _by_feature(
        ExternalAPICallLog.objects.filter(timestamp__date__gte=week_ago))

    feature_rows = [{
        "label": label,
        "key": feature,
        "cache_db_today": svc_today.get(feature, 0),
        "cache_db_week": svc_week.get(feature, 0),
        "external_today": ext_today_by_feature.get(feature, 0),
        "external_week": ext_week_by_feature.get(feature, 0),
    } for feature, label in ServiceRequestLog.FEATURE_CHOICES]

    served_today = ServiceRequestLog.objects.filter(
        data_source__in=["cache", "database"], timestamp__date=today
    ).count()

    context = {
        "total_users": User.objects.count(),
        "new_users_week": User.objects.filter(date_joined__date__gte=week_ago).count(),
        "city_count": City.objects.count(),
        "active_api_keys": APIKey.objects.filter(is_active=True).count(),
        "openmeteo_calls_today": om_total_today,
        "openmeteo_calls_week": om_week.count(),
        "openmeteo_success_rate": round(om_success_today / om_total_today * 100) if om_total_today else 0,
        "cache_db_served_today": served_today,
        "backend_b2b_calls_today": b2b_today,
        "backend_b2b_calls_week": b2b_week,
        "website_free_calls_today": free_today,
        "website_free_calls_week": free_week,
        "feature_rows": feature_rows,
        "recent_external_calls": ExternalAPICallLog.objects.all()[:12],
        "recent_b2b_calls": APIRequestLog.objects.select_related("api_key").all()[:12],
    }
    return render(request, "admin/dashboard.html", context)
