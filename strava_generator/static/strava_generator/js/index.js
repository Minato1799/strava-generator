const MAX_POINTS = 26;
const DEFAULT_CENTER = [13.7563, 100.5018];
const ACTIVITY_MINIMUMS = { run: 3000, bike: 5000 };
const ROUTE_DEBOUNCE_MS = 1100;
const DEFAULT_PACE_VALUES = { run: '6:00', bike: '3:00' };
const PACE_LIMITS_SECONDS = { run: [120, 1800], bike: [30, 1200] };
const MAX_MAP_DISPLAY_POINTS = 5000;

const state = {
    map: null,
    markers: [],
    routeLayer: null,
    routeReady: false,
    routePoints: [],
    routeDistanceMeters: 0,
    routeController: null,
    routeRequestId: 0,
    updateTimer: null,
    generating: false,
    generationController: null,
    generationRequestId: 0,
    paceByActivity: { ...DEFAULT_PACE_VALUES },
    importedTrack: null,
    importRequestId: 0,
    activityNameTouched: false,
};

const elements = {
    searchForm: document.querySelector('#search-form'),
    searchInput: document.querySelector('#location-search'),
    searchResults: document.querySelector('#search-results'),
    importGpx: document.querySelector('#import-gpx'),
    gpxFile: document.querySelector('#gpx-file'),
    clearRoute: document.querySelector('#clear-route'),
    routeStatus: document.querySelector('#route-status'),
    mapHint: document.querySelector('.map-hint'),
    routeHeading: document.querySelector('#route-heading'),
    pointList: document.querySelector('#point-list'),
    pointCount: document.querySelector('#point-count'),
    importSummary: document.querySelector('#import-summary'),
    importFileName: document.querySelector('#import-file-name'),
    importDetails: document.querySelector('#import-details'),
    activityName: document.querySelector('#activity-name'),
    activityNameError: document.querySelector('#activity-name-error'),
    timingOptions: document.querySelector('#timing-options'),
    preserveOption: document.querySelector('input[name="timing-mode"][value="preserve"]'),
    preserveError: document.querySelector('#preserve-error'),
    paceField: document.querySelector('#pace-field'),
    pace: document.querySelector('#pace-input'),
    paceSpeed: document.querySelector('#pace-speed'),
    paceError: document.querySelector('#pace-error'),
    estimatedDuration: document.querySelector('#estimated-duration'),
    calculatedStart: document.querySelector('#calculated-start'),
    finishTime: document.querySelector('#finish-time'),
    finishError: document.querySelector('#finish-error'),
    finishStepLabel: document.querySelector('#finish-step-label'),
    finishControl: document.querySelector('#finish-control'),
    durationLabel: document.querySelector('#duration-label'),
    startLabel: document.querySelector('#start-label'),
    setNow: document.querySelector('#set-now'),
    generate: document.querySelector('#generate-gpx'),
    toast: document.querySelector('#toast'),
};

function initialise() {
    state.map = L.map('map', { zoomControl: true }).setView(DEFAULT_CENTER, 12);
    L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
        maxZoom: 19,
        attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
    }).addTo(state.map);

    state.map.on('click', (event) => {
        if (state.importedTrack) {
            showError('Clear the imported GPX before drawing a new route.');
            return;
        }
        const { lat, lng } = event.latlng;
        addPoint(lat, lng, `Pinned point ${state.markers.length + 1}`);
    });

    elements.searchForm.addEventListener('submit', searchLocations);
    elements.importGpx.addEventListener('click', () => elements.gpxFile.click());
    elements.gpxFile.addEventListener('change', importGpxFile);
    elements.clearRoute.addEventListener('click', clearRoute);
    elements.setNow.addEventListener('click', setFinishTimeToNow);
    elements.generate.addEventListener('click', generateGpx);
    elements.activityName.addEventListener('input', () => {
        state.activityNameTouched = true;
        cancelGeneration();
        updateActivityNameUi(false);
        syncGenerateState();
    });
    elements.activityName.addEventListener('blur', () => {
        const validation = activityNameValidation();
        if (validation.valid) elements.activityName.value = validation.name;
        updateActivityNameUi(true);
        syncGenerateState();
    });
    elements.pace.addEventListener('input', () => {
        cancelGeneration();
        state.paceByActivity[activityType()] = elements.pace.value;
        updatePaceUi(false);
    });
    elements.pace.addEventListener('blur', () => {
        const parsed = parsePaceInput(elements.pace.value, activityType());
        if (parsed.valid) {
            elements.pace.value = parsed.normalized;
            state.paceByActivity[activityType()] = parsed.normalized;
        }
        updatePaceUi(true);
    });
    elements.finishTime.addEventListener('input', () => {
        cancelGeneration();
        updatePaceUi(false, true);
    });
    document.querySelectorAll('input[name="activity"]').forEach((input) => {
        input.addEventListener('change', handleActivityChange);
    });
    document.querySelectorAll('input[name="timing-mode"]').forEach((input) => {
        input.addEventListener('change', () => {
            cancelGeneration();
            updateTimingModeUi();
        });
    });
    document.addEventListener('click', (event) => {
        if (!elements.searchForm.contains(event.target)) elements.searchResults.hidden = true;
    });

    elements.pace.value = state.paceByActivity[activityType()];
    setFinishTimeToNow();
    renderPointList();
    updatePaceUi(false);

    if (navigator.geolocation) {
        navigator.geolocation.getCurrentPosition(
            ({ coords }) => {
                if (!state.markers.length) state.map.setView([coords.latitude, coords.longitude], 14);
            },
            () => {},
            { timeout: 5000 }
        );
    }
}

function activityType() {
    return document.querySelector('input[name="activity"]:checked').value;
}

function timingMode() {
    return document.querySelector('input[name="timing-mode"]:checked').value;
}

function preservingImportedTiming() {
    return Boolean(state.importedTrack) && timingMode() === 'preserve';
}

function defaultActivityName(type = activityType()) {
    return `Generated ${type === 'bike' ? 'Bike' : 'Run'} Activity`;
}

function activityNameValidation() {
    const name = elements.activityName.value.trim().replace(/\s+/g, ' ');
    if (!name) return { valid: false, error: 'Enter an activity name.' };
    if (name.length > 120) return { valid: false, error: 'Use no more than 120 characters.' };
    return { valid: true, name };
}

function updateActivityNameUi(showError) {
    const validation = activityNameValidation();
    elements.activityName.setAttribute('aria-invalid', String(!validation.valid));
    elements.activityNameError.hidden = validation.valid || !showError;
    elements.activityNameError.textContent = validation.valid ? '' : validation.error;
    return validation;
}

function handleActivityChange() {
    cancelGeneration();
    if (!state.importedTrack && !state.activityNameTouched) {
        elements.activityName.value = defaultActivityName();
    }
    elements.pace.value = state.paceByActivity[activityType()];
    updatePaceUi(false);
    if (state.importedTrack) {
        syncGenerateState();
    } else {
        scheduleRouteUpdate();
    }
}

function pointString() {
    return state.markers
        .map(({ marker }) => {
            const point = marker.getLatLng();
            return `${point.lat.toFixed(7)},${point.lng.toFixed(7)}`;
        })
        .join('|');
}

function addPoint(latitude, longitude, name) {
    if (state.importedTrack) {
        showError('Clear the imported GPX before adding route points.');
        return;
    }
    if (state.markers.length >= MAX_POINTS) {
        showError(`A route can contain at most ${MAX_POINTS} points.`);
        return;
    }

    const marker = L.marker([latitude, longitude], { draggable: true }).addTo(state.map);
    marker.on('dragend', () => {
        renderPointList();
        scheduleRouteUpdate();
    });
    state.markers.push({ marker, name });
    renderPointList();
    scheduleRouteUpdate();
}

function displaySegments(segments) {
    const totalPoints = segments.reduce((total, segment) => total + segment.length, 0);
    const stride = Math.max(1, Math.ceil(totalPoints / MAX_MAP_DISPLAY_POINTS));
    return segments.map((segment) => segment.filter((_, index) => (
        index === 0 || index === segment.length - 1 || index % stride === 0
    )).map((point) => [point.latitude, point.longitude]));
}

function importedActivityType(imported) {
    if (!imported.activityType) return;
    const input = document.querySelector(`input[name="activity"][value="${imported.activityType}"]`);
    if (input) input.checked = true;
}

function setImportedModeControls(enabled) {
    elements.searchInput.disabled = enabled;
    elements.searchForm.querySelector('button[type="submit"]').disabled = enabled;
    elements.pointList.hidden = enabled;
    elements.importSummary.hidden = !enabled;
    elements.timingOptions.hidden = !enabled;
    elements.searchResults.hidden = true;
    elements.routeHeading.textContent = enabled ? 'Imported GPX' : 'Route points';
    elements.mapHint.textContent = enabled
        ? 'Imported locally · Clear the track to draw a new route'
        : 'Click to add · Drag to adjust · Run and Bike follow matching paths';
}

function applyImportedTrack(imported) {
    cancelGeneration();
    window.clearTimeout(state.updateTimer);
    state.updateTimer = null;
    state.routeRequestId += 1;
    if (state.routeController) state.routeController.abort();
    state.routeController = null;
    state.markers.forEach(({ marker }) => state.map.removeLayer(marker));
    state.markers = [];
    removeRouteLayer();

    state.importedTrack = imported;
    state.routeReady = true;
    state.routePoints = [];
    state.routeDistanceMeters = imported.distanceMeters;
    state.activityNameTouched = true;
    importedActivityType(imported);
    elements.activityName.value = imported.activityName;
    elements.pace.value = state.paceByActivity[activityType()];

    const timingInput = document.querySelector(
        `input[name="timing-mode"][value="${imported.preserveAvailable ? 'preserve' : 'retime'}"]`
    );
    timingInput.checked = true;
    elements.preserveOption.disabled = !imported.preserveAvailable;
    elements.preserveError.hidden = imported.preserveAvailable;
    elements.preserveError.textContent = imported.preserveAvailable
        ? ''
        : 'Preserve is unavailable because some timestamps are missing or not strictly increasing.';

    state.routeLayer = L.polyline(displaySegments(imported.segments), {
        color: '#fc4c02', weight: 5, opacity: .92, lineJoin: 'round',
    }).addTo(state.map);
    state.map.fitBounds(state.routeLayer.getBounds(), { padding: [45, 45], maxZoom: 16 });

    elements.pointCount.textContent = `${imported.points.length.toLocaleString()} pts`;
    elements.importFileName.textContent = imported.filename;
    const sensorSummary = imported.extensionPointCount
        ? ` · sensor extensions ${imported.extensionPointCount.toLocaleString()}`
        : '';
    elements.importDetails.textContent = `${(imported.distanceMeters / 1000).toFixed(2)} km`
        + ` · ${imported.points.length.toLocaleString()} points`
        + ` · elevation ${imported.elevationPointCount.toLocaleString()}/${imported.points.length.toLocaleString()}`
        + sensorSummary;
    setImportedModeControls(true);
    setRouteStatus(`${(imported.distanceMeters / 1000).toFixed(2)} km · imported locally`, 'is-ready');
    renderPointList();
    updateActivityNameUi(false);
    updateTimingModeUi();
}

async function importGpxFile(event) {
    const file = event.target.files[0];
    if (!file) return;
    const requestId = state.importRequestId + 1;
    state.importRequestId = requestId;
    if (file.size > window.GpxImport.MAX_FILE_BYTES) {
        showError('Choose a GPX file no larger than 25 MB.');
        elements.gpxFile.value = '';
        return;
    }

    const previousImport = state.importedTrack;
    setRouteStatus('Reading GPX locally…', 'is-loading');
    try {
        const text = await file.text();
        if (requestId !== state.importRequestId) return;
        applyImportedTrack(window.GpxImport.parse(text, file.name));
    } catch (error) {
        if (requestId !== state.importRequestId) return;
        if (previousImport && state.importedTrack === previousImport) {
            setRouteStatus(
                `${(previousImport.distanceMeters / 1000).toFixed(2)} km · imported locally`,
                'is-ready',
            );
        } else {
            setRouteStatus('GPX import failed', 'is-error');
        }
        showError(error.message || 'The GPX file could not be imported.');
        elements.gpxFile.value = '';
    }
}

function removePoint(index) {
    const [removed] = state.markers.splice(index, 1);
    if (removed) state.map.removeLayer(removed.marker);
    renderPointList();
    scheduleRouteUpdate();
}

function movePoint(index, direction) {
    const destination = index + direction;
    if (destination < 0 || destination >= state.markers.length) return;
    [state.markers[index], state.markers[destination]] = [state.markers[destination], state.markers[index]];
    renderPointList();
    scheduleRouteUpdate();
}

function pointActionButton(action, label, text, disabled, onClick) {
    const button = document.createElement('button');
    button.type = 'button';
    button.dataset.action = action;
    button.setAttribute('aria-label', label);
    button.textContent = text;
    button.disabled = disabled;
    button.addEventListener('click', onClick);
    return button;
}

function renderPointList() {
    if (state.importedTrack) {
        elements.pointCount.textContent = `${state.importedTrack.points.length.toLocaleString()} pts`;
        elements.pointList.replaceChildren();
        return;
    }
    elements.pointCount.textContent = `${state.markers.length} / ${MAX_POINTS}`;
    elements.pointList.replaceChildren();

    if (!state.markers.length) {
        const empty = document.createElement('li');
        empty.className = 'empty-points';
        empty.textContent = 'Your route points will appear here.';
        elements.pointList.append(empty);
        return;
    }

    state.markers.forEach((item, index) => {
        const letter = String.fromCharCode(65 + index);
        item.marker.unbindTooltip();
        item.marker.bindTooltip(letter, {
            permanent: true,
            direction: 'center',
            className: 'marker-label',
        });

        const coordinates = item.marker.getLatLng();
        const row = document.createElement('li');
        row.className = 'point-item';

        const pointLetter = document.createElement('span');
        pointLetter.className = 'point-letter';
        pointLetter.textContent = letter;

        const pointCopy = document.createElement('button');
        pointCopy.type = 'button';
        pointCopy.className = 'point-copy';
        pointCopy.title = item.name;
        pointCopy.setAttribute('aria-label', `Show point ${letter} on map: ${item.name}`);
        const pointName = document.createElement('strong');
        pointName.textContent = item.name;
        const pointCoordinates = document.createElement('small');
        pointCoordinates.textContent = `${coordinates.lat.toFixed(5)}, ${coordinates.lng.toFixed(5)}`;
        pointCopy.append(pointName, pointCoordinates);
        pointCopy.addEventListener('click', () => state.map.panTo(item.marker.getLatLng()));

        const actions = document.createElement('span');
        actions.className = 'point-actions';
        actions.append(
            pointActionButton('up', `Move point ${letter} up`, '↑', index === 0, () => movePoint(index, -1)),
            pointActionButton(
                'down',
                `Move point ${letter} down`,
                '↓',
                index === state.markers.length - 1,
                () => movePoint(index, 1)
            ),
            pointActionButton('remove', `Remove point ${letter}`, '×', false, () => removePoint(index))
        );

        row.append(pointLetter, pointCopy, actions);
        elements.pointList.append(row);
    });
}

function removeRouteLayer() {
    if (state.routeLayer) state.map.removeLayer(state.routeLayer);
    state.routeLayer = null;
}

function scheduleRouteUpdate() {
    cancelGeneration();
    window.clearTimeout(state.updateTimer);
    state.updateTimer = null;
    state.routeRequestId += 1;
    if (state.routeController) state.routeController.abort();
    state.routeController = null;
    state.routeReady = false;
    state.routePoints = [];
    state.routeDistanceMeters = 0;
    removeRouteLayer();
    updatePaceUi(false);

    if (state.markers.length < 2) {
        setRouteStatus('Add two points to begin', 'is-empty');
        return;
    }

    const requestId = state.routeRequestId;
    setRouteStatus('Updating route…', 'is-loading');
    state.updateTimer = window.setTimeout(() => updateRoute(requestId), ROUTE_DEBOUNCE_MS);
}

async function updateRoute(requestId) {
    if (requestId !== state.routeRequestId) return;
    state.updateTimer = null;
    const controller = new AbortController();
    state.routeController = controller;
    setRouteStatus('Building route…', 'is-loading');

    try {
        const response = await fetch('/api/v1/route', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ points: pointString(), activity_type: activityType() }),
            signal: controller.signal,
        });
        const payload = await response.json();
        if (!response.ok) throw new Error(payload.error || 'Route could not be built');
        if (requestId !== state.routeRequestId) return;
        if (
            !Array.isArray(payload.route)
            || payload.route.length < 2
            || !Number.isFinite(payload.distance)
            || payload.distance <= 0
        ) {
            throw new Error('The routing service returned an incomplete route');
        }

        state.routePoints = payload.route;
        state.routeDistanceMeters = payload.distance;
        state.routeLayer = L.polyline(payload.route, {
            color: '#fc4c02', weight: 5, opacity: .92, lineJoin: 'round',
        }).addTo(state.map);
        state.map.fitBounds(state.routeLayer.getBounds(), { padding: [45, 45], maxZoom: 16 });

        const minimum = ACTIVITY_MINIMUMS[activityType()];
        const statusClass = payload.distance < minimum ? 'is-warning' : 'is-ready';
        const suffix = payload.distance < minimum ? ` · suggested minimum ${(minimum / 1000).toFixed(0)} km` : '';
        setRouteStatus(`${(payload.distance / 1000).toFixed(2)} km${suffix}`, statusClass);
        state.routeReady = true;
        updatePaceUi(false);
    } catch (error) {
        if (error.name === 'AbortError') return;
        if (requestId !== state.routeRequestId) return;
        setRouteStatus(error.message, 'is-error');
        showError(error.message);
    } finally {
        if (state.routeController === controller) state.routeController = null;
        syncGenerateState();
    }
}

async function searchLocations(event) {
    event.preventDefault();
    const query = elements.searchInput.value.trim();
    if (query.length < 2) {
        showError('Enter at least two characters to search.');
        return;
    }

    const submit = elements.searchForm.querySelector('button[type="submit"]');
    submit.disabled = true;
    submit.textContent = 'Searching…';
    try {
        const response = await fetch('/api/v1/search-location', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ query }),
        });
        const payload = await response.json();
        if (!response.ok) throw new Error(payload.error || 'Location search failed');
        renderSearchResults(payload.results);
    } catch (error) {
        showError(error.message);
    } finally {
        submit.disabled = false;
        submit.textContent = 'Search';
    }
}

function renderSearchResults(results) {
    if (state.importedTrack) {
        elements.searchResults.hidden = true;
        return;
    }
    elements.searchResults.replaceChildren();
    if (!results.length) {
        const empty = document.createElement('div');
        empty.className = 'search-result';
        empty.textContent = 'No locations found.';
        elements.searchResults.append(empty);
    } else {
        results.forEach((result) => {
            const button = document.createElement('button');
            button.type = 'button';
            button.className = 'search-result';
            button.textContent = result.name;
            button.addEventListener('click', () => {
                addPoint(result.lat, result.lon, result.name);
                state.map.setView([result.lat, result.lon], 15);
                elements.searchResults.hidden = true;
                elements.searchInput.value = '';
            });
            elements.searchResults.append(button);
        });
    }
    elements.searchResults.hidden = false;
}

function clearRoute() {
    const wasImported = Boolean(state.importedTrack);
    cancelGeneration();
    state.importRequestId += 1;
    window.clearTimeout(state.updateTimer);
    state.updateTimer = null;
    state.routeRequestId += 1;
    if (state.routeController) state.routeController.abort();
    state.routeController = null;
    state.markers.forEach(({ marker }) => state.map.removeLayer(marker));
    state.markers = [];
    removeRouteLayer();
    state.importedTrack = null;
    state.routeReady = false;
    state.routePoints = [];
    state.routeDistanceMeters = 0;
    elements.gpxFile.value = '';
    elements.preserveOption.disabled = false;
    elements.preserveError.hidden = true;
    setImportedModeControls(false);
    if (wasImported) {
        state.activityNameTouched = false;
        elements.activityName.value = defaultActivityName();
    }
    setGenerateButtonLabel(false);
    renderPointList();
    setRouteStatus('Add two points to begin', 'is-empty');
    updatePaceUi(false);
}

function parsePaceInput(value, type) {
    const rawValue = String(value || '').trim();
    const numberPadMatch = rawValue.match(/^(\d{1,2})(\d{2})$/);
    const paceValue = numberPadMatch ? `${numberPadMatch[1]}:${numberPadMatch[2]}` : rawValue;
    const match = paceValue.match(/^(\d{1,2}):([0-5]\d)$/);
    if (!match) {
        return { valid: false, error: 'Use MM:SS, or type digits such as 530.' };
    }

    const seconds = Number(match[1]) * 60 + Number(match[2]);
    const [minimum, maximum] = PACE_LIMITS_SECONDS[type];
    if (seconds < minimum || seconds > maximum) {
        const minimumText = formatPace(minimum);
        const maximumText = formatPace(maximum);
        return { valid: false, error: `Use a ${type} pace from ${minimumText} to ${maximumText} min/km.` };
    }

    return { valid: true, seconds, normalized: formatPace(seconds) };
}

function formatPace(totalSeconds) {
    const minutes = Math.floor(totalSeconds / 60);
    const seconds = totalSeconds % 60;
    return `${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`;
}

function formatDuration(totalSeconds) {
    const hours = Math.floor(totalSeconds / 3600);
    const minutes = Math.floor((totalSeconds % 3600) / 60);
    const seconds = totalSeconds % 60;
    return [hours, minutes, seconds].map((value) => String(value).padStart(2, '0')).join(':');
}

function formatDateTime(date) {
    return new Intl.DateTimeFormat(undefined, {
        dateStyle: 'medium',
        timeStyle: 'medium',
    }).format(date);
}

function finishDate() {
    return new Date(elements.finishTime.value);
}

function finishValidation() {
    const selectedFinish = finishDate();
    if (!Number.isFinite(selectedFinish.getTime())) {
        return { valid: false, error: 'Choose a valid finish time.' };
    }
    if (selectedFinish.getTime() > Date.now() + 60000) {
        return { valid: false, error: 'Finish time cannot be in the future.' };
    }
    return { valid: true, date: selectedFinish };
}

function updateTimingModeUi() {
    const preserve = preservingImportedTiming();
    elements.paceField.hidden = preserve;
    elements.finishControl.hidden = preserve;
    if (preserve) elements.finishError.hidden = true;
    elements.finishStepLabel.textContent = preserve ? '03 · ORIGINAL TIMING' : '03 · FINISH TIME';
    elements.durationLabel.textContent = preserve ? 'Elapsed duration' : 'Estimated duration';
    elements.startLabel.textContent = preserve ? 'Original start' : 'Calculated start';
    setGenerateButtonLabel(false);
    updatePaceUi(false);
}

function updatePaceUi(showPaceError, showFinishError = false) {
    if (preservingImportedTiming()) {
        const imported = state.importedTrack;
        elements.estimatedDuration.textContent = formatDuration(imported.durationSeconds);
        elements.calculatedStart.textContent = formatDateTime(imported.startTime);
        syncGenerateState();
        return;
    }

    const parsed = parsePaceInput(elements.pace.value, activityType());
    elements.pace.setAttribute('aria-invalid', String(!parsed.valid));
    elements.paceError.hidden = parsed.valid || !showPaceError;
    elements.paceError.textContent = parsed.valid ? '' : parsed.error;
    elements.paceSpeed.textContent = parsed.valid ? `${(3600 / parsed.seconds).toFixed(1)} km/h` : '— km/h';

    const finish = finishValidation();
    elements.finishTime.setAttribute('aria-invalid', String(!finish.valid));
    elements.finishError.hidden = finish.valid || !showFinishError;
    elements.finishError.textContent = finish.valid ? '' : finish.error;

    if (!parsed.valid || !state.routeReady || !finish.valid) {
        elements.estimatedDuration.textContent = '—';
        elements.calculatedStart.textContent = '—';
        syncGenerateState();
        return;
    }

    const durationSeconds = Math.max(1, Math.round(state.routeDistanceMeters / 1000 * parsed.seconds));
    const start = new Date(finish.date.getTime() - durationSeconds * 1000);
    elements.estimatedDuration.textContent = formatDuration(durationSeconds);
    elements.calculatedStart.textContent = formatDateTime(start);
    syncGenerateState();
}

function syncGenerateState() {
    const nameValid = activityNameValidation().valid;
    const preserveValid = preservingImportedTiming() && state.importedTrack.preserveAvailable;
    const retimeValid = !preservingImportedTiming()
        && parsePaceInput(elements.pace.value, activityType()).valid
        && finishValidation().valid;
    elements.generate.disabled = !state.routeReady
        || !nameValid
        || (!preserveValid && !retimeValid)
        || state.generating;
}

function setGenerateButtonLabel(generating) {
    const label = document.createElement('span');
    label.textContent = generating ? 'Preparing…' : (state.importedTrack ? 'Export GPX' : 'Generate GPX');
    const icon = document.createElement('span');
    icon.setAttribute('aria-hidden', 'true');
    icon.textContent = generating ? '•••' : '↓';
    elements.generate.replaceChildren(label, icon);
}

function cancelGeneration() {
    state.generationRequestId += 1;
    if (state.generationController) state.generationController.abort();
    state.generationController = null;
    if (state.generating) {
        state.generating = false;
        setGenerateButtonLabel(false);
    }
}

async function generateGpx() {
    if (!state.routeReady || state.generating) return;
    const nameValidation = updateActivityNameUi(true);
    if (!nameValidation.valid) {
        elements.activityName.focus();
        return;
    }

    const preserve = preservingImportedTiming();
    let parsedPace = null;
    let finish = null;
    if (!preserve) {
        parsedPace = parsePaceInput(elements.pace.value, activityType());
        if (!parsedPace.valid) {
            updatePaceUi(true);
            elements.pace.focus();
            return;
        }

        finish = finishValidation();
        if (!finish.valid) {
            updatePaceUi(false, true);
            elements.finishTime.focus();
            return;
        }
    } else if (!state.importedTrack.preserveAvailable) {
        showError('The imported GPX does not have complete, increasing timestamps.');
        return;
    }

    const requestId = state.generationRequestId + 1;
    state.generationRequestId = requestId;
    const controller = new AbortController();
    state.generationController = controller;
    state.generating = true;
    syncGenerateState();
    setGenerateButtonLabel(true);

    try {
        if (state.importedTrack) {
            const mode = preserve ? 'preserved' : 'retimed';
            const result = preserve
                ? { gpx: window.GpxImport.serializePreserved(
                    state.importedTrack,
                    nameValidation.name,
                    activityType(),
                ) }
                : window.GpxImport.serializeRetimed(
                    state.importedTrack,
                    nameValidation.name,
                    activityType(),
                    finish.date,
                    parsedPace.seconds,
                );
            if (requestId !== state.generationRequestId) return;
            downloadText(result.gpx, activityFilename(nameValidation.name, mode));
            return;
        }

        const response = await fetch('/api/v1/generate-strava-gpx', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                route_points: state.routePoints,
                route_distance: state.routeDistanceMeters,
                activity_type: activityType(),
                activity_name: nameValidation.name,
                end_time: finish.date.toISOString(),
                pace: parsedPace.normalized,
            }),
            signal: controller.signal,
        });
        const payload = await response.json();
        if (!response.ok) throw new Error(payload.error || 'GPX generation failed');
        if (requestId !== state.generationRequestId) return;
        downloadText(payload.gpx, activityFilename(nameValidation.name, 'generated'));
    } catch (error) {
        if (error.name === 'AbortError') return;
        if (requestId !== state.generationRequestId) return;
        showError(error.message);
    } finally {
        if (requestId === state.generationRequestId) {
            state.generationController = null;
            state.generating = false;
            setGenerateButtonLabel(false);
            syncGenerateState();
        }
    }
}

function setFinishTimeToNow() {
    cancelGeneration();
    const now = new Date();
    const local = new Date(now.getTime() - now.getTimezoneOffset() * 60000);
    elements.finishTime.value = local.toISOString().slice(0, 19);
    updatePaceUi(false);
}

function setRouteStatus(message, className) {
    elements.routeStatus.textContent = message;
    elements.routeStatus.className = `route-status ${className}`;
}

function showError(message) {
    elements.toast.textContent = message;
    elements.toast.hidden = false;
    window.clearTimeout(elements.toast.hideTimer);
    elements.toast.hideTimer = window.setTimeout(() => { elements.toast.hidden = true; }, 5000);
}

function downloadText(text, filename) {
    const url = URL.createObjectURL(new Blob([text], { type: 'application/gpx+xml;charset=utf-8' }));
    const anchor = document.createElement('a');
    anchor.href = url;
    anchor.download = filename;
    document.body.append(anchor);
    anchor.click();
    anchor.remove();
    URL.revokeObjectURL(url);
}

function fileTimestamp(date) {
    return date.toISOString().replace(/[-:]/g, '').replace(/\..+/, '').replace('T', '_');
}

function activityFilename(name, mode) {
    const safeName = name.normalize('NFKC')
        .replace(/[\\/:*?"<>|\u0000-\u001f]/g, '_')
        .trim()
        .slice(0, 80) || 'strava_activity';
    return `${safeName}_${mode}_${fileTimestamp(new Date())}.gpx`;
}

window.addEventListener('DOMContentLoaded', initialise);
