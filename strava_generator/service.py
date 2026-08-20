"""Stateless routing and geocoding helpers used by the public API."""

import copy
import hashlib
import logging
import math
import os
import re
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from urllib.parse import urlsplit

import requests
from django.conf import settings

from mylibs.gpxgen import GpxGen

logger = logging.getLogger("strava_generator")

MAX_ROUTE_POINTS = 26
MAX_ROUTE_POINTS_TEXT_LENGTH = 4_096
MAX_TRACK_POINTS = 10_000
MAX_SEARCH_RESULTS = 5
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
ROUTING_FALLBACK_BASE_URLS = {
    "run": os.getenv("ROUTING_FOOT_FALLBACK_BASE_URL", "").strip(),
    "bike": os.getenv("ROUTING_BIKE_FALLBACK_BASE_URL", "").strip(),
}
ROUTING_LOCAL_BBOX = os.getenv("ROUTING_LOCAL_BBOX", "").strip()
SEARCH_URL = os.getenv(
    "GEOCODING_SEARCH_URL",
    "https://nominatim.openstreetmap.org/search",
)
REQUEST_HEADERS = {
    "User-Agent": os.getenv(
        "PROVIDER_USER_AGENT",
        "StravaGenerator/3.0 (+https://github.com/Minato1799/strava-generator)",
    ),
    "Referer": os.getenv(
        "PROVIDER_REFERER",
        "https://strava.scan-realtime.site/",
    ),
}
PACE_LIMITS_SECONDS = {"run": (120.0, 1800.0), "bike": (30.0, 1200.0)}

_MISSING = object()
_state_lock = threading.Lock()
_route_cache = OrderedDict()
_search_cache = OrderedDict()
_inflight_requests = {}
_throttles_lock = threading.Lock()
_provider_throttles = {}


@dataclass
class _CacheEntry:
    expires_at: float
    value: object


@dataclass
class _InFlightRequest:
    completed: threading.Event = field(default_factory=threading.Event)
    value: object = _MISSING
    error: BaseException | None = None


@dataclass
class _ProviderThrottle:
    lock: threading.Lock = field(default_factory=threading.Lock)
    last_started_at: float | None = None


class RequestValidationError(ValueError):
    pass


class ExternalServiceError(RuntimeError):
    pass


class RouteNotFoundError(RequestValidationError):
    """A provider could not connect the requested points on its current graph."""


def _now():
    return time.monotonic()


def _sleep(seconds):
    time.sleep(seconds)


def _response_status(response):
    status_code = getattr(response, "status_code", None)
    return status_code if isinstance(status_code, int) else "unknown"


def _log_provider_event(
    provider,
    event,
    outcome,
    started_at,
    *,
    status="not_applicable",
    level=logging.INFO,
):
    elapsed_ms = max(0, round((_now() - started_at) * 1000))
    logger.log(
        level,
        "provider_event provider=%s event=%s outcome=%s status=%s elapsed_ms=%d",
        provider,
        event,
        outcome,
        status,
        elapsed_ms,
    )


def _cache_digest(*parts):
    digest = hashlib.sha256()
    for part in parts:
        digest.update(str(part).encode("utf-8"))
        digest.update(b"\0")
    return digest.digest()


def _cache_config(namespace):
    if namespace == "route":
        return (
            _route_cache,
            settings.ROUTE_CACHE_TTL_SECONDS,
            settings.PROVIDER_CACHE_MAX_ENTRIES,
        )
    return (
        _search_cache,
        settings.SEARCH_CACHE_TTL_SECONDS,
        settings.PROVIDER_CACHE_MAX_ENTRIES,
    )


def _cache_get_locked(cache, key, now):
    entry = cache.get(key)
    if entry is None:
        return _MISSING
    if entry.expires_at <= now:
        del cache[key]
        return _MISSING
    cache.move_to_end(key)
    return copy.deepcopy(entry.value)


def _cache_set_locked(cache, key, value, now, ttl_seconds, max_entries):
    if ttl_seconds <= 0 or max_entries <= 0:
        return

    expired_keys = [cache_key for cache_key, entry in cache.items() if entry.expires_at <= now]
    for expired_key in expired_keys:
        del cache[expired_key]

    cache[key] = _CacheEntry(
        expires_at=now + ttl_seconds,
        value=copy.deepcopy(value),
    )
    cache.move_to_end(key)
    while len(cache) > max_entries:
        cache.popitem(last=False)


def _wait_for_inflight(flight, provider, started_at):
    _log_provider_event(provider, "coalescing", "wait", started_at)
    flight.completed.wait()
    if flight.error is not None:
        _log_provider_event(
            provider,
            "coalescing",
            "shared_error",
            started_at,
            level=logging.WARNING,
        )
        raise flight.error
    _log_provider_event(provider, "coalescing", "shared_success", started_at)
    return copy.deepcopy(flight.value)


def _cached_provider_call(namespace, key, provider, loader):
    started_at = _now()
    cache, ttl_seconds, max_entries = _cache_config(namespace)
    flight_key = (namespace, key)

    with _state_lock:
        cached = _cache_get_locked(cache, key, started_at)
        if cached is not _MISSING:
            _log_provider_event(provider, "cache", "hit", started_at)
            return cached

        flight = _inflight_requests.get(flight_key)
        if flight is None:
            flight = _InFlightRequest()
            _inflight_requests[flight_key] = flight
            is_leader = True
        else:
            is_leader = False

    if not is_leader:
        return _wait_for_inflight(flight, provider, started_at)

    try:
        value = loader()
    except BaseException as error:
        with _state_lock:
            flight.error = error
            _inflight_requests.pop(flight_key, None)
            flight.completed.set()
        raise

    with _state_lock:
        _cache_set_locked(cache, key, value, _now(), ttl_seconds, max_entries)
        flight.value = copy.deepcopy(value)
        _inflight_requests.pop(flight_key, None)
        flight.completed.set()
    return copy.deepcopy(value)


def _provider_identity(url):
    parsed = urlsplit(url)
    return (parsed.scheme.casefold(), parsed.netloc.casefold())


def _is_loopback_url(url):
    hostname = (urlsplit(url).hostname or "").casefold()
    return hostname in {"127.0.0.1", "::1", "localhost"}


def _local_bbox_contains(points):
    try:
        west, south, east, north = (
            float(value.strip()) for value in ROUTING_LOCAL_BBOX.split(",")
        )
    except (TypeError, ValueError):
        return False
    if not all(math.isfinite(value) for value in (west, south, east, north)):
        return False
    if not (-180 <= west < east <= 180 and -90 <= south < north <= 90):
        return False
    return all(south <= latitude <= north and west <= longitude <= east for latitude, longitude in points)


def _throttle_provider(url, minimum_interval_seconds):
    identity = _provider_identity(url)
    with _throttles_lock:
        throttle = _provider_throttles.setdefault(identity, _ProviderThrottle())

    with throttle.lock:
        now = _now()
        if throttle.last_started_at is not None:
            delay = max(0.0, throttle.last_started_at + minimum_interval_seconds - now)
            if delay:
                _sleep(delay)
                now = _now()
        throttle.last_started_at = now


def _reset_provider_state():
    """Clear per-process provider state for deterministic tests."""

    with _state_lock:
        _route_cache.clear()
        _search_cache.clear()
        _inflight_requests.clear()
    with _throttles_lock:
        _provider_throttles.clear()


def parse_points(raw_points):
    if not isinstance(raw_points, str) or not raw_points:
        raise RequestValidationError("Add at least two route points")
    if len(raw_points) > MAX_ROUTE_POINTS_TEXT_LENGTH:
        raise RequestValidationError("Route points are too long")

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
            raise RequestValidationError("Route contains an invalid point") from None

        if not math.isfinite(latitude) or not math.isfinite(longitude):
            raise RequestValidationError("Route contains an invalid point")
        if not -90 <= latitude <= 90 or not -180 <= longitude <= 180:
            raise RequestValidationError("Route contains a point outside valid map bounds")
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
        return datetime.now(UTC)
    if not isinstance(raw_end_time, str):
        raise RequestValidationError("Finish time must be a valid ISO date and time")

    try:
        parsed = datetime.fromisoformat(raw_end_time)
    except ValueError:
        raise RequestValidationError("Finish time must be a valid ISO date and time") from None

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    else:
        parsed = parsed.astimezone(UTC)

    if parsed.timestamp() > datetime.now(UTC).timestamp() + 60:
        raise RequestValidationError("Finish time cannot be in the future")
    return parsed


def _fetch_route(url):
    started_at = _now()
    response = None
    try:
        minimum_interval = (
            0
            if _is_loopback_url(url)
            else settings.ROUTING_PROVIDER_MIN_INTERVAL_SECONDS
        )
        _throttle_provider(url, minimum_interval)
        # A cache miss performs one request only. Provider failures are surfaced
        # to the caller and are never retried automatically.
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
        error_response = getattr(error, "response", None)
        if error_response is not None:
            response = error_response
        _log_provider_event(
            "routing",
            "outbound",
            type(error).__name__,
            started_at,
            status=_response_status(response),
            level=logging.WARNING,
        )
        raise ExternalServiceError("The routing service is temporarily unavailable") from error

    if not isinstance(payload, dict):
        _log_provider_event(
            "routing",
            "outbound",
            "invalid_response",
            started_at,
            status=_response_status(response),
            level=logging.WARNING,
        )
        raise ExternalServiceError("The routing service returned an invalid response")

    routes = payload.get("routes") or []
    if payload.get("code") != "Ok" or not routes:
        _log_provider_event(
            "routing",
            "outbound",
            "no_route",
            started_at,
            status=_response_status(response),
        )
        raise RouteNotFoundError("A route could not be built for these points")
    if not isinstance(routes, list):
        _log_provider_event(
            "routing",
            "outbound",
            "invalid_response",
            started_at,
            status=_response_status(response),
            level=logging.WARNING,
        )
        raise ExternalServiceError("The routing service returned an invalid response")

    route = routes[0]
    try:
        distance = float(route.get("distance", 0))
        duration = float(route.get("duration", 0))
    except (AttributeError, TypeError, ValueError) as error:
        _log_provider_event(
            "routing",
            "outbound",
            "invalid_response",
            started_at,
            status=_response_status(response),
            level=logging.WARNING,
        )
        raise ExternalServiceError("The routing service returned an invalid response") from error
    if not math.isfinite(distance) or distance <= 0:
        _log_provider_event(
            "routing",
            "outbound",
            "invalid_response",
            started_at,
            status=_response_status(response),
            level=logging.WARNING,
        )
        raise ExternalServiceError("The routing service returned an invalid distance")
    if not math.isfinite(duration) or duration < 0:
        _log_provider_event(
            "routing",
            "outbound",
            "invalid_response",
            started_at,
            status=_response_status(response),
            level=logging.WARNING,
        )
        raise ExternalServiceError("The routing service returned an invalid duration")
    if distance > MAX_TOTAL_DISTANCE_METERS:
        _log_provider_event(
            "routing",
            "outbound",
            "route_too_long",
            started_at,
            status=_response_status(response),
        )
        raise RequestValidationError(
            f"Route distance cannot exceed {MAX_TOTAL_DISTANCE_METERS / 1000:.0f} km"
        )

    try:
        geometry = route.get("geometry", {}).get("coordinates") or []
        if not isinstance(geometry, list) or not 2 <= len(geometry) <= MAX_TRACK_POINTS:
            raise RequestValidationError("The routing service returned invalid geometry")
        route_points = parse_track_points(
            [[coordinate[1], coordinate[0]] for coordinate in geometry]
        )
        validate_track_distance(route_points, distance)
    except (AttributeError, IndexError, TypeError, RequestValidationError) as error:
        _log_provider_event(
            "routing",
            "outbound",
            "invalid_response",
            started_at,
            status=_response_status(response),
            level=logging.WARNING,
        )
        raise ExternalServiceError("The routing service returned an invalid route") from error

    result = {
        "points": route_points,
        "distance": distance,
        "duration": duration,
    }
    _log_provider_event(
        "routing",
        "outbound",
        "success",
        started_at,
        status=_response_status(response),
    )
    return result


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
    primary_base_url = ROUTING_BASE_URLS[activity_type].rstrip("/")
    base_urls = []
    if not _is_loopback_url(primary_base_url) or _local_bbox_contains(points):
        base_urls.append(primary_base_url)
    fallback_base_url = ROUTING_FALLBACK_BASE_URLS[activity_type].rstrip("/")
    if fallback_base_url and fallback_base_url not in base_urls:
        base_urls.append(fallback_base_url)
    if not base_urls:
        raise ExternalServiceError("The routing service is temporarily unavailable")
    cache_key = _cache_digest(tuple(base_urls), activity_type, coordinates)

    def fetch_route():
        for index, base_url in enumerate(base_urls):
            try:
                return _fetch_route(f"{base_url}/{coordinates}")
            except (ExternalServiceError, RouteNotFoundError):
                if index == len(base_urls) - 1:
                    raise
                _log_provider_event(
                    "routing",
                    "failover",
                    "next_candidate",
                    _now(),
                    level=logging.WARNING,
                )
        raise ExternalServiceError("The routing service is temporarily unavailable")

    return _cached_provider_call(
        "route",
        cache_key,
        "routing",
        fetch_route,
    )


def _fetch_search_results(query):
    started_at = _now()
    response = None
    try:
        _throttle_provider(SEARCH_URL, settings.GEOCODING_PROVIDER_MIN_INTERVAL_SECONDS)
        # Do not add automatic retries here: retrying public geocoding requests
        # can amplify load during provider outages.
        response = requests.get(
            SEARCH_URL,
            params={"q": query, "format": "jsonv2", "limit": MAX_SEARCH_RESULTS},
            headers=REQUEST_HEADERS,
            timeout=10,
        )
        response.raise_for_status()
        payload = response.json()
    except (requests.RequestException, ValueError) as error:
        error_response = getattr(error, "response", None)
        if error_response is not None:
            response = error_response
        _log_provider_event(
            "geocoding",
            "outbound",
            type(error).__name__,
            started_at,
            status=_response_status(response),
            level=logging.WARNING,
        )
        raise ExternalServiceError("Location search is temporarily unavailable") from error
    if not isinstance(payload, list):
        _log_provider_event(
            "geocoding",
            "outbound",
            "invalid_response",
            started_at,
            status=_response_status(response),
            level=logging.WARNING,
        )
        raise ExternalServiceError("The location search service returned an invalid response")

    results = []
    for item in payload[:MAX_SEARCH_RESULTS]:
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
    _log_provider_event(
        "geocoding",
        "outbound",
        "success",
        started_at,
        status=_response_status(response),
    )
    return results


def search_locations(query):
    if query in (None, ""):
        query = ""
    elif not isinstance(query, str):
        raise RequestValidationError("Search text must be a string")
    query = query.strip()
    if len(query) < 2:
        raise RequestValidationError("Enter at least two characters to search")
    if len(query) > 120:
        raise RequestValidationError("Search text is too long")
    try:
        query.encode("utf-8")
    except UnicodeEncodeError:
        raise RequestValidationError("Search text contains invalid Unicode") from None

    normalized_query = " ".join(query.casefold().split())
    cache_key = _cache_digest(SEARCH_URL, normalized_query)
    return _cached_provider_call(
        "search",
        cache_key,
        "geocoding",
        lambda: _fetch_search_results(query),
    )


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
