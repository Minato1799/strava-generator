# VPS operations

These files provide two small systemd jobs for the production VPS:

- `strava-generator.service` runs the application from the atomic `current`
  release symlink with one process and eight threads.
- `strava-healthcheck.timer` checks the local Django health endpoint every two
  minutes and attempts at most one service restart after a failure.
- `strava-config-backup.timer` creates a root-only configuration archive each
  day and retains archives for 14 days.
- `strava-osrm-foot.service` and `strava-osrm-bike.service` run pinned,
  read-only OSRM containers on `127.0.0.1:8731` and `127.0.0.1:8732`.

The backup covers the Caddy configuration, the application environment file,
the application service unit, and these operational jobs. Application source is
not copied because it is recoverable from the recorded Git commit. Archives are
stored in `/var/backups/strava-generator`; an off-server Hostinger snapshot or
backup is still required for disaster recovery.

Install scripts as mode `0750` in `/usr/local/sbin`, install units as mode
`0644` in `/etc/systemd/system`, then run:

```sh
systemctl daemon-reload
systemctl enable --now strava-healthcheck.timer strava-config-backup.timer
systemctl start strava-healthcheck.service strava-config-backup.service
systemctl list-timers 'strava-*'
```

Production geocoding intentionally stays on the public Nominatim endpoint only
while traffic is low. The single Gunicorn process makes the in-process 1.05
second geocoding interval apply across all application threads, while a
15-minute bounded cache and Cloudflare edge rate limit reduce duplicate and
abusive requests. Do not increase the worker count without first moving
geocoding to a managed/self-hosted provider or adding a shared global limiter.

The OSRM services expect a preprocessed regional MLD dataset at
`/srv/strava-osrm/current/{foot,bike}/thailand.osrm.*`. Build a new version in a
separate release directory, verify both route profiles, switch the `current`
symlink, and restart the two units. Keep the prior release for rollback. The
application can use the private graphs while retaining an external fallback:

```sh
/usr/local/sbin/strava-osrm-build YYYYMMDD
ln -sfn /srv/strava-osrm/releases/YYYYMMDD-bangkok-region /srv/strava-osrm/current
systemctl restart strava-osrm-foot.service strava-osrm-bike.service
```

The build script clips the current Geofabrik Thailand extract to a Bangkok and
surrounding-provinces bounding box before creating the foot and bicycle MLD
graphs. It never changes `current`; promotion stays an explicit, reversible
operation after route verification.

```env
ROUTING_FOOT_BASE_URL=http://127.0.0.1:8731/route/v1/foot
ROUTING_BIKE_BASE_URL=http://127.0.0.1:8732/route/v1/bike
ROUTING_FOOT_FALLBACK_BASE_URL=https://routing.openstreetmap.de/routed-foot/route/v1/driving
ROUTING_BIKE_FALLBACK_BASE_URL=https://routing.openstreetmap.de/routed-bike/route/v1/driving
ROUTING_LOCAL_BBOX=99.3,12.7,101.5,14.8
```
