# Roadmap

This roadmap tracks work needed to keep the public demo safe, maintainable, and practical to operate. Completed items are verified in code or in the linked deployment workflow; future items are intentionally not presented as finished.

## Completed foundation

- Replaced the retired Google Maps/account workflow with a stateless Leaflet and OpenStreetMap interface.
- Added separate foot and bike routing so mapped park paths can be used.
- Added a user-defined pace with live duration and start-time calculation.
- Added server-side input, distance, timestamp, and provider-response validation.
- Added a health endpoint, automated tests, and a Vercel production deployment.

## Current hardening release

- Remove unreachable legacy assets and application stubs from the deployment artifact.
- Lock Python dependencies and validate them in CI.
- Add linting, coverage, CodeQL, Dependabot, and pinned GitHub Actions.
- Add repository contribution, security, ownership, and upstream-provenance documentation.
- Cache and coalesce identical provider requests, pace calls within each warm process, and emit privacy-safe provider metrics.
- Run the function in Singapore and validate the exact build through a protected Vercel Preview before production.
- Stage conservative, log-only Vercel rate-limit rules for review before they can block traffic.
- Require pull requests and passing checks before changes reach `main`.

## Next: provider and observability maturity

- Review staged rate-limit telemetry, then publish tuned rules only after confirming they do not affect normal use.
- Add alerts for sustained provider failures, application 5xx responses, and latency regressions.
- Move routing/geocoding to managed or self-hosted providers if traffic exceeds public-demo policy or availability needs.
- Benchmark Singapore against another region if the audience becomes geographically distributed.
- Add low-frequency, policy-safe synthetic route checks and browser end-to-end coverage.

## Security follow-up requiring the original key owner

GitHub reports three historic Google API key findings inherited from upstream history. The current application does not use those keys, but history cleanup cannot prove revocation.

1. Ask the owner of the original Google Cloud project to revoke or restrict the keys.
2. Record confirmation without copying key values into an issue, commit, or log.
3. Coordinate a `git filter-repo` history rewrite and force-push only after all collaborators agree to re-clone.
4. Ask GitHub Support to remove cached sensitive data if required.
5. Resolve each secret-scanning alert using its verified state; never mark a key revoked without confirmation.

The history rewrite is deliberately not automated in this release because it is destructive and cannot revoke credentials at the provider.
