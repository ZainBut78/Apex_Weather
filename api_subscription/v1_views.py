from django.http import JsonResponse
from django.views.decorators.http import require_GET
from .api_auth import require_api_key
from trip_planner.views import build_trip_plan_response
from events.views import build_event_risk_response


@require_GET
@require_api_key(feature="trip_planner")
def v1_trip_plan(request):
    """
    GET /api/v1/trips/plan/?city=paris&start=2026-08-01&end=2026-08-05
    Headers: X-API-Key: wv_live_xxxxx
    """
    city_query = request.GET.get("city", "").strip()
    start = request.GET.get("start", "").strip()
    end = request.GET.get("end", "").strip()

    if not city_query or not start or not end:
        return JsonResponse({"error": "city, start, and end parameters are required"}, status=400)

    result = build_trip_plan_response(city_query, start, end)
    if "error" in result:
        status = result.pop("status", 400)
        return JsonResponse(result, status=status)

    return JsonResponse({"success": True, "data": result})


@require_GET
@require_api_key(feature="events")
def v1_event_risk(request):
    """
    GET /api/v1/events/risk/?city=paris&date=2026-08-05&type=wedding&time=18
    Headers: X-API-Key: wv_live_xxxxx
    """
    city_query = request.GET.get("city", "").strip()
    event_date = request.GET.get("date", "").strip()
    event_type = request.GET.get("type", "general").strip()
    event_time = request.GET.get("time", "").strip()

    if not city_query or not event_date:
        return JsonResponse({"error": "city and date parameters are required"}, status=400)

    result = build_event_risk_response(city_query, event_date, event_type, event_time)
    if "error" in result:
        status = result.pop("status", 400)
        return JsonResponse(result, status=status)

    return JsonResponse({"success": True, "data": result})
