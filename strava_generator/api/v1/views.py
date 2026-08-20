import json

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

from ... import service


def _error_response(error, status):
    return JsonResponse({"code": status, "error": str(error)}, status=status)


@require_GET
def route(request):
    try:
        points = service.parse_points(request.GET.get("points", ""))
        activity_type = service.validate_activity_type(request.GET.get("activity_type", "run"))
        result = service.get_route(points, activity_type)
    except service.RequestValidationError as error:
        return _error_response(error, 400)
    except service.ExternalServiceError as error:
        return _error_response(error, 502)

    return JsonResponse(
        {
            "code": 200,
            "route": result["points"],
            "distance": result["distance"],
            "duration": result["duration"],
        }
    )


@require_GET
def search_location(request):
    try:
        results = service.search_locations(request.GET.get("q", ""))
    except service.RequestValidationError as error:
        return _error_response(error, 400)
    except service.ExternalServiceError as error:
        return _error_response(error, 502)
    return JsonResponse({"code": 200, "results": results})


@csrf_exempt
@require_POST
def get_generated_strava_gpx(request):
    if request.content_type != "application/json":
        return _error_response(
            service.RequestValidationError("Content-Type must be application/json"),
            415,
        )
    try:
        payload = json.loads(request.body or b"{}")
        if not isinstance(payload, dict):
            raise service.RequestValidationError("Request body must be a JSON object")
        route_points = service.parse_track_points(payload.get("route_points"))
        route_distance = service.parse_route_distance(payload.get("route_distance"))
        activity_type = service.validate_activity_type(payload.get("activity_type", "run"))
        end_time = service.parse_end_time(payload.get("end_time", ""))
        pace_seconds_per_km = service.parse_pace(payload.get("pace", ""), activity_type)
        generated = service.generate_gpx(
            route_points,
            activity_type,
            end_time,
            pace_seconds_per_km,
            route_distance,
        )
    except (json.JSONDecodeError, UnicodeDecodeError):
        return _error_response(service.RequestValidationError("Request body must be valid JSON"), 400)
    except service.RequestValidationError as error:
        return _error_response(error, 400)
    except ValueError as error:
        return _error_response(error, 400)

    response = JsonResponse(
        {
            "code": 200,
            "gpx": generated["gpx"],
            "distance": route_distance,
            "pace_seconds_per_km": pace_seconds_per_km,
            "duration_seconds": generated["duration_seconds"],
            "start_time": generated["start_time"].isoformat().replace("+00:00", "Z"),
        }
    )
    response["Cache-Control"] = "private, no-store"
    return response
