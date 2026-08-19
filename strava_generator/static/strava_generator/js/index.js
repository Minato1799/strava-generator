const MAX_POINTS = 26;
const DEFAULT_CENTER = [13.7563, 100.5018];
const ACTIVITY_MINIMUMS = { run: 3000, bike: 5000 };

const state = {
    map: null,
    markers: [],
    routeLayer: null,
    routeReady: false,
    routeController: null,
    updateTimer: null,
};

const elements = {
    searchForm: document.querySelector('#search-form'),
    searchInput: document.querySelector('#location-search'),
    searchResults: document.querySelector('#search-results'),
    clearRoute: document.querySelector('#clear-route'),
    routeStatus: document.querySelector('#route-status'),
    pointList: document.querySelector('#point-list'),
    pointCount: document.querySelector('#point-count'),
    finishTime: document.querySelector('#finish-time'),
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
        const { lat, lng } = event.latlng;
        addPoint(lat, lng, `Pinned point ${state.markers.length + 1}`);
    });

    elements.searchForm.addEventListener('submit', searchLocations);
    elements.clearRoute.addEventListener('click', clearRoute);
    elements.setNow.addEventListener('click', setFinishTimeToNow);
    elements.generate.addEventListener('click', generateGpx);
    document.querySelectorAll('input[name="activity"]').forEach((input) => {
        input.addEventListener('change', scheduleRouteUpdate);
    });
    document.addEventListener('click', (event) => {
        if (!elements.searchForm.contains(event.target)) elements.searchResults.hidden = true;
    });

    setFinishTimeToNow();
    renderPointList();

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

function pointString() {
    return state.markers
        .map(({ marker }) => {
            const point = marker.getLatLng();
            return `${point.lat.toFixed(7)},${point.lng.toFixed(7)}`;
        })
        .join('|');
}

function addPoint(latitude, longitude, name) {
    if (state.markers.length >= MAX_POINTS) {
        showError(`A route can contain at most ${MAX_POINTS} points.`);
        return;
    }

    const marker = L.marker([latitude, longitude], { draggable: true }).addTo(state.map);
    marker.on('dragend', scheduleRouteUpdate);
    state.markers.push({ marker, name });
    renderPointList();
    scheduleRouteUpdate();
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

function renderPointList() {
    elements.pointCount.textContent = `${state.markers.length} / ${MAX_POINTS}`;
    elements.pointList.innerHTML = '';

    if (!state.markers.length) {
        const empty = document.createElement('li');
        empty.className = 'empty-points';
        empty.textContent = 'Your route points will appear here.';
        elements.pointList.append(empty);
        return;
    }

    state.markers.forEach((item, index) => {
        item.marker.unbindTooltip();
        item.marker.bindTooltip(String.fromCharCode(65 + index), {
            permanent: true,
            direction: 'center',
            className: 'marker-label',
        });

        const coordinates = item.marker.getLatLng();
        const row = document.createElement('li');
        row.className = 'point-item';
        row.innerHTML = `
            <span class="point-letter">${String.fromCharCode(65 + index)}</span>
            <span class="point-copy">
                <strong title="${escapeHtml(item.name)}">${escapeHtml(item.name)}</strong>
                <small>${coordinates.lat.toFixed(5)}, ${coordinates.lng.toFixed(5)}</small>
            </span>
            <span class="point-actions">
                <button type="button" data-action="up" aria-label="Move point up">↑</button>
                <button type="button" data-action="down" aria-label="Move point down">↓</button>
                <button type="button" data-action="remove" aria-label="Remove point">×</button>
            </span>`;
        row.querySelector('[data-action="up"]').addEventListener('click', () => movePoint(index, -1));
        row.querySelector('[data-action="down"]').addEventListener('click', () => movePoint(index, 1));
        row.querySelector('[data-action="remove"]').addEventListener('click', () => removePoint(index));
        row.querySelector('.point-copy').addEventListener('click', () => state.map.panTo(item.marker.getLatLng()));
        elements.pointList.append(row);
    });
}

function scheduleRouteUpdate() {
    window.clearTimeout(state.updateTimer);
    state.updateTimer = window.setTimeout(updateRoute, 350);
}

async function updateRoute() {
    state.routeReady = false;
    elements.generate.disabled = true;

    if (state.routeController) state.routeController.abort();
    if (state.routeLayer) {
        state.map.removeLayer(state.routeLayer);
        state.routeLayer = null;
    }

    if (state.markers.length < 2) {
        setRouteStatus('Add two points to begin', 'is-empty');
        return;
    }

    state.routeController = new AbortController();
    setRouteStatus('Building route…', 'is-loading');

    const params = new URLSearchParams({ points: pointString(), activity_type: activityType() });
    try {
        const response = await fetch(`/api/v1/route?${params}`, { signal: state.routeController.signal });
        const payload = await response.json();
        if (!response.ok) throw new Error(payload.error || 'Route could not be built');

        state.routeLayer = L.polyline(payload.route, {
            color: '#fc4c02', weight: 5, opacity: .92, lineJoin: 'round',
        }).addTo(state.map);
        state.map.fitBounds(state.routeLayer.getBounds(), { padding: [45, 45], maxZoom: 16 });

        const distance = payload.distance;
        const minimum = ACTIVITY_MINIMUMS[activityType()];
        const statusClass = distance < minimum ? 'is-warning' : 'is-ready';
        const suffix = distance < minimum ? ` · suggested minimum ${(minimum / 1000).toFixed(0)} km` : '';
        setRouteStatus(`${(distance / 1000).toFixed(2)} km${suffix}`, statusClass);
        state.routeReady = true;
        elements.generate.disabled = false;
    } catch (error) {
        if (error.name === 'AbortError') return;
        setRouteStatus(error.message, 'is-error');
        showError(error.message);
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
        const response = await fetch(`/api/v1/search-location?q=${encodeURIComponent(query)}`);
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
    elements.searchResults.innerHTML = '';
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
    state.markers.forEach(({ marker }) => state.map.removeLayer(marker));
    state.markers = [];
    if (state.routeLayer) state.map.removeLayer(state.routeLayer);
    state.routeLayer = null;
    state.routeReady = false;
    elements.generate.disabled = true;
    renderPointList();
    setRouteStatus('Add two points to begin', 'is-empty');
}

async function generateGpx() {
    if (!state.routeReady) return;
    const finishDate = new Date(elements.finishTime.value);
    if (Number.isNaN(finishDate.getTime())) {
        showError('Choose a valid finish time.');
        return;
    }

    elements.generate.disabled = true;
    const original = elements.generate.innerHTML;
    elements.generate.innerHTML = '<span>Generating…</span><span>•••</span>';
    const params = new URLSearchParams({
        points: pointString(),
        activity_type: activityType(),
        end_time: finishDate.toISOString(),
    });

    try {
        const response = await fetch(`/api/v1/generate-strava-gpx?${params}`);
        const payload = await response.json();
        if (!response.ok) throw new Error(payload.error || 'GPX generation failed');
        downloadText(payload.gpx, `strava_${fileTimestamp(new Date())}.gpx`);
    } catch (error) {
        showError(error.message);
    } finally {
        elements.generate.innerHTML = original;
        elements.generate.disabled = !state.routeReady;
    }
}

function setFinishTimeToNow() {
    const now = new Date();
    const local = new Date(now.getTime() - now.getTimezoneOffset() * 60000);
    elements.finishTime.value = local.toISOString().slice(0, 19);
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

function escapeHtml(value) {
    const element = document.createElement('div');
    element.textContent = value;
    return element.innerHTML;
}

window.addEventListener('DOMContentLoaded', initialise);
