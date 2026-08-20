# Contributing

Thanks for improving Strava Generator. Keep changes small, explain the user
impact, and preserve the project's stateless and privacy-conscious design.

## Local setup

Use Python 3.12. With `uv` installed:

```bash
uv venv --python 3.12 .venv
uv pip install --python .venv/bin/python --require-hashes -r requirements-dev.txt
CONTEXT=DEBUG .venv/bin/python manage.py runserver
```

When changing dependencies, edit the corresponding `.in` file and regenerate
both locks deliberately:

```bash
uv pip compile requirements.in --python-version 3.12 --generate-hashes --output-file requirements.txt
uv pip compile requirements-dev.in --python-version 3.12 --generate-hashes --output-file requirements-dev.txt
```

Never commit `.env`, `.vercel`, database files, generated GPX files, route
coordinates, or real credentials.

## Before opening a pull request

Run the same checks as CI:

```bash
CONTEXT=DEBUG .venv/bin/python manage.py check
.venv/bin/ruff check .
CONTEXT=DEBUG .venv/bin/coverage run --branch --source=mylibs,strava,strava_generator manage.py test tests
.venv/bin/coverage report --skip-covered --fail-under=80
.venv/bin/pip-audit --require-hashes -r requirements.txt
node --check strava_generator/static/strava_generator/js/index.js
```

For UI or routing changes, also verify the affected flow in a browser and cover
input validation with a focused test. Describe any third-party API, new data
retention, environment variable, or deployment impact in the pull request.

## Project constraints

- Keep GPX creation stateless and avoid retaining route or activity data.
- Validate client-provided values again on the server.
- Respect OpenStreetMap attribution and public-service usage policies.
- Do not add features intended to misrepresent real-world activity.
- Do not embed service credentials in browser code or repository history.
- Retain GPL-3.0 and upstream attribution for derived code.

Report security issues using [SECURITY.md](SECURITY.md), not a public issue with
sensitive details.
