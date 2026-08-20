# Upstream provenance

This repository is derived from
[`iamdubrovskii/strava-generator`](https://github.com/iamdubrovskii/strava-generator)
under GPL-3.0.

The fork diverged after upstream commit
`6a9665a3d23bbc331d77113f79b6f3d9157c65c1` (2023-05-25). It replaces the
original account, SQLite, token, Google Maps, and activity-history architecture
with a stateless Django and OpenStreetMap deployment for Vercel.

## Upstream update policy

Track the source repository as `upstream`, but review changes manually rather
than merging its branch wholesale:

```bash
git remote add upstream https://github.com/iamdubrovskii/strava-generator.git
git fetch upstream
git log --oneline main..upstream/main
```

Adapt relevant bug fixes or security patches in a focused pull request, retain
the original authorship where appropriate, and run the full local test suite.
Because the architectures now differ substantially, an empty log does not mean
the fork's dependencies or deployment are current; those are maintained
independently through CI and Dependabot.
