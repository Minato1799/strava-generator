# Strava Generator

[![Tests](https://github.com/Minato1799/strava-generator/actions/workflows/tests.yml/badge.svg)](https://github.com/Minato1799/strava-generator/actions/workflows/tests.yml)
[![Vercel](https://img.shields.io/badge/Vercel-Live-000000?logo=vercel)](https://strava-generator-opal.vercel.app)

A stateless Django route builder that creates timestamped GPX files for running and cycling activities.

**Live site:** [strava.scan-realtime.site](https://strava.scan-realtime.site)

**Fallback:** [strava-generator-opal.vercel.app](https://strava-generator-opal.vercel.app)

> Use this project for personal route simulation and testing. Respect Strava's rules and only upload activity data that accurately represents your effort.

## Features

- Interactive Leaflet and OpenStreetMap route builder
- Location search powered by Nominatim
- Separate foot and bike routing profiles powered by OSRM, including mapped park paths
- Reorderable and draggable route points
- Manual `MM:SS` pace (or number-pad digits such as `530`) with live speed, duration, and calculated start time
- Custom finish time and deterministic GPX 1.1 timestamps
- Stateless deployment: no account, database, or Google Maps API key required
- Vercel-ready Django deployment with source-controlled runtime settings

## Architecture

```text
Browser (Leaflet UI)
  ├─ POST /api/v1/search-location  → Nominatim
  ├─ POST /api/v1/route            → OSRM foot or bike profile
  └─ POST /api/v1/generate-strava-gpx
       └─ Django + Python GPX generator
```

The app intentionally does not persist users, routes, or generated files. Route points and search text are sent in JSON request bodies rather than query strings, and API responses are marked `private, no-store`. Warm application instances keep only a short-lived, bounded cache to coalesce identical provider requests and pace calls within that process. The browser reuses the route geometry it has already fetched when generating a GPX, avoiding a duplicate routing request.

Public OpenStreetMap services are suitable for normal, low-volume use but do not provide a production SLA; follow both the [routing service usage policy](https://routing.openstreetmap.de/about.html) and [Nominatim usage policy](https://operations.osmfoundation.org/policies/nominatim/). Per-process pacing is not a global rate limit across Vercel instances, so move to a managed or self-hosted provider before scaling traffic. Infrastructure and upstream providers can still retain ordinary request metadata under their own policies.

## Local development

Python 3.12 and [`uv`](https://docs.astral.sh/uv/) are recommended.

```bash
uv venv --python 3.12 .venv
uv pip install --python .venv/bin/python --require-hashes -r requirements-dev.txt
CONTEXT=DEBUG .venv/bin/python manage.py runserver
```

Open <http://127.0.0.1:8000>.

## Tests

```bash
.venv/bin/python manage.py check
.venv/bin/ruff check .
CONTEXT=DEBUG .venv/bin/coverage run --branch --source=mylibs,strava,strava_generator manage.py test tests
.venv/bin/coverage report --skip-covered --fail-under=80
.venv/bin/pip-audit --require-hashes -r requirements.txt
node --check strava_generator/static/strava_generator/js/index.js
```

## Deploy to Vercel

Vercel detects `manage.py`, uses Python 3.12 from `.python-version`, installs `requirements.txt`, and collects Django static assets automatically.

```bash
vercel link
vercel env add DJANGO_SECRET_KEY production --sensitive
vercel deploy --prod
```

Generate a unique Django secret rather than committing one to the repository.

## Configuration

| Variable | Required | Purpose |
| --- | --- | --- |
| `DJANGO_SECRET_KEY` | Production | Django cryptographic signing key |
| `ALLOWED_HOSTS` | No | Comma-separated custom hosts in addition to localhost and `.vercel.app` |
| `ROUTING_FOOT_BASE_URL` | No | OSRM-compatible endpoint for walking and running routes |
| `ROUTING_BIKE_BASE_URL` | No | OSRM-compatible endpoint for cycling routes |
| `ROUTING_FOOT_FALLBACK_BASE_URL` | No | Optional OSRM-compatible fallback after the primary walking graph is unavailable or cannot connect the points |
| `ROUTING_BIKE_FALLBACK_BASE_URL` | No | Optional OSRM-compatible fallback after the primary cycling graph is unavailable or cannot connect the points |
| `ROUTING_LOCAL_BBOX` | With a loopback router | `west,south,east,north` bounds; requests outside the regional graph skip directly to the fallback |
| `GEOCODING_SEARCH_URL` | No | Nominatim-compatible search endpoint |
| `PROVIDER_USER_AGENT` | No | Contactable application identity sent to routing and geocoding providers |
| `PROVIDER_REFERER` | No | Public application URL sent to routing and geocoding providers |
| `PROVIDER_CACHE_MAX_ENTRIES` | No | Maximum cached route and search responses per warm process; default `256` |
| `ROUTE_CACHE_TTL_SECONDS` | No | Route response cache lifetime; default `300` |
| `SEARCH_CACHE_TTL_SECONDS` | No | Search response cache lifetime; default `900` |
| `ROUTING_PROVIDER_MIN_INTERVAL_SECONDS` | No | Minimum interval between routing calls to the same host; default `1.05` |
| `GEOCODING_PROVIDER_MIN_INTERVAL_SECONDS` | No | Minimum interval between geocoding calls to the same host; default `1.05` |
| `CONTEXT=DEBUG` | Local only | Enables Django debug mode |

See [ROADMAP.md](ROADMAP.md) for completed hardening work, operational follow-ups, and the historic-secret remediation that requires the original key owner.

## Upstream and license

This is a substantially modified Vercel-oriented version of [iamdubrovskii/strava-generator](https://github.com/iamdubrovskii/strava-generator). The original project used Django accounts, SQLite usage tokens, Google Maps, and server-side activity history. This version replaces those components with a stateless OpenStreetMap workflow while preserving upstream attribution.

Distributed under the [GNU General Public License v3.0](LICENSE). See the upstream repository history for the original authorship and commit provenance.
