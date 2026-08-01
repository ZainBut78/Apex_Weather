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
from api_subscription import v1_views
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView
from weather.views import sitemap_view


def health_check(request):
    return JsonResponse({"status": "ok"})


def robots_txt(request):
    content = """User-agent: *
Allow: /
Disallow: /admin/
Disallow: /api/
Sitemap: https://weatherapex.com/sitemap.xml
"""
    return HttpResponse(content, content_type="text/plain")


urlpatterns = [
    path('health/', health_check),
    path('admin/', admin.site.urls),
    path('api/weather/', include('weather.urls')),
    path('api/trips/plan/', include('trip_planner.urls')),
    path('api/affiliate/', include('affiliates.urls')),
    path('api/events/risk/', include('events.urls')),
    path('api/auth/', include('api_subscription.urls')),
    path('api/v1/trips/plan/', v1_views.v1_trip_plan),
    path('api/v1/events/risk/', v1_views.v1_event_risk),
    path('api/schema/', SpectacularAPIView.as_view(), name='schema'),
    path('api/docs/', SpectacularSwaggerView.as_view(url_name='schema'), name='docs'),
    path('sitemap.xml', sitemap_view, name='sitemap'),
    path('robots.txt', robots_txt, name='robots'),
]
