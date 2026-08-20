# Strava Generator — Vercel Edition

[![Tests](https://github.com/Minato1799/strava-generator/actions/workflows/tests.yml/badge.svg)](https://github.com/Minato1799/strava-generator/actions/workflows/tests.yml)
[![Vercel](https://img.shields.io/badge/Vercel-Live-000000?logo=vercel)](https://strava-generator-opal.vercel.app)

A stateless Django route builder that creates timestamped GPX files for running and cycling activities.

**Live site:** [strava-generator-opal.vercel.app](https://strava-generator-opal.vercel.app)

> Use this project for personal route simulation and testing. Respect Strava's rules and only upload activity data that accurately represents your effort.

## Features

- Interactive Leaflet and OpenStreetMap route builder
- Location search powered by Nominatim
- Separate foot and bike routing profiles powered by OSRM, including mapped park paths
- Reorderable and draggable route points
- Manual `MM:SS` pace (or number-pad digits such as `530`) with live speed, duration, and calculated start time
- Custom finish time and deterministic GPX 1.1 timestamps
- Stateless deployment: no account, database, or Google Maps API key required
- Zero-configuration Django deployment on Vercel

## Architecture

```text
Browser (Leaflet UI)
  ├─ /api/v1/search-location  → Nominatim
  ├─ /api/v1/route            → OSRM foot or bike profile
  └─ POST /api/v1/generate-strava-gpx
       └─ Django + Python GPX generator
```

The app intentionally does not persist users, routes, or generated files. The browser reuses the route geometry it has already fetched when generating a GPX, avoiding a duplicate routing request. Public OpenStreetMap services are suitable for normal, low-volume use but do not provide a production SLA; follow the [routing service usage policy](https://routing.openstreetmap.de/about.html).

## Local development

Python 3.12 and [`uv`](https://docs.astral.sh/uv/) are recommended.

```bash
uv venv --python 3.12 .venv
uv pip install --python .venv/bin/python -r requirements.txt
CONTEXT=DEBUG .venv/bin/python manage.py runserver
```

Open <http://127.0.0.1:8000>.

## Tests

```bash
.venv/bin/python manage.py check
.venv/bin/python manage.py test tests
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
| `CONTEXT=DEBUG` | Local only | Enables Django debug mode |

## Upstream and license

This is a substantially modified Vercel-oriented version of [iamdubrovskii/strava-generator](https://github.com/iamdubrovskii/strava-generator). The original project used Django accounts, SQLite usage tokens, Google Maps, and server-side activity history. This version replaces those components with a stateless OpenStreetMap workflow while preserving upstream attribution.

Distributed under the [GNU General Public License v3.0](LICENSE). See the upstream repository history for the original authorship and commit provenance.
