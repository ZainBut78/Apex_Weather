"""SITE_URL ko har template mein available karna.

Is se canonical tags / absolute links templates mein hardcode nahi karne
parte — bas {{ SITE_URL }} likho.
"""
from django.conf import settings


def site(request):
    return {
        "SITE_URL": settings.SITE_URL,
        "SITE_HOST": settings.SITE_HOST,
    }
