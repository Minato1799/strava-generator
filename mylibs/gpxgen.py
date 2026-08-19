"""Create GPX 1.1 tracks with varied, activity-appropriate pacing."""

import math
import random
from datetime import datetime, timedelta, timezone
from xml.etree import ElementTree


GPX_NAMESPACE = "http://www.topografix.com/GPX/1/1"
XSI_NAMESPACE = "http://www.w3.org/2001/XMLSchema-instance"
EARTH_RADIUS_KM = 6371.0088

ElementTree.register_namespace("", GPX_NAMESPACE)
ElementTree.register_namespace("xsi", XSI_NAMESPACE)


class GpxGen:
    def __init__(self, *, activity_type="run", end_time=None, random_source=None):
        if activity_type not in {"run", "bike"}:
            raise ValueError("Activity type must be run or bike")
        self.activity_type = activity_type
        self.end_time = end_time or datetime.now(timezone.utc)
        if self.end_time.tzinfo is None:
            self.end_time = self.end_time.replace(tzinfo=timezone.utc)
        self.end_time = self.end_time.astimezone(timezone.utc)
        self.points = []
        self.random = random_source or random.Random()

    def add_point(self, point):
        latitude, longitude = point
        self.points.append((float(latitude), float(longitude)))

    def add_points(self, points):
        for point in points:
            self.add_point(point)

    @staticmethod
    def _distance_km(point_a, point_b):
        lat1, lon1 = map(math.radians, point_a)
        lat2, lon2 = map(math.radians, point_b)
        delta_lat = lat2 - lat1
        delta_lon = lon2 - lon1
        haversine = (
            math.sin(delta_lat / 2) ** 2
            + math.cos(lat1) * math.cos(lat2) * math.sin(delta_lon / 2) ** 2
        )
        return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(haversine))

    def _segment_seconds(self):
        pace_range = (3.2, 7.8) if self.activity_type == "run" else (2.0, 5.0)
        durations = []
        current_pace = self.random.uniform(*pace_range)
        for index in range(1, len(self.points)):
            if index % 20 == 0:
                current_pace = self.random.uniform(*pace_range)
            distance_km = self._distance_km(self.points[index - 1], self.points[index])
            durations.append(max(distance_km * current_pace * 60, 0.1))
        return durations

    def build(self):
        if len(self.points) < 2:
            raise ValueError("At least two route points are required")

        durations = self._segment_seconds()
        start_time = self.end_time - timedelta(seconds=sum(durations))

        root = ElementTree.Element(
            f"{{{GPX_NAMESPACE}}}gpx",
            {
                "version": "1.1",
                "creator": "Strava Generator",
                f"{{{XSI_NAMESPACE}}}schemaLocation": (
                    "http://www.topografix.com/GPX/1/1 "
                    "http://www.topografix.com/GPX/1/1/gpx.xsd"
                ),
            },
        )
        metadata = ElementTree.SubElement(root, f"{{{GPX_NAMESPACE}}}metadata")
        metadata_time = ElementTree.SubElement(metadata, f"{{{GPX_NAMESPACE}}}time")
        metadata_time.text = self._format_time(start_time)

        track = ElementTree.SubElement(root, f"{{{GPX_NAMESPACE}}}trk")
        track_name = ElementTree.SubElement(track, f"{{{GPX_NAMESPACE}}}name")
        track_name.text = f"Generated {self.activity_type.title()} Activity"
        segment = ElementTree.SubElement(track, f"{{{GPX_NAMESPACE}}}trkseg")

        point_time = start_time
        for index, (latitude, longitude) in enumerate(self.points):
            if index:
                point_time += timedelta(seconds=durations[index - 1])
            track_point = ElementTree.SubElement(
                segment,
                f"{{{GPX_NAMESPACE}}}trkpt",
                {"lat": f"{latitude:.7f}", "lon": f"{longitude:.7f}"},
            )
            time_element = ElementTree.SubElement(track_point, f"{{{GPX_NAMESPACE}}}time")
            time_element.text = self._format_time(point_time)

        ElementTree.indent(root, space="  ")
        return ElementTree.tostring(root, encoding="unicode", xml_declaration=True)

    @staticmethod
    def _format_time(value):
        return value.astimezone(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")
