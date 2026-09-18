"""
URL configuration for weathervibe project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path, include
from django.http import HttpResponse, JsonResponse
from django.conf import settings
from django.conf.urls.static import static
from api_subscription import v1_views
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView
from weather.views import sitemap_view
from .admin_dashboard import dashboard_view

admin.site.site_header = "WeatherApex Admin"
admin.site.site_title = "WeatherApex Admin"
admin.site.index_title = "Site Monitoring & Management"


def health_check(request):
    return JsonResponse({"status": "ok"})


def robots_txt(request):
    # Sitemap URL settings.SITE_URL se — pehle hardcoded tha.
    content = (
        "User-agent: *\n"
        "Allow: /\n"
        "Disallow: /admin/\n"
        "Disallow: /api/\n"
        f"Sitemap: {settings.SITE_URL}/sitemap.xml\n"
    )
    return HttpResponse(content, content_type="text/plain")


urlpatterns = [
    path('health/', health_check),
    path('admin/dashboard/', admin.site.admin_view(dashboard_view), name='admin_dashboard'),
    path('admin/', admin.site.urls),
    path('api/weather/', include('weather.urls')),
    path('api/trips/plan/', include('trip_planner.urls')),
    path('api/affiliate/', include('affiliates.urls')),
    path('api/events/risk/', include('events.urls')),
    path('api/auth/', include('api_subscription.urls')),
    path('api/blog/', include('blog.urls')),
    path('api/v1/trips/plan/', v1_views.v1_trip_plan),
    path('api/v1/events/risk/', v1_views.v1_event_risk),
    path('api/schema/', SpectacularAPIView.as_view(), name='schema'),
    path('api/docs/', SpectacularSwaggerView.as_view(url_name='schema'), name='docs'),
    path('sitemap.xml', sitemap_view, name='sitemap'),
    path('robots.txt', robots_txt, name='robots'),
    path('ckeditor/', include('ckeditor_uploader.urls')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
