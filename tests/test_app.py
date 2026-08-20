import json
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from itertools import pairwise
from threading import Event
from typing import ClassVar
from unittest.mock import Mock, patch
from xml.etree import ElementTree

import requests
from django.test import SimpleTestCase
from django.test.utils import override_settings

from mylibs.gpxgen import GPX_NAMESPACE, GpxGen
from strava_generator import service


@override_settings(
    ROUTING_PROVIDER_MIN_INTERVAL_SECONDS=0,
    GEOCODING_PROVIDER_MIN_INTERVAL_SECONDS=0,
)
class ServiceValidationTests(SimpleTestCase):
    def setUp(self):
        service._reset_provider_state()

    def test_parse_points_accepts_valid_coordinates(self):
        self.assertEqual(
            service.parse_points("13.7563,100.5018|13.7466,100.5347"),
            [(13.7563, 100.5018), (13.7466, 100.5347)],
        )

    def test_parse_points_requires_two_points(self):
        with self.assertRaisesRegex(service.RequestValidationError, "at least two"):
            service.parse_points("13.7563,100.5018")

    def test_parse_points_rejects_oversized_or_malformed_input_without_echoing_it(self):
        oversized = "x" * (service.MAX_ROUTE_POINTS_TEXT_LENGTH + 1)
        with self.assertRaises(service.RequestValidationError) as oversized_error:
            service.parse_points(oversized)
        self.assertNotIn("x" * 100, str(oversized_error.exception))

        private_value = "private-location-value"
        with self.assertRaises(service.RequestValidationError) as malformed_error:
            service.parse_points(f"{private_value}|0,0")
        self.assertNotIn(private_value, str(malformed_error.exception))

    def test_parse_track_points_and_distance(self):
        self.assertEqual(
            service.parse_track_points([[13.73024, 100.53877], [13.72927, 100.54268]]),
            [(13.73024, 100.53877), (13.72927, 100.54268)],
        )
        self.assertEqual(service.parse_route_distance(743.8), 743.8)

    def test_parse_track_points_rejects_invalid_coordinates(self):
        with self.assertRaises(service.RequestValidationError):
            service.parse_track_points([[13.73024, 100.53877], [float("nan"), 100.54268]])
        with self.assertRaises(service.RequestValidationError):
            service.parse_points("13.73024,100.53877|nan,100.54268")

    def test_search_rejects_non_string_queries(self):
        for query in (["park"], {"query": "park"}, 123, True):
            with self.subTest(query=query), self.assertRaises(service.RequestValidationError):
                service.search_locations(query)

    def test_search_rejects_unpaired_unicode_surrogates(self):
        with self.assertRaisesRegex(service.RequestValidationError, "invalid Unicode"):
            service.search_locations("\ud800x")

    def test_json_fields_reject_invalid_types(self):
        with self.assertRaises(service.RequestValidationError):
            service.validate_activity_type(["run"])
        with self.assertRaises(service.RequestValidationError):
            service.parse_end_time(["2026-08-19T09:30:00Z"])

    def test_future_finish_time_is_rejected(self):
        future = (datetime.now(UTC) + timedelta(minutes=2)).isoformat()
        with self.assertRaisesRegex(service.RequestValidationError, "future"):
            service.parse_end_time(future)

    def test_parse_pace_accepts_minutes_and_seconds(self):
        self.assertEqual(service.parse_pace("5:30", "run"), 330)
        self.assertEqual(service.parse_pace("03:00", "bike"), 180)

    def test_parse_pace_rejects_missing_or_malformed_values(self):
        for value in ("", "6:5", "6:60", "6.00", "abc"):
            with self.subTest(value=value), self.assertRaises(service.RequestValidationError):
                service.parse_pace(value, "run")

    def test_parse_pace_uses_activity_specific_limits(self):
        self.assertEqual(service.parse_pace("2:00", "run"), 120)
        self.assertEqual(service.parse_pace("30:00", "run"), 1800)
        self.assertEqual(service.parse_pace("0:30", "bike"), 30)
        self.assertEqual(service.parse_pace("20:00", "bike"), 1200)
        with self.assertRaises(service.RequestValidationError):
            service.parse_pace("1:59", "run")

    @patch("strava_generator.service.requests.get")
    def test_routing_uses_separate_foot_and_bike_graphs(self, get):
        points = [(13.73024, 100.53877), (13.72927, 100.54268)]
        response = Mock()
        response.json.return_value = {
            "code": "Ok",
            "routes": [
                {
                    "distance": service.track_distance_meters(points),
                    "duration": 600,
                    "geometry": {"coordinates": [[100.53877, 13.73024], [100.54268, 13.72927]]},
                }
            ],
        }
        get.return_value = response

        service.get_route(points, "run")
        run_url = get.call_args.args[0]
        service.get_route(points, "bike")
        bike_url = get.call_args.args[0]

        self.assertIn("/routed-foot/route/v1/driving/", run_url)
        self.assertIn("/routed-bike/route/v1/driving/", bike_url)

    @patch("strava_generator.service.requests.get")
    def test_identical_routes_are_served_from_bounded_process_cache(self, get):
        points = [(13.73024, 100.53877), (13.72927, 100.54268)]
        response = Mock(status_code=200)
        response.json.return_value = {
            "code": "Ok",
            "routes": [
                {
                    "distance": service.track_distance_meters(points),
                    "duration": 600,
                    "geometry": {
                        "coordinates": [[100.53877, 13.73024], [100.54268, 13.72927]]
                    },
                }
            ],
        }
        get.return_value = response

        first = service.get_route(points, "run")
        first["points"].append((0, 0))
        second = service.get_route(points, "run")

        get.assert_called_once()
        self.assertEqual(second["points"], points)

    @patch("strava_generator.service.requests.get")
    def test_identical_concurrent_routes_share_one_outbound_request(self, get):
        points = [(13.73024, 100.53877), (13.72927, 100.54268)]
        response = Mock(status_code=200)
        response.json.return_value = {
            "code": "Ok",
            "routes": [
                {
                    "distance": service.track_distance_meters(points),
                    "duration": 600,
                    "geometry": {
                        "coordinates": [[100.53877, 13.73024], [100.54268, 13.72927]]
                    },
                }
            ],
        }
        outbound_started = Event()
        release_outbound = Event()
        follower_joined = Event()

        def blocked_get(*_args, **_kwargs):
            outbound_started.set()
            if not release_outbound.wait(timeout=2):
                raise requests.Timeout("test request was not released")
            return response

        real_wait_for_inflight = service._wait_for_inflight

        def observed_wait(*args, **kwargs):
            follower_joined.set()
            return real_wait_for_inflight(*args, **kwargs)

        get.side_effect = blocked_get
        with (
            patch("strava_generator.service._wait_for_inflight", side_effect=observed_wait),
            ThreadPoolExecutor(max_workers=2) as pool,
        ):
            first = pool.submit(service.get_route, points, "run")
            outbound_ready = outbound_started.wait(timeout=2)
            second = pool.submit(service.get_route, points, "run")
            joined = follower_joined.wait(timeout=2)
            release_outbound.set()

            self.assertTrue(outbound_ready)
            self.assertTrue(joined)
            self.assertEqual(first.result(timeout=2), second.result(timeout=2))

        get.assert_called_once()

    @patch("strava_generator.service.requests.get")
    def test_search_cache_normalizes_query_and_is_bounded(self, get):
        response = Mock(status_code=200)
        response.json.return_value = [
            {"display_name": "Lumphini Park", "lat": "13.7300", "lon": "100.5410"}
        ]
        get.return_value = response

        with override_settings(PROVIDER_CACHE_MAX_ENTRIES=1):
            first = service.search_locations("Lumphini Park")
            normalized = service.search_locations("  lumphini   park ")
            service.search_locations("Benjakitti Park")
            service.search_locations("Lumphini Park")

        self.assertEqual(first, normalized)
        self.assertEqual(get.call_count, 3)

    @patch("strava_generator.service.requests.get")
    def test_provider_errors_are_not_retried_or_cached(self, get):
        points = [(13.73024, 100.53877), (13.72927, 100.54268)]
        get.side_effect = requests.Timeout("provider timeout with hidden coordinates")

        with self.assertRaises(service.ExternalServiceError):
            service.get_route(points, "run")
        self.assertEqual(get.call_count, 1)

        with self.assertRaises(service.ExternalServiceError):
            service.get_route(points, "run")
        self.assertEqual(get.call_count, 2)

    def test_provider_throttle_spaces_requests_to_the_same_host(self):
        with (
            patch("strava_generator.service._now", side_effect=[100.0, 100.25, 101.1]),
            patch("strava_generator.service._sleep") as sleep,
        ):
            service._throttle_provider("https://provider.test/route", 1.0)
            service._throttle_provider("https://provider.test/search", 1.0)

        sleep.assert_called_once()
        self.assertAlmostEqual(sleep.call_args.args[0], 0.75)
        throttle = service._provider_throttles[("https", "provider.test")]
        self.assertEqual(throttle.last_started_at, 101.1)

    @patch("strava_generator.service.requests.get")
    def test_routing_rejects_overlong_waypoints_before_provider_call(self, get):
        with self.assertRaises(service.RequestValidationError):
            service.get_route([(13.7563, 100.5018), (14.7563, 100.5018)], "run")
        get.assert_not_called()

    @patch("strava_generator.service.requests.get")
    def test_routing_rejects_identical_waypoints_before_provider_call(self, get):
        with self.assertRaisesRegex(service.RequestValidationError, "identical"):
            service.get_route([(13.7563, 100.5018), (13.7563, 100.5018)], "run")
        get.assert_not_called()

    @patch("strava_generator.service.requests.get")
    def test_routing_rejects_non_finite_provider_data(self, get):
        response = Mock()
        response.json.return_value = {
            "code": "Ok",
            "routes": [
                {
                    "distance": float("nan"),
                    "duration": 600,
                    "geometry": {"coordinates": [[100.53877, 13.73024], [100.54268, 13.72927]]},
                }
            ],
        }
        get.return_value = response

        with self.assertRaises(service.ExternalServiceError):
            service.get_route([(13.73024, 100.53877), (13.72927, 100.54268)], "run")

    @patch("strava_generator.service.requests.get")
    def test_routing_rejects_oversized_provider_geometry_before_conversion(self, get):
        response = Mock(status_code=200)
        response.json.return_value = {
            "code": "Ok",
            "routes": [
                {
                    "distance": 100,
                    "duration": 60,
                    "geometry": {
                        "coordinates": [[100.54, 13.73]] * (service.MAX_TRACK_POINTS + 1)
                    },
                }
            ],
        }
        get.return_value = response

        with self.assertRaises(service.ExternalServiceError):
            service.get_route([(13.73024, 100.53877), (13.72927, 100.54268)], "run")

    @patch("strava_generator.service.requests.get")
    def test_search_caps_provider_results_even_if_provider_ignores_limit(self, get):
        response = Mock(status_code=200)
        response.json.return_value = [
            {"display_name": f"Park {index}", "lat": "13.73", "lon": "100.54"}
            for index in range(20)
        ]
        get.return_value = response

        results = service.search_locations("public park")

        self.assertEqual(len(results), service.MAX_SEARCH_RESULTS)

    @patch("strava_generator.service.requests.get")
    def test_provider_failure_log_does_not_include_route_coordinates(self, get):
        response = Mock(status_code=429)
        response.raise_for_status.side_effect = requests.HTTPError(
            "429 for https://provider.test/13.73024,100.53877",
            response=response,
        )
        get.return_value = response

        with (
            self.assertLogs("strava_generator", level="WARNING") as captured,
            self.assertRaises(service.ExternalServiceError),
        ):
            service.get_route([(13.73024, 100.53877), (13.72927, 100.54268)], "run")

        logs = " ".join(captured.output)
        self.assertIn("status=429", logs)
        self.assertNotIn("13.73024", logs)


class GpxGeneratorTests(SimpleTestCase):
    def test_generates_gpx_with_timestamps_for_every_point(self):
        finish = datetime(2026, 8, 19, 9, 30, tzinfo=UTC)
        generator = GpxGen(activity_type="run", end_time=finish, duration_seconds=330)
        generator.add_points([(13.7563, 100.5018), (13.75, 100.51), (13.7466, 100.5347)])

        document = ElementTree.fromstring(generator.build())
        points = document.findall(f".//{{{GPX_NAMESPACE}}}trkpt")
        timestamps = document.findall(f".//{{{GPX_NAMESPACE}}}trkpt/{{{GPX_NAMESPACE}}}time")

        self.assertEqual(len(points), 3)
        self.assertEqual(len(timestamps), 3)
        self.assertEqual(timestamps[0].text, "2026-08-19T09:24:30.000Z")
        self.assertEqual(timestamps[-1].text, "2026-08-19T09:30:00.000Z")
        timestamp_values = [timestamp.text for timestamp in timestamps]
        self.assertTrue(all(first < second for first, second in pairwise(timestamp_values)))

    def test_same_inputs_generate_identical_gpx(self):
        finish = datetime(2026, 8, 19, 9, 30, tzinfo=UTC)

        def build():
            generator = GpxGen(activity_type="bike", end_time=finish, duration_seconds=900)
            generator.add_points([(13.73024, 100.53877), (13.72877, 100.54067)])
            return generator.build()

        self.assertEqual(build(), build())


class HttpFlowTests(SimpleTestCase):
    route_result: ClassVar[dict] = {
        "points": [(13.7563, 100.5018), (13.75, 100.51), (13.7466, 100.5347)],
        "distance": 3824.0,
        "duration": 1800.0,
    }

    def test_home_and_health_render(self):
        home = self.client.get("/")
        health = self.client.get("/health/")

        self.assertEqual(home.status_code, 200)
        self.assertContains(home, "No account or API key required")
        self.assertJSONEqual(health.content, {"status": "ok"})

    @patch("strava_generator.service.get_route", return_value=route_result)
    def test_route_endpoint_returns_geometry(self, _get_route):
        response = self.client.post(
            "/api/v1/route",
            data=json.dumps(
                {
                    "points": "13.7563,100.5018|13.7466,100.5347",
                    "activity_type": "run",
                }
            ),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["distance"], 3824.0)
        self.assertEqual(len(response.json()["route"]), 3)
        self.assertEqual(response["Cache-Control"], "private, no-store")

    @patch("strava_generator.service.search_locations", return_value=[])
    def test_search_endpoint_uses_private_json_post(self, search_locations):
        response = self.client.post(
            "/api/v1/search-location",
            data=json.dumps({"query": "Lumphini Park"}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["results"], [])
        self.assertEqual(response["Cache-Control"], "private, no-store")
        search_locations.assert_called_once_with("Lumphini Park")

    def test_route_and_search_reject_get_and_non_json_post(self):
        for path in ("/api/v1/route", "/api/v1/search-location"):
            with self.subTest(path=path, method="get"):
                self.assertEqual(self.client.get(path).status_code, 405)
            with self.subTest(path=path, method="non-json"):
                response = self.client.post(path, data="{}", content_type="text/plain")
                self.assertEqual(response.status_code, 415)

    def test_search_rejects_non_string_json_without_server_error(self):
        response = self.client.post(
            "/api/v1/search-location",
            data=json.dumps({"query": ["Lumphini Park"]}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response["Cache-Control"], "private, no-store")

    def test_search_rejects_pathological_json_without_server_error(self):
        payloads = (
            b'{"query":' + b"9" * 5_000 + b"}",
            b'{"query":' + b"[" * 10_000 + b"0" + b"]" * 10_000 + b"}",
        )
        for body in payloads:
            with self.subTest(size=len(body)):
                response = self.client.post(
                    "/api/v1/search-location",
                    data=body,
                    content_type="application/json",
                )
                self.assertEqual(response.status_code, 400)
                self.assertEqual(response["Cache-Control"], "private, no-store")

    def test_route_rejects_large_body_with_small_private_error(self):
        body = json.dumps({"points": "x" * 1_000_000 + "|0,0"})
        response = self.client.post(
            "/api/v1/route",
            data=body,
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertLess(len(response.content), 256)
        self.assertEqual(response["Cache-Control"], "private, no-store")

    @override_settings(DATA_UPLOAD_MAX_MEMORY_SIZE=1_024)
    def test_route_rejects_body_over_django_limit_with_json_413(self):
        response = self.client.post(
            "/api/v1/route",
            data=json.dumps({"points": "x" * 2_000}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 413)
        self.assertLess(len(response.content), 256)
        self.assertEqual(response["Cache-Control"], "private, no-store")

    def test_generate_endpoint_returns_valid_gpx(self):
        response = self.client.post(
            "/api/v1/generate-strava-gpx",
            data=json.dumps(
                {
                    "route_points": self.route_result["points"],
                    "route_distance": self.route_result["distance"],
                    "activity_type": "bike",
                    "end_time": "2026-08-19T09:30:00Z",
                    "pace": "3:00",
                }
            ),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("<gpx", response.json()["gpx"])
        self.assertEqual(response.json()["distance"], 3824.0)
        self.assertEqual(response.json()["duration_seconds"], 688)
        self.assertEqual(response.json()["start_time"], "2026-08-19T09:18:32Z")
        self.assertEqual(response["Cache-Control"], "private, no-store")

    def test_generate_rejects_invalid_pace(self):
        response = self.client.post(
            "/api/v1/generate-strava-gpx",
            data=json.dumps(
                {
                    "route_points": self.route_result["points"],
                    "route_distance": self.route_result["distance"],
                    "activity_type": "run",
                    "end_time": "2026-08-19T09:30:00Z",
                    "pace": "6:60",
                }
            ),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)

    def test_generate_rejects_distance_mismatch_and_time_underflow(self):
        base_payload = {
            "route_points": self.route_result["points"],
            "route_distance": 1,
            "activity_type": "run",
            "end_time": "2026-08-19T09:30:00Z",
            "pace": "6:00",
        }
        mismatch = self.client.post(
            "/api/v1/generate-strava-gpx",
            data=json.dumps(base_payload),
            content_type="application/json",
        )
        self.assertEqual(mismatch.status_code, 400)

        underflow_payload = {
            **base_payload,
            "route_distance": self.route_result["distance"],
            "end_time": "0001-01-01T00:00:00Z",
            "pace": "30:00",
        }
        underflow = self.client.post(
            "/api/v1/generate-strava-gpx",
            data=json.dumps(underflow_payload),
            content_type="application/json",
        )
        self.assertEqual(underflow.status_code, 400)

    def test_generate_deduplicates_consecutive_track_points(self):
        points = [
            self.route_result["points"][0],
            self.route_result["points"][0],
            *self.route_result["points"][1:],
        ]
        response = self.client.post(
            "/api/v1/generate-strava-gpx",
            data=json.dumps(
                {
                    "route_points": points,
                    "route_distance": self.route_result["distance"],
                    "activity_type": "run",
                    "end_time": "2026-08-19T09:30:00Z",
                    "pace": "6:00",
                }
            ),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        document = ElementTree.fromstring(response.json()["gpx"])
        track_points = document.findall(f".//{{{GPX_NAMESPACE}}}trkpt")
        self.assertEqual(len(track_points), len(self.route_result["points"]))

    def test_generate_requires_post(self):
        self.assertEqual(self.client.get("/api/v1/generate-strava-gpx").status_code, 405)

    def test_generate_requires_json_content_type(self):
        response = self.client.post(
            "/api/v1/generate-strava-gpx",
            data="{}",
            content_type="text/plain",
        )
        self.assertEqual(response.status_code, 415)
