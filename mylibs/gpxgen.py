"""Create GPX 1.1 tracks with a user-selected, constant pace."""

import math
from datetime import UTC, datetime, timedelta
from xml.etree import ElementTree

GPX_NAMESPACE = "http://www.topografix.com/GPX/1/1"
XSI_NAMESPACE = "http://www.w3.org/2001/XMLSchema-instance"
EARTH_RADIUS_KM = 6371.0088

ElementTree.register_namespace("", GPX_NAMESPACE)
ElementTree.register_namespace("xsi", XSI_NAMESPACE)


class GpxGen:
    def __init__(self, *, activity_type="run", end_time=None, duration_seconds=None):
        if activity_type not in {"run", "bike"}:
            raise ValueError("Activity type must be run or bike")
        self.activity_type = activity_type
        self.end_time = end_time or datetime.now(UTC)
        if self.end_time.tzinfo is None:
            self.end_time = self.end_time.replace(tzinfo=UTC)
        self.end_time = self.end_time.astimezone(UTC)
        self.duration_seconds = float(duration_seconds) if duration_seconds is not None else None
        if self.duration_seconds is None or not math.isfinite(self.duration_seconds):
            raise ValueError("A finite activity duration is required")
        if self.duration_seconds <= 0:
            raise ValueError("Activity duration must be positive")
        self.points = []

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

    def _segment_milliseconds(self):
        distances = [
            self._distance_km(self.points[index - 1], self.points[index])
            for index in range(1, len(self.points))
        ]
        total_distance = sum(distances)
        if total_distance <= 0:
            raise ValueError("Route points must cover a positive distance")

        total_milliseconds = round(self.duration_seconds * 1000)
        segment_count = len(distances)
        if total_milliseconds < segment_count:
            raise ValueError("Activity duration is too short for the route detail")

        # Reserve one millisecond for every segment so GPX timestamps remain
        # strictly increasing, then distribute the remaining duration by distance.
        remaining = total_milliseconds - segment_count
        weighted = [remaining * distance / total_distance for distance in distances]
        allocated = [math.floor(value) for value in weighted]
        remainder = remaining - sum(allocated)
        remainder_order = sorted(
            range(segment_count),
            key=lambda index: weighted[index] - allocated[index],
            reverse=True,
        )
        for index in remainder_order[:remainder]:
            allocated[index] += 1
        return [milliseconds + 1 for milliseconds in allocated]

    def build(self):
        if len(self.points) < 2:
            raise ValueError("At least two route points are required")

        durations = self._segment_milliseconds()
        start_time = self.end_time - timedelta(milliseconds=sum(durations))

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

        elapsed_milliseconds = 0
        last_point_index = len(self.points) - 1
        for index, (latitude, longitude) in enumerate(self.points):
            # Force the final point to the requested finish time. Building a
            # timedelta from floating-point segment lengths can otherwise end
            # one microsecond early and format as xx:xx:59.999Z.
            point_time = (
                self.end_time
                if index == last_point_index
                else start_time + timedelta(milliseconds=elapsed_milliseconds)
            )
            track_point = ElementTree.SubElement(
                segment,
                f"{{{GPX_NAMESPACE}}}trkpt",
                {"lat": f"{latitude:.7f}", "lon": f"{longitude:.7f}"},
            )
            time_element = ElementTree.SubElement(track_point, f"{{{GPX_NAMESPACE}}}time")
            time_element.text = self._format_time(point_time)
            if index < len(durations):
                elapsed_milliseconds += durations[index]

        ElementTree.indent(root, space="  ")
        return ElementTree.tostring(root, encoding="unicode", xml_declaration=True)

    @staticmethod
    def _format_time(value):
        return value.astimezone(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")
