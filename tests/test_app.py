from datetime import datetime, timedelta, timezone
from unittest.mock import patch
from xml.etree import ElementTree

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

    def test_future_finish_time_is_rejected(self):
        future = (datetime.now(timezone.utc) + timedelta(minutes=2)).isoformat()
        with self.assertRaisesRegex(service.RequestValidationError, "future"):
            service.parse_end_time(future)


class GpxGeneratorTests(SimpleTestCase):
    def test_generates_gpx_with_timestamps_for_every_point(self):
        finish = datetime(2026, 8, 19, 9, 30, tzinfo=timezone.utc)
        generator = GpxGen(activity_type="run", end_time=finish)
        generator.add_points([(13.7563, 100.5018), (13.75, 100.51), (13.7466, 100.5347)])

        document = ElementTree.fromstring(generator.build())
        points = document.findall(f".//{{{GPX_NAMESPACE}}}trkpt")
        timestamps = document.findall(f".//{{{GPX_NAMESPACE}}}trkpt/{{{GPX_NAMESPACE}}}time")

        self.assertEqual(len(points), 3)
        self.assertEqual(len(timestamps), 3)
        self.assertEqual(timestamps[-1].text, "2026-08-19T09:30:00.000Z")


class HttpFlowTests(SimpleTestCase):
    route_result = {
        "points": [(13.7563, 100.5018), (13.75, 100.51), (13.7466, 100.5347)],
        "distance": 4100.0,
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
        self.assertEqual(response.json()["distance"], 4100.0)
        self.assertEqual(len(response.json()["route"]), 3)

    @patch("strava_generator.service.get_route", return_value=route_result)
    def test_generate_endpoint_returns_valid_gpx(self, _get_route):
        response = self.client.get(
            "/api/v1/generate-strava-gpx",
            {
                "points": "13.7563,100.5018|13.7466,100.5347",
                "activity_type": "bike",
                "end_time": "2026-08-19T09:30:00Z",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("<gpx", response.json()["gpx"])
        self.assertEqual(response.json()["distance"], 4100.0)
