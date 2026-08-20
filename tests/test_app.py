import json
from datetime import datetime, timedelta, timezone
from itertools import pairwise
from typing import ClassVar
from unittest.mock import Mock, patch
from xml.etree import ElementTree

import requests
from django.test import SimpleTestCase

from mylibs.gpxgen import GPX_NAMESPACE, GpxGen
from strava_generator import service


class ServiceValidationTests(SimpleTestCase):
    def test_parse_points_accepts_valid_coordinates(self):
        self.assertEqual(
            service.parse_points("13.7563,100.5018|13.7466,100.5347"),
            [(13.7563, 100.5018), (13.7466, 100.5347)],
        )

    def test_parse_points_requires_two_points(self):
        with self.assertRaisesRegex(service.RequestValidationError, "at least two"):
            service.parse_points("13.7563,100.5018")

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

    def test_json_fields_reject_invalid_types(self):
        with self.assertRaises(service.RequestValidationError):
            service.validate_activity_type(["run"])
        with self.assertRaises(service.RequestValidationError):
            service.parse_end_time(["2026-08-19T09:30:00Z"])

    def test_future_finish_time_is_rejected(self):
        future = (datetime.now(timezone.utc) + timedelta(minutes=2)).isoformat()
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
        finish = datetime(2026, 8, 19, 9, 30, tzinfo=timezone.utc)
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
        finish = datetime(2026, 8, 19, 9, 30, tzinfo=timezone.utc)

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
        response = self.client.get(
            "/api/v1/route",
            {"points": "13.7563,100.5018|13.7466,100.5347", "activity_type": "run"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["distance"], 3824.0)
        self.assertEqual(len(response.json()["route"]), 3)

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
