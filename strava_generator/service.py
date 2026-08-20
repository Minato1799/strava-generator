"""Stateless routing and geocoding helpers used by the public API."""

import logging
import math
import os
import re
from datetime import datetime, timedelta, timezone

import requests

from mylibs.gpxgen import GpxGen

logger = logging.getLogger("strava_generator")

MAX_ROUTE_POINTS = 26
MAX_TRACK_POINTS = 10_000
MAX_TOTAL_DISTANCE_METERS = 50_000
DISTANCE_RELATIVE_TOLERANCE = 0.05
DISTANCE_ABSOLUTE_TOLERANCE_METERS = 25
ROUTING_BASE_URLS = {
    "run": os.getenv(
        "ROUTING_FOOT_BASE_URL",
        "https://routing.openstreetmap.de/routed-foot/route/v1/driving",
    ),
    "bike": os.getenv(
        "ROUTING_BIKE_BASE_URL",
        "https://routing.openstreetmap.de/routed-bike/route/v1/driving",
    ),
}
SEARCH_URL = "https://nominatim.openstreetmap.org/search"
REQUEST_HEADERS = {
    "User-Agent": "StravaGeneratorVercel/2.0 (+https://github.com/Minato1799/strava-generator)",
    "Referer": "https://strava-generator-opal.vercel.app/",
}
PACE_LIMITS_SECONDS = {"run": (120.0, 1800.0), "bike": (30.0, 1200.0)}


class RequestValidationError(ValueError):
    pass


class ExternalServiceError(RuntimeError):
    pass


def _log_provider_failure(provider, error):
    response = getattr(error, "response", None)
    status_code = getattr(response, "status_code", "unknown")
    logger.warning(
        "%s provider request failed (error=%s, status=%s)",
        provider,
        type(error).__name__,
        status_code,
    )


def parse_points(raw_points):
    if not isinstance(raw_points, str) or not raw_points:
        raise RequestValidationError("Add at least two route points")

    point_strings = raw_points.split("|")
    if len(point_strings) < 2:
        raise RequestValidationError("Add at least two route points")
    if len(point_strings) > MAX_ROUTE_POINTS:
        raise RequestValidationError(f"A route can contain at most {MAX_ROUTE_POINTS} points")

    points = []
    for raw_point in point_strings:
        try:
            latitude, longitude = (float(value.strip()) for value in raw_point.split(",", 1))
        except (TypeError, ValueError):
            raise RequestValidationError(f"Invalid route point: {raw_point}") from None

        if not math.isfinite(latitude) or not math.isfinite(longitude):
            raise RequestValidationError(f"Invalid route point: {raw_point}")
        if not -90 <= latitude <= 90 or not -180 <= longitude <= 180:
            raise RequestValidationError(f"Route point is outside valid map bounds: {raw_point}")
        points.append((latitude, longitude))

    return points


def parse_track_points(raw_points):
    if not isinstance(raw_points, list) or len(raw_points) < 2:
        raise RequestValidationError("Generated track must contain at least two points")
    if len(raw_points) > MAX_TRACK_POINTS:
        raise RequestValidationError(f"Generated track cannot exceed {MAX_TRACK_POINTS} points")

    points = []
    for raw_point in raw_points:
        if not isinstance(raw_point, (list, tuple)) or len(raw_point) != 2:
            raise RequestValidationError("Generated track contains an invalid point")
        try:
            latitude, longitude = (float(value) for value in raw_point)
        except (TypeError, ValueError):
            raise RequestValidationError("Generated track contains an invalid point") from None
        if not math.isfinite(latitude) or not math.isfinite(longitude):
            raise RequestValidationError("Generated track contains an invalid point")
        if not -90 <= latitude <= 90 or not -180 <= longitude <= 180:
            raise RequestValidationError("Generated track contains a point outside valid map bounds")
        points.append((latitude, longitude))
    return points


def _segment_distance_meters(point_a, point_b):
    latitude_a, longitude_a = (math.radians(value) for value in point_a)
    latitude_b, longitude_b = (math.radians(value) for value in point_b)
    latitude_delta = latitude_b - latitude_a
    longitude_delta = longitude_b - longitude_a
    haversine = (
        math.sin(latitude_delta / 2) ** 2
        + math.cos(latitude_a)
        * math.cos(latitude_b)
        * math.sin(longitude_delta / 2) ** 2
    )
    return 2 * 6_371_008.8 * math.asin(math.sqrt(haversine))


def track_distance_meters(points):
    return sum(
        _segment_distance_meters(points[index - 1], points[index])
        for index in range(1, len(points))
    )


def deduplicate_track_points(points):
    unique_points = []
    for point in points:
        if not unique_points or point != unique_points[-1]:
            unique_points.append(point)
    if len(unique_points) < 2:
        raise RequestValidationError("Generated track must contain at least two unique points")
    return unique_points


def validate_track_distance(points, reported_distance):
    geometry_distance = track_distance_meters(points)
    if not math.isfinite(geometry_distance) or not 0 < geometry_distance <= MAX_TOTAL_DISTANCE_METERS:
        raise RequestValidationError(
            f"Route geometry must cover more than zero and at most {MAX_TOTAL_DISTANCE_METERS / 1000:.0f} km"
        )
    tolerance = max(
        DISTANCE_ABSOLUTE_TOLERANCE_METERS,
        max(geometry_distance, reported_distance) * DISTANCE_RELATIVE_TOLERANCE,
    )
    if abs(geometry_distance - reported_distance) > tolerance:
        raise RequestValidationError("Route geometry does not match its reported distance")
    return geometry_distance


def parse_route_distance(raw_distance):
    try:
        distance = float(raw_distance)
    except (TypeError, ValueError):
        raise RequestValidationError("Route distance must be a number") from None
    if not math.isfinite(distance) or not 0 < distance <= MAX_TOTAL_DISTANCE_METERS:
        raise RequestValidationError(
            f"Route distance must be greater than zero and at most {MAX_TOTAL_DISTANCE_METERS / 1000:.0f} km"
        )
    return distance


def validate_activity_type(activity_type):
    if activity_type in (None, ""):
        return "run"
    if not isinstance(activity_type, str):
        raise RequestValidationError("Activity type must be run or bike")
    activity_type = activity_type.strip().lower()
    if activity_type not in {"run", "bike"}:
        raise RequestValidationError("Activity type must be run or bike")
    return activity_type


def parse_pace(raw_pace, activity_type):
    activity_type = validate_activity_type(activity_type)
    raw_pace = str(raw_pace or "").strip()
    if not raw_pace:
        raise RequestValidationError("Enter an average pace in min/km, for example 5:30")

    match = re.fullmatch(r"(\d{1,2}):([0-5]\d)", raw_pace)
    if not match:
        raise RequestValidationError("Pace must use min/km format, for example 5:30")
    pace_seconds = float(int(match.group(1)) * 60 + int(match.group(2)))

    minimum, maximum = PACE_LIMITS_SECONDS[activity_type]
    if not math.isfinite(pace_seconds) or not minimum <= pace_seconds <= maximum:
        minimum_text = f"{int(minimum // 60)}:{int(minimum % 60):02d}"
        maximum_text = f"{int(maximum // 60)}:{int(maximum % 60):02d}"
        raise RequestValidationError(
            f"Pace must be between {minimum_text} and {maximum_text} min/km for {activity_type}"
        )
    return pace_seconds


def parse_end_time(raw_end_time):
    if raw_end_time in (None, ""):
        return datetime.now(timezone.utc)
    if not isinstance(raw_end_time, str):
        raise RequestValidationError("Finish time must be a valid ISO date and time")

    try:
        parsed = datetime.fromisoformat(raw_end_time.replace("Z", "+00:00"))
    except ValueError:
        raise RequestValidationError("Finish time must be a valid ISO date and time") from None

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    else:
        parsed = parsed.astimezone(timezone.utc)

    if parsed.timestamp() > datetime.now(timezone.utc).timestamp() + 60:
        raise RequestValidationError("Finish time cannot be in the future")
    return parsed


def get_route(points, activity_type):
    activity_type = validate_activity_type(activity_type)
    waypoint_distance = track_distance_meters(points)
    if waypoint_distance <= 0:
        raise RequestValidationError("Route points must not all be identical")
    if waypoint_distance > MAX_TOTAL_DISTANCE_METERS:
        raise RequestValidationError(
            f"Route distance cannot exceed {MAX_TOTAL_DISTANCE_METERS / 1000:.0f} km"
        )
    coordinates = ";".join(f"{longitude:.7f},{latitude:.7f}" for latitude, longitude in points)
    url = f"{ROUTING_BASE_URLS[activity_type].rstrip('/')}/{coordinates}"

    try:
        response = requests.get(
            url,
            params={
                "overview": "full",
                "geometries": "geojson",
                "steps": "false",
                "generate_hints": "false",
            },
            headers=REQUEST_HEADERS,
            timeout=15,
        )
        response.raise_for_status()
        payload = response.json()
    except (requests.RequestException, ValueError) as error:
        _log_provider_failure("Routing", error)
        raise ExternalServiceError("The routing service is temporarily unavailable") from error

    if not isinstance(payload, dict):
        raise ExternalServiceError("The routing service returned an invalid response")

    routes = payload.get("routes") or []
    if payload.get("code") != "Ok" or not routes:
        raise RequestValidationError("A route could not be built for these points")
    if not isinstance(routes, list):
        raise ExternalServiceError("The routing service returned an invalid response")

    route = routes[0]
    try:
        distance = float(route.get("distance", 0))
        duration = float(route.get("duration", 0))
    except (AttributeError, TypeError, ValueError) as error:
        raise ExternalServiceError("The routing service returned an invalid response") from error
    if not math.isfinite(distance) or distance <= 0:
        raise ExternalServiceError("The routing service returned an invalid distance")
    if not math.isfinite(duration) or duration < 0:
        raise ExternalServiceError("The routing service returned an invalid duration")
    if distance > MAX_TOTAL_DISTANCE_METERS:
        raise RequestValidationError(
            f"Route distance cannot exceed {MAX_TOTAL_DISTANCE_METERS / 1000:.0f} km"
        )

    try:
        geometry = route.get("geometry", {}).get("coordinates") or []
        route_points = parse_track_points(
            [[coordinate[1], coordinate[0]] for coordinate in geometry]
        )
        validate_track_distance(route_points, distance)
    except (AttributeError, IndexError, TypeError, RequestValidationError) as error:
        raise ExternalServiceError("The routing service returned an invalid route") from error

    return {
        "points": route_points,
        "distance": distance,
        "duration": duration,
    }


def search_locations(query):
    query = (query or "").strip()
    if len(query) < 2:
        raise RequestValidationError("Enter at least two characters to search")
    if len(query) > 120:
        raise RequestValidationError("Search text is too long")

    try:
        response = requests.get(
            SEARCH_URL,
            params={"q": query, "format": "jsonv2", "limit": 5},
            headers=REQUEST_HEADERS,
            timeout=10,
        )
        response.raise_for_status()
        payload = response.json()
    except (requests.RequestException, ValueError) as error:
        _log_provider_failure("Geocoding", error)
        raise ExternalServiceError("Location search is temporarily unavailable") from error
    if not isinstance(payload, list):
        raise ExternalServiceError("The location search service returned an invalid response")

    results = []
    for item in payload:
        try:
            latitude = float(item["lat"])
            longitude = float(item["lon"])
            if not math.isfinite(latitude) or not math.isfinite(longitude):
                continue
            if not -90 <= latitude <= 90 or not -180 <= longitude <= 180:
                continue
            results.append(
                {
                    "name": item["display_name"],
                    "lat": latitude,
                    "lon": longitude,
                }
            )
        except (KeyError, TypeError, ValueError):
            continue
    return results


def generate_gpx(
    route_points,
    activity_type,
    end_time,
    pace_seconds_per_km,
    route_distance_meters,
):
    route_points = deduplicate_track_points(route_points)
    validate_track_distance(route_points, route_distance_meters)
    duration_seconds = max(
        1,
        math.floor(route_distance_meters / 1000 * pace_seconds_per_km + 0.5),
    )
    try:
        start_time = end_time - timedelta(seconds=duration_seconds)
    except OverflowError:
        raise RequestValidationError("Finish time is too early for this route and pace") from None
    generator = GpxGen(
        activity_type=activity_type,
        end_time=end_time,
        duration_seconds=duration_seconds,
    )
    generator.add_points(route_points)
    return {
        "gpx": generator.build(),
        "duration_seconds": duration_seconds,
        "start_time": start_time,
    }
