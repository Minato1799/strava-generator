from django.http import JsonResponse
from django.views.decorators.http import require_GET

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


@require_GET
def get_generated_strava_gpx(request):
    try:
        points = service.parse_points(request.GET.get("points", ""))
        activity_type = service.validate_activity_type(request.GET.get("activity_type", "run"))
        end_time = service.parse_end_time(request.GET.get("end_time", ""))
        result = service.get_route(points, activity_type)
        generated_gpx = service.generate_gpx(result["points"], activity_type, end_time)
    except service.RequestValidationError as error:
        return _error_response(error, 400)
    except service.ExternalServiceError as error:
        return _error_response(error, 502)
    except ValueError as error:
        return _error_response(error, 400)

    return JsonResponse(
        {
            "code": 200,
            "gpx": generated_gpx,
            "distance": result["distance"],
        }
    )
