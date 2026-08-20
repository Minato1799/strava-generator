import json

from django.core.exceptions import RequestDataTooBig
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from ... import service


class UnsupportedMediaTypeError(service.RequestValidationError):
    pass


class RequestBodyTooLargeError(service.RequestValidationError):
    pass


def _error_response(message, status):
    response = JsonResponse({"code": status, "error": message}, status=status)
    response["Cache-Control"] = "private, no-store"
    return response


def _json_payload(request):
    if request.content_type != "application/json":
        raise UnsupportedMediaTypeError("Content-Type must be application/json")
    try:
        payload = json.loads(request.body or b"{}")
    except RequestDataTooBig:
        raise RequestBodyTooLargeError("Request body is too large") from None
    except (RecursionError, UnicodeDecodeError, ValueError):
        raise service.RequestValidationError("Request body must be valid JSON") from None
    if not isinstance(payload, dict):
        raise service.RequestValidationError("Request body must be a JSON object")
    return payload


def _success_response(payload):
    response = JsonResponse(payload)
    response["Cache-Control"] = "private, no-store"
    return response


def _validation_error_response(error, default_message):
    if isinstance(error, UnsupportedMediaTypeError):
        status = 415
        message = "Content-Type must be application/json"
    elif isinstance(error, RequestBodyTooLargeError):
        status = 413
        message = "Request body is too large"
    else:
        status = 400
        message = default_message
    return _error_response(message, status)


@csrf_exempt
@require_POST
def route(request):
    try:
        payload = _json_payload(request)
        points = service.parse_points(payload.get("points", ""))
        activity_type = service.validate_activity_type(payload.get("activity_type", "run"))
        result = service.get_route(points, activity_type)
    except service.RequestValidationError as error:
        return _validation_error_response(error, "The route request is invalid")
    except service.ExternalServiceError:
        return _error_response("The routing service is temporarily unavailable", 502)

    return _success_response(
        {
            "code": 200,
            "route": result["points"],
            "distance": result["distance"],
            "duration": result["duration"],
        }
    )


@csrf_exempt
@require_POST
def search_location(request):
    try:
        payload = _json_payload(request)
        results = service.search_locations(payload.get("query", ""))
    except service.RequestValidationError as error:
        return _validation_error_response(error, "The search request is invalid")
    except service.ExternalServiceError:
        return _error_response("Location search is temporarily unavailable", 502)
    return _success_response({"code": 200, "results": results})


@csrf_exempt
@require_POST
def get_generated_strava_gpx(request):
    try:
        payload = _json_payload(request)
        route_points = service.parse_track_points(payload.get("route_points"))
        route_distance = service.parse_route_distance(payload.get("route_distance"))
        activity_type = service.validate_activity_type(payload.get("activity_type", "run"))
        activity_name = service.parse_activity_name(payload.get("activity_name"), activity_type)
        end_time = service.parse_end_time(payload.get("end_time", ""))
        pace_seconds_per_km = service.parse_pace(payload.get("pace", ""), activity_type)
        generated = service.generate_gpx(
            route_points,
            activity_type,
            end_time,
            pace_seconds_per_km,
            route_distance,
            activity_name,
        )
    except service.RequestValidationError as error:
        return _validation_error_response(error, "The GPX request is invalid")
    except ValueError:
        return _error_response("The GPX request is invalid", 400)

    return _success_response(
        {
            "code": 200,
            "gpx": generated["gpx"],
            "distance": route_distance,
            "pace_seconds_per_km": pace_seconds_per_km,
            "duration_seconds": generated["duration_seconds"],
            "start_time": generated["start_time"].isoformat().replace("+00:00", "Z"),
        }
    )
