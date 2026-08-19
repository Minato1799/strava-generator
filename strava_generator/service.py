"""Stateless routing and geocoding helpers used by the public API."""

import logging
from datetime import datetime, timezone

import requests

from mylibs.gpxgen import GpxGen


logger = logging.getLogger("strava_generator")

MAX_ROUTE_POINTS = 26
MAX_TOTAL_DISTANCE_METERS = 50_000
ROUTING_BASE_URL = "https://router.project-osrm.org/route/v1"
SEARCH_URL = "https://nominatim.openstreetmap.org/search"
REQUEST_HEADERS = {
    "User-Agent": "StravaGeneratorVercel/1.0 (+https://github.com/iamdubrovskii/strava-generator)"
}


class RequestValidationError(ValueError):
    pass


class ExternalServiceError(RuntimeError):
    pass


def parse_points(raw_points):
    if not raw_points:
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

        if not -90 <= latitude <= 90 or not -180 <= longitude <= 180:
            raise RequestValidationError(f"Route point is outside valid map bounds: {raw_point}")
        points.append((latitude, longitude))

    return points


def validate_activity_type(activity_type):
    activity_type = (activity_type or "run").strip().lower()
    if activity_type not in {"run", "bike"}:
        raise RequestValidationError("Activity type must be run or bike")
    return activity_type


def parse_end_time(raw_end_time):
    if not raw_end_time:
        return datetime.now(timezone.utc)

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
    profile = "foot" if activity_type == "run" else "bike"
    coordinates = ";".join(f"{longitude:.7f},{latitude:.7f}" for latitude, longitude in points)
    url = f"{ROUTING_BASE_URL}/{profile}/{coordinates}"

    try:
        response = requests.get(
            url,
            params={"overview": "full", "geometries": "geojson", "steps": "false"},
            headers=REQUEST_HEADERS,
            timeout=15,
        )
        response.raise_for_status()
        payload = response.json()
    except (requests.RequestException, ValueError) as error:
        logger.warning("Routing provider request failed: %s", error)
        raise ExternalServiceError("The routing service is temporarily unavailable") from error

    routes = payload.get("routes") or []
    if payload.get("code") != "Ok" or not routes:
        raise RequestValidationError("A route could not be built for these points")

    route = routes[0]
    distance = float(route.get("distance", 0))
    if distance > MAX_TOTAL_DISTANCE_METERS:
        raise RequestValidationError(
            f"Route distance cannot exceed {MAX_TOTAL_DISTANCE_METERS / 1000:.0f} km"
        )

    geometry = route.get("geometry", {}).get("coordinates") or []
    if len(geometry) < 2:
        raise ExternalServiceError("The routing service returned an incomplete route")

    route_points = [(float(latitude), float(longitude)) for longitude, latitude in geometry]
    return {
        "points": route_points,
        "distance": distance,
        "duration": float(route.get("duration", 0)),
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
        logger.warning("Geocoding provider request failed: %s", error)
        raise ExternalServiceError("Location search is temporarily unavailable") from error

    results = []
    for item in payload:
        try:
            results.append(
                {
                    "name": item["display_name"],
                    "lat": float(item["lat"]),
                    "lon": float(item["lon"]),
                }
            )
        except (KeyError, TypeError, ValueError):
            continue
    return results


def generate_gpx(route_points, activity_type, end_time):
    generator = GpxGen(activity_type=activity_type, end_time=end_time)
    generator.add_points(route_points)
    return generator.build()
