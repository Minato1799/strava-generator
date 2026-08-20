(function initialiseGpxImport(global) {
    'use strict';

    const GPX_NAMESPACE = 'http://www.topografix.com/GPX/1/1';
    const XSI_NAMESPACE = 'http://www.w3.org/2001/XMLSchema-instance';
    const EARTH_RADIUS_METERS = 6371008.8;
    const MAX_FILE_BYTES = 25 * 1024 * 1024;
    const MAX_TRACK_POINTS = 100000;
    const GPX_TYPE_BY_ACTIVITY = { run: 'running', bike: 'cycling' };

    function elementsByLocalName(parent, name) {
        return Array.from(parent.getElementsByTagNameNS('*', name));
    }

    function directChild(parent, name) {
        return Array.from(parent.children).find((child) => child.localName === name) || null;
    }

    function haversineMeters(first, second) {
        const latitudeA = first.latitude * Math.PI / 180;
        const latitudeB = second.latitude * Math.PI / 180;
        const latitudeDelta = (second.latitude - first.latitude) * Math.PI / 180;
        const longitudeDelta = (second.longitude - first.longitude) * Math.PI / 180;
        const haversine = Math.sin(latitudeDelta / 2) ** 2
            + Math.cos(latitudeA) * Math.cos(latitudeB) * Math.sin(longitudeDelta / 2) ** 2;
        return 2 * EARTH_RADIUS_METERS * Math.asin(Math.min(1, Math.sqrt(haversine)));
    }

    function activityFromTrackType(value) {
        const normalized = String(value || '').trim().toLowerCase();
        if (['bike', 'biking', 'cycling', 'ride'].includes(normalized)) return 'bike';
        if (['run', 'running', 'trailrun'].includes(normalized)) return 'run';
        return null;
    }

    function parsePoint(pointElement, segmentIndex) {
        if (!pointElement.hasAttribute('lat') || !pointElement.hasAttribute('lon')) {
            throw new Error('The GPX contains a track point without coordinates.');
        }
        const latitude = Number(pointElement.getAttribute('lat'));
        const longitude = Number(pointElement.getAttribute('lon'));
        if (
            !Number.isFinite(latitude)
            || !Number.isFinite(longitude)
            || latitude < -90
            || latitude > 90
            || longitude < -180
            || longitude > 180
        ) {
            throw new Error('The GPX contains an invalid track coordinate.');
        }

        const timeElement = directChild(pointElement, 'time');
        const timestamp = timeElement ? Date.parse(timeElement.textContent.trim()) : Number.NaN;
        return {
            latitude,
            longitude,
            segmentIndex,
            timestamp,
            hasTime: Boolean(timeElement) && Number.isFinite(timestamp),
            hasElevation: Boolean(directChild(pointElement, 'ele')),
            hasExtensions: Boolean(directChild(pointElement, 'extensions')),
        };
    }

    function parse(text, filename = 'activity.gpx') {
        if (typeof text !== 'string' || !text.trim()) throw new Error('Choose a non-empty GPX file.');
        if (/<!DOCTYPE|<!ENTITY/i.test(text)) {
            throw new Error('GPX files containing DTD or entity declarations are not supported.');
        }

        const document = new DOMParser().parseFromString(text, 'application/xml');
        if (elementsByLocalName(document, 'parsererror').length) {
            throw new Error('The selected file is not valid XML.');
        }
        if (!document.documentElement || document.documentElement.localName !== 'gpx') {
            throw new Error('The selected file is not a GPX document.');
        }

        const tracks = elementsByLocalName(document, 'trk');
        if (!tracks.length) throw new Error('The GPX does not contain a recorded track.');
        const segmentElements = tracks.flatMap((track) => elementsByLocalName(track, 'trkseg'));
        const segments = segmentElements.map((segment, segmentIndex) =>
            elementsByLocalName(segment, 'trkpt').map((point) => parsePoint(point, segmentIndex))
        ).filter((segment) => segment.length);
        const points = segments.flat();
        if (points.length < 2) throw new Error('The GPX must contain at least two track points.');
        if (points.length > MAX_TRACK_POINTS) {
            throw new Error(`The GPX exceeds the ${MAX_TRACK_POINTS.toLocaleString()} point import limit.`);
        }

        const distanceMeters = segments.reduce((total, segment) => total + segment
            .slice(1)
            .reduce((segmentTotal, point, index) => segmentTotal + haversineMeters(segment[index], point), 0), 0);
        if (!Number.isFinite(distanceMeters) || distanceMeters <= 0) {
            throw new Error('The GPX track must cover a positive distance.');
        }

        const timestampsComplete = points.every((point) => point.hasTime);
        const timestampsStrict = timestampsComplete && points
            .slice(1)
            .every((point, index) => point.timestamp > points[index].timestamp);
        const firstTrack = tracks[0];
        const nameElement = directChild(firstTrack, 'name');
        const typeElement = directChild(firstTrack, 'type');
        const fallbackName = filename.replace(/\.gpx$/i, '') || 'Imported activity';
        const activityName = (nameElement?.textContent || fallbackName).trim().slice(0, 120)
            || 'Imported activity';

        return {
            document,
            filename,
            activityName,
            activityType: activityFromTrackType(typeElement?.textContent),
            segments,
            points,
            distanceMeters,
            preserveAvailable: timestampsStrict,
            startTime: timestampsStrict ? new Date(points[0].timestamp) : null,
            endTime: timestampsStrict ? new Date(points.at(-1).timestamp) : null,
            durationSeconds: timestampsStrict
                ? Math.round((points.at(-1).timestamp - points[0].timestamp) / 1000)
                : null,
            elevationPointCount: points.filter((point) => point.hasElevation).length,
            extensionPointCount: points.filter((point) => point.hasExtensions).length,
        };
    }

    function createTrackChild(document, track, name, beforeNames) {
        const namespace = document.documentElement.namespaceURI || GPX_NAMESPACE;
        const element = document.createElementNS(namespace, name);
        const before = Array.from(track.children).find((child) => beforeNames.includes(child.localName));
        track.insertBefore(element, before || null);
        return element;
    }

    function setTrackIdentity(document, activityName, activityType) {
        if (!GPX_TYPE_BY_ACTIVITY[activityType]) throw new Error('Choose Run or Bike.');
        if (typeof activityName !== 'string' || !activityName.trim() || activityName.length > 120) {
            throw new Error('Enter an activity name using no more than 120 characters.');
        }
        const track = elementsByLocalName(document, 'trk')[0];
        if (!track) throw new Error('The GPX does not contain a recorded track.');
        const name = directChild(track, 'name')
            || createTrackChild(
                document,
                track,
                'name',
                ['cmt', 'desc', 'src', 'link', 'number', 'type', 'extensions', 'trkseg'],
            );
        name.textContent = activityName;
        const type = directChild(track, 'type')
            || createTrackChild(document, track, 'type', ['trkseg', 'extensions']);
        type.textContent = GPX_TYPE_BY_ACTIVITY[activityType];
    }

    function serializeDocument(document) {
        const serialized = new XMLSerializer().serializeToString(document);
        return serialized.startsWith('<?xml')
            ? serialized
            : `<?xml version="1.0" encoding="UTF-8"?>\n${serialized}`;
    }

    function serializePreserved(imported, activityName, activityType) {
        const document = imported.document.cloneNode(true);
        setTrackIdentity(document, activityName, activityType);
        return serializeDocument(document);
    }

    function allocateMilliseconds(points, totalMilliseconds, totalDistance) {
        const segmentCount = points.length - 1;
        if (totalMilliseconds < segmentCount) {
            throw new Error('The selected duration is too short for this GPX point density.');
        }
        const distances = points.slice(1).map((point, index) => (
            point.segmentIndex === points[index].segmentIndex
                ? haversineMeters(points[index], point)
                : 0
        ));
        const remaining = totalMilliseconds - segmentCount;
        const weighted = distances.map((distance) => remaining * distance / totalDistance);
        const allocated = weighted.map(Math.floor);
        let remainder = remaining - allocated.reduce((total, value) => total + value, 0);
        const order = allocated.map((_, index) => index)
            .sort((first, second) => (weighted[second] - allocated[second])
                - (weighted[first] - allocated[first]));
        for (let index = 0; index < order.length && remainder > 0; index += 1, remainder -= 1) {
            allocated[order[index]] += 1;
        }
        return allocated.map((milliseconds) => milliseconds + 1);
    }

    function setPointTime(document, point, value) {
        let time = directChild(point, 'time');
        if (!time) {
            const namespace = document.documentElement.namespaceURI || GPX_NAMESPACE;
            time = document.createElementNS(namespace, 'time');
            const firstAfterElevation = Array.from(point.children)
                .find((child) => child.localName !== 'ele');
            point.insertBefore(time, firstAfterElevation || null);
        }
        time.textContent = value.toISOString();
    }

    function setMetadataTime(document, value) {
        const root = document.documentElement;
        let metadata = directChild(root, 'metadata');
        const namespace = root.namespaceURI || GPX_NAMESPACE;
        if (!metadata) {
            metadata = document.createElementNS(namespace, 'metadata');
            root.insertBefore(metadata, root.firstElementChild);
        }
        let time = directChild(metadata, 'time');
        if (!time) {
            time = document.createElementNS(namespace, 'time');
            const before = Array.from(metadata.children)
                .find((child) => ['keywords', 'bounds', 'extensions'].includes(child.localName));
            metadata.insertBefore(time, before || null);
        }
        time.textContent = value.toISOString();
    }

    function serializeRetimed(imported, activityName, activityType, finishTime, paceSecondsPerKm) {
        if (!(finishTime instanceof Date) || !Number.isFinite(finishTime.getTime())) {
            throw new Error('Choose a valid finish time.');
        }
        if (!Number.isFinite(paceSecondsPerKm) || paceSecondsPerKm <= 0) {
            throw new Error('Choose a valid average pace.');
        }
        const document = imported.document.cloneNode(true);
        const pointElements = elementsByLocalName(document, 'trkpt');
        if (pointElements.length !== imported.points.length) {
            throw new Error('The GPX track changed while it was being processed.');
        }

        const durationSeconds = Math.max(1, Math.round(imported.distanceMeters / 1000 * paceSecondsPerKm));
        const durations = allocateMilliseconds(
            imported.points,
            durationSeconds * 1000,
            imported.distanceMeters,
        );
        const startTime = new Date(finishTime.getTime() - durationSeconds * 1000);
        let elapsedMilliseconds = 0;
        pointElements.forEach((point, index) => {
            const extensions = directChild(point, 'extensions');
            if (extensions) extensions.remove();
            const pointTime = index === pointElements.length - 1
                ? finishTime
                : new Date(startTime.getTime() + elapsedMilliseconds);
            setPointTime(document, point, pointTime);
            if (index < durations.length) elapsedMilliseconds += durations[index];
        });

        setTrackIdentity(document, activityName, activityType);
        setMetadataTime(document, startTime);
        const rootNamespace = document.documentElement.namespaceURI || GPX_NAMESPACE;
        document.documentElement.setAttributeNS(
            XSI_NAMESPACE,
            'xsi:schemaLocation',
            `${rootNamespace} ${rootNamespace}/gpx.xsd`,
        );
        return {
            gpx: serializeDocument(document),
            durationSeconds,
            startTime,
        };
    }

    global.GpxImport = Object.freeze({
        MAX_FILE_BYTES,
        parse,
        serializePreserved,
        serializeRetimed,
    });
}(window));
