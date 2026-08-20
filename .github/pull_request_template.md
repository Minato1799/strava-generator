## Summary

Describe the problem and the user-visible result.

## Verification

- [ ] `CONTEXT=DEBUG .venv/bin/python manage.py check`
- [ ] `.venv/bin/ruff check .`
- [ ] Coverage remains at or above 80%
- [ ] `.venv/bin/pip-audit --require-hashes -r requirements.txt`
- [ ] `node --check strava_generator/static/strava_generator/js/index.js`
- [ ] Relevant browser or API flow tested when behavior changed

## Safety checklist

- [ ] No credentials, tokens, private route data, or generated GPX files are committed
- [ ] User input remains validated server-side
- [ ] New third-party requests document attribution, privacy, and usage limits
- [ ] Deployment or environment-variable changes include a rollback note
- [ ] Upstream-derived code retains its license and attribution
