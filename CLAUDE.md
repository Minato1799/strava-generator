# Claude continuation guide

Last verified: 2026-08-20, Asia/Bangkok.

This file is the durable handoff for Claude or another coding agent. Read it before changing this repository. Re-check all drift-prone GitHub and Vercel facts before relying on them, and treat the user's latest message as the final authority.

## Current objective

Keep the Strava Generator small, stateless, privacy-conscious, and easy to operate while modernizing the parts users actually feel. Local GPX import, editable activity identity, and Preserve/Re-time export modes are released. The next implementation should focus on mobile route building, accessibility, a three-way effort calculator, and permanent browser regression coverage.

The latest request authorizes committing and pushing this handoff update on a feature branch. It does not authorize PR creation, merge, deployment, destructive history work, or unrelated GitHub/Vercel/Cloudflare/VPS changes.

Current local handoff state:

- Branch: `agent/update-claude-handoff`, based on `main` at `443539fdbb88d65cb4d55c9a1c480bf2c3dcabf5`. It contains only the requested `CLAUDE.md` handoff update; verify its current commit/push state before continuing.
- Feature PR #6 and cache-busting hotfix PR #7 are merged. No pull requests were open at the time of this snapshot.
- The real user-supplied GPX was used only for local browser verification and was not copied into the repository.
- The real file contains 2,200 track points. Production Chrome verification passed on both the VPS primary and Vercel fallback: Preserve retained all timestamps, elevations, and sensor extensions; Re-time retained geometry/elevation, changed the activity identity/type, regenerated strictly increasing timestamps from pace 5:30, removed sensor extensions, and made no request to the application's GPX-generation API.
- Release verification: Ruff and Django checks passed, 51 tests passed with at least 85% branch coverage in the feature release, deploy check passed, dependency audit found no known vulnerabilities, both JavaScript files passed syntax checks, GitHub Tests/CodeQL/Vercel checks passed, and public root/health endpoints returned 200.

## Product and architecture

- Public repository: `Minato1799/strava-generator`
- Primary production URL: `https://strava.scan-realtime.site`; Vercel fallback: `https://strava-generator-opal.vercel.app`.
- Stack: Django 5.2 LTS, Python 3.12, native JavaScript, Leaflet 1.9.4, OpenStreetMap tiles, Nominatim-compatible search, and OSRM-compatible foot/bike routing.
- The application is intentionally stateless. It has no user accounts, database, stored route history, or required Google Maps key.
- The browser builds a manual route and sends JSON POST requests. The server validates inputs/provider output and generates authoritative timestamps for manually drawn routes.
- Imported GPX files are parsed locally in the browser. Preserve changes only activity identity and retains original timestamps/elevation/extensions. Re-time retains geometry/elevation, removes track-point sensor extensions, and creates new timestamps locally; imported GPX content is not sent to the application API.
- Warm processes have short-lived bounded caches, request coalescing, and per-process provider pacing. This is not a global rate limit across Vercel instances.
- `requirements*.in` record dependency intent; the hash-locked `requirements*.txt` files are the reviewed install inputs. Do not commit Vercel-generated `pyproject.toml` or `uv.lock` files.
- Preserve GPL-3.0 and upstream attribution. Read `UPSTREAM.md` before provenance-related changes.

## Last verified external state

These facts are a handoff snapshot, not permanent truth. Verify them before release work.

- `main`, VPS application release, and production source SHA: `443539fdbb88d65cb4d55c9a1c480bf2c3dcabf5`
- Primary production URL: `https://strava.scan-realtime.site`; Vercel remains the fallback at `https://strava-generator-opal.vercel.app`.
- Latest verified Vercel fallback deployment: `dpl_2mswpDYHwk8xELo25xL6q2HvKQqZ`; runtime region `sin1`, Python 3.12, about 18.16 MiB.
- Vercel rollback targets: `dpl_6hPyjvUwdVsQVq1CXU92PSXc7dub` is the GPX feature before cache-busting; `dpl_35neWR4VwVbFCYfavEtXJiVhLEWt` is the pre-feature production.
- VPS `current` points to `/opt/strava-generator/releases/443539fdbb88d65cb4d55c9a1c480bf2c3dcabf5`. Immediate rollback is release `9f2b90e9e179dd586c29a7ca5f2736f2b4f2b4a9`; pre-feature rollback is `3ba9b93ae7b7e8c99806f1aa8318c78021e76979`.
- VPS services `strava-generator`, `caddy`, `strava-osrm-foot`, and `strava-osrm-bike` were active after release. No VPS error-priority entries and no Vercel error/500 records were found in the post-release verification window.
- Static application assets use the query version `v=20260820-gpx1`. This was added because Cloudflare served a previous unversioned `index.js`/`index.css` for up to four hours after the first GPX rollout. Do not remove versioning without replacing it with content-hashed assets or an equivalent cache-safe strategy.
- Cloudflare Browser Insights attempts to inject its beacon, which the current CSP intentionally blocks. It does not affect application behavior. Prefer disabling that Cloudflare feature if a clean console is required; do not weaken `script-src` merely to allow an unpinned injected script.
- `main` requires a pull request and the `test`, `Analyze (python)`, `Analyze (javascript-typescript)`, `CodeQL`, and `Vercel` checks. Admin enforcement and conversation resolution were enabled; force-push and deletion were disabled.
- No pull requests were open at the time of this snapshot.
- Production and generic Preview each have a distinct encrypted `DJANGO_SECRET_KEY`. Never print, copy, or reuse either value. A stale branch-specific Preview override still exists for `agent/park-routing-manual-pace`.
- The Vercel project default function timeout is 30 seconds. Verify the effective timeout on each Preview/Production artifact rather than assuming project defaults were applied.
- Production has an exact `ALLOWED_HOSTS` environment entry for `strava-generator-opal.vercel.app`; generated deployment, branch, and project-production hosts come from Vercel system variables.
- Cloudflare proxies the primary production hostname with Full (strict) TLS. One active rate-limit rule covers the three POST APIs at 10 requests per 10 seconds per IP. This is abuse protection, not aggregate Nominatim quota enforcement.
- GitHub secret scanning has three open historic Google API key findings inherited from upstream history. The current application does not use them. Do not display or test the values, do not claim revocation, and do not rewrite history without original-key-owner confirmation plus explicit user approval.

## Preserve these invariants

1. Do not add accounts, a database, server-side route history, or automatic local persistence unless the user explicitly scopes a feature that needs them.
2. Never log search text, route coordinates, GPX contents, credentials, or provider URLs containing user input.
3. Keep route/search/generate APIs as JSON POST endpoints with fixed public error messages and `private, no-store` responses.
4. Keep server-side validation authoritative for coordinate bounds, waypoint/track limits, maximum distance, provider schemas, geometry-distance consistency, pace, finish time, and monotonic GPX timestamps.
   Preserve the current safety ceilings unless a tested requirement changes them: 26 route points, 10,000 track points, 50 km, and 5 search results.
5. Do not implement Nominatim autocomplete. Do not bulk-download, prefetch, or offer offline use through the public OpenStreetMap tile service.
6. Do not add automatic retries against public routing/geocoding providers. Cache, coalesce, pace, fail clearly, and use a managed or self-hosted provider before meaningful scale.
7. Preserve CSP, SRI, security headers, privacy copy, run/bike routing profiles, request cancellation, and stale-response protection.
8. Keep server validation authoritative for manually drawn routes. Imported-file Preserve/Re-time is intentionally local-only; do not send imported GPX content or sensor data to the application API.
9. Do not add features intended to fabricate real-world activity. Keep the product framed as legitimate personal route simulation and testing.

## Prioritized modernization backlog

### P0 — before increasing traffic

- Public Nominatim and routing services allow roughly one request per second for the whole application and provide no production SLA. Per-process Vercel pacing cannot enforce that aggregate ceiling. Stay low-volume or move to a managed/self-hosted provider or a genuinely global queue/limiter before promotion or meaningful growth.
- Keep Vercel fail-closed when `DJANGO_SECRET_KEY` is absent, keep Preview and Production secrets distinct, force `DEBUG=False` on Vercel, and allow only approved Vercel/custom hosts. Re-verify these controls after every environment or domain change.
- Review the three firewall drafts, then let the user publish the log-only version. Observe real traffic, tune it, and evaluate enforcing actions in a later reviewed change. Firewall protection does not replace outbound provider quota control.
- Ask the original Google Cloud project owner to revoke or restrict the three historic keys and confirm without copying values. Only then plan any destructive history rewrite.

### P1 — next implementation PRs

1. **Mobile and accessible route building**
   - Make the mobile hero compact and size the map relative to `dvh`.
   - Put route controls in a usable bottom sheet/accordion and keep Generate reachable with a safe-area-aware sticky action.
   - Give the map an appropriate landmark/region role and add a keyboard path such as “Add point at map center” or explicit latitude/longitude input.
   - Make search results keyboard-operable with correct expanded/result state, Arrow/Escape behavior, focus management, and announcements.
   - Increase small waypoint controls and critical text to comfortable touch/read sizes.

2. **Editable Pace / Speed / Duration calculator**
   - Make all three fields editable. Whichever valid field the user edits last becomes `activeSource`; calculate the other two from route distance.
   - Use: `speed_kmh = 3600 / pace_seconds_per_km`, `duration_seconds = distance_km * pace_seconds_per_km`, and the corresponding inverse formulas.
   - Define rounding, empty, partial, zero, range, and route-distance-change behavior explicitly.
   - Normalize Speed or Duration back to pace before Generate so the existing server API remains authoritative and backward compatible.
   - Unit-test parsing, normalization, all inverse formulas, rounding boundaries, and activity-specific limits.

3. **Fix current interaction debt**
   - Do not request geolocation on page load. Add an explicit “Use my location” control with permission/error states.
   - After a marker is dragged, replace the stale place name with a neutral moved-point label or offer explicit rate-limited reverse geocoding.
   - Retain the last-good route while recalculation is pending; dim it and provide Retry on failure instead of clearing it immediately.
   - Add Undo after Clear, show the finish-time timezone, and provide a persistent/dismissible download success state.

4. **Modular JavaScript and real browser tests**
   - Split the 566-line script into small native ES modules such as `calculator.js`, `api.js`, `map.js`, `route-state.js`, and `app.js`. A framework or heavy build pipeline is not required.
   - Add fast JavaScript unit tests for pure calculator/state functions.
   - Add Playwright tests with mocked provider responses for search, point add/reorder/drag, run/bike switching, all calculator inputs, stale-request cancellation, invalid input, and downloaded GPX parsing.
   - Cover at least 320 px and 390 px mobile widths plus keyboard/accessibility checks. Do not call public providers on every pull request.

5. **Production release gate and observability**
   - Add a CI production-settings gate using Django `check --deploy --fail-level WARNING` with an audit-only secret.
   - Configure Vercel Deployment Checks or staged production so a `main` build is not assigned the production alias until required smoke/E2E checks pass.
   - Emit structured JSON with request ID, provider, outcome, status, and elapsed time while excluding user input.
   - Alert on sustained application 5xx, provider 502/failure rate, and latency regression. Confirm severity mapping in Vercel rather than assuming stdout text levels are preserved.

### P2 — resilience and operational maturity

- Make the browser tile URL and attribution configurable without a code change. Move search, routing, and tiles to managed or self-hosted services before traffic can exceed public-demo policy or an SLA becomes necessary.
- Add a timeout to in-process single-flight followers, cap caches by approximate response size/point count as well as entry count, and impose provider response-size/geometry limits before fully materializing large payloads.
- Set an explicit Django request-body ceiling that still accommodates the legitimate 10,000-point GPX payload, and return a small fixed 413 response when exceeded.
- Consider a server-issued signed route token/hash that binds validated geometry and distance before GPX generation.
- Benchmark long routes on mobile; use Leaflet canvas/display-only simplification when needed while retaining full validated geometry for GPX.
- Self-host Leaflet and fonts, then tighten CSP and remove unnecessary third-party page-load dependencies.
- Confirm new deployments use the 30-second project default, then benchmark whether 2 GiB memory is still justified.
- Split provider connect/read timeouts and record timeout/429/5xx outcomes separately. Reuse connections where safe, but do not automatically retry public providers.

### P3 — optional product polish

- Thai/English localization with a real `lang` switch.
- Repair or remove the unused/incorrect web manifest.
- Add an “Unofficial, not affiliated with Strava” notice.
- Add scale/direction indicators and elevation/surface only when a suitable provider and usage policy are in place.
- If route saving is requested, start with an explicit “Save on this device” action; never persist coordinates automatically.

## Avoid modernization theatre

- Do not rewrite this single-page application in React, Next.js, Vue, microservices, or a separate API solely to appear modern.
- Do not upgrade production to a prerelease Leaflet build.
- Stay on Django 5.2 LTS while it remains supported and patched; do not move to a shorter-support Django release just because its version number is larger.
- Do not reintroduce Google Maps, accounts, database storage, or a frontend-only trust model.
- Do not add PWA/offline map caching on the public OpenStreetMap tile service.

## Local verification

Use a clean Python 3.12 environment and the hashed dependency files.

```bash
uv venv --python 3.12 .venv
uv pip install --python .venv/bin/python --require-hashes -r requirements-dev.txt
.venv/bin/ruff check .
CONTEXT=DEBUG .venv/bin/python manage.py check
VERCEL=1 DJANGO_SECRET_KEY='audit-only-secret-not-for-any-deployment-0123456789abcdef' .venv/bin/python manage.py check --deploy --fail-level WARNING
CONTEXT=DEBUG .venv/bin/coverage run --branch --source=mylibs,strava,strava_generator manage.py test tests
.venv/bin/coverage report --skip-covered --fail-under=80
node --check strava_generator/static/strava_generator/js/index.js
node --check strava_generator/static/strava_generator/js/gpx-import.js
.venv/bin/pip-audit --require-hashes -r requirements.txt
git diff --check
```

If JavaScript is split into modules, update the syntax/unit-test commands and CI in the same PR. Tests must not depend on live public providers.

## Safe GitHub, Vercel, and VPS workflow

1. Read `README.md`, `ROADMAP.md`, `SECURITY.md`, `UPSTREAM.md`, and this file.
2. Run `git status --short --branch` and `git rev-parse HEAD`. Preserve unrelated user changes.
3. Refresh GitHub state: current branch, open PRs, protection/check names, Dependabot/CodeQL/secret alerts.
4. Refresh Vercel and VPS state: project link, environment-variable scopes without revealing values, current production SHA/deployment/region, VPS `current` symlink/source SHA, service health, Cloudflare behavior, and rollback targets.
5. Work on a new feature branch and one coherent PR. Never bypass protected `main`.
6. Use a distinct encrypted Preview `DJANGO_SECRET_KEY`; do not expose or copy Production secrets.
7. Wait for all required GitHub checks and a protected Preview deployment of the exact commit.
8. Verify Preview root, health, static assets, headers, invalid JSON, calculator/GPX, and browser behavior. If a live provider smoke is necessary, make only a minimal number of spaced requests and record that it is not an SLA test.
9. Before any production change, record both the healthy Vercel deployment ID and VPS release symlink as rollback targets.
10. For VPS release work, create a detached Git worktree at `/opt/strava-generator/releases/<full-sha>`, install only hash-locked requirements, run `check --deploy`, collect static files, and run the test suite in an isolated test environment. Do not source `/etc/strava-generator.env` into the test suite: production HTTPS/local-OSRM settings cause expected test responses and provider mocks to differ. Promote through a temporary symlink and atomic rename, restart only `strava-generator`, and roll back the symlink immediately if the local health check fails. Do not restart OSRM for application-only changes.
11. After an authorized merge/deploy, verify the deployed source SHA, versioned static asset hashes, public root/health, security headers, browser Preserve/Re-time with a safe GPX fixture, one policy-safe foot route and bike route only when routing changed, logs, and 5xx status. Roll back immediately on regression.

## Definition of done

A task is not complete merely because local code builds. Record:

- branch and exact commit SHA;
- files and behavior changed;
- local tests and coverage;
- Preview and Production deployment IDs/URLs and their exact source SHA;
- required GitHub check results;
- runtime/mobile/accessibility evidence appropriate to the change;
- external settings or state changed;
- Production verification and both Vercel/VPS rollback targets, if Production changed;
- remaining risks and any user-only action.

## Token/context handoff protocol

When context is nearly full, update this file only if the durable facts above changed, and leave a compact continuation block in the conversation or a temporary local note. Never store tokens, email addresses, secret values, private URLs, or raw user route/search data.

Use this structure:

```text
Objective:
Latest user instruction:
Completed:
Current branch / HEAD / git status:
Files changed and whether staged:
Verification run and exact results:
GitHub PR/check state:
Vercel Preview/Production deployment and source SHA:
External state changed:
Remaining work in priority order:
Blockers and user-only actions:
Exact next safe command:
Rollback target:
```

On resume, do not start from memory alone: read the latest user instruction, inspect the worktree, and refresh drift-prone external state before acting.
